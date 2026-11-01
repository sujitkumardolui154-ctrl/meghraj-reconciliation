#!/usr/bin/env bash
# Reporting-only, independently approved Cloud Run revision promotion with rollback.
set -Eeuo pipefail
umask 077
PROJECT="meghraj-reconciliation"
REGION="asia-south1"
SERVICE="sbi-dashboard"
CANDIDATE="$1"
SOURCE_SHA="$2"
WORK="$(mktemp -d)"
PROMOTION_STARTED="no"
BASELINE=""
cleanup() { rm -rf "$WORK"; }
rollback() {
  local rc=$?
  trap - ERR
  if [[ "$PROMOTION_STARTED" == "yes" && -n "$BASELINE" ]]; then
    echo "::error::Release verification failed; restoring baseline revision"
    gcloud run services update-traffic "$SERVICE" --project "$PROJECT" \
      --region "$REGION" --to-revisions "$BASELINE=100" --quiet ||
      echo "::error::ROLLBACK_FAILED_REQUIRES_OPERATOR"
  fi
  cleanup
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

gcloud run services describe "$SERVICE" --project "$PROJECT" \
  --region "$REGION" --format=json > "$WORK/service.json"
gcloud run revisions describe "$CANDIDATE" --project "$PROJECT" \
  --region "$REGION" --format=json > "$WORK/revision.json"

python3 - "$WORK/service.json" "$WORK/revision.json" "$CANDIDATE" "$SOURCE_SHA" "$WORK/preflight.txt" <<'PY'
import json, re, sys
from urllib.parse import urlparse

service = json.load(open(sys.argv[1], encoding="utf-8"))
revision = json.load(open(sys.argv[2], encoding="utf-8"))
candidate, sha, filename = sys.argv[3:]
if not re.fullmatch(r"sbi-dashboard-[a-z0-9-]{5,55}", candidate):
    raise SystemExit("BLOCKED: invalid candidate revision")
if not re.fullmatch(r"[a-f0-9]{40}", sha):
    raise SystemExit("BLOCKED: invalid source commit")
if revision.get("metadata", {}).get("name") != candidate:
    raise SystemExit("BLOCKED: revision identity mismatch")
if revision.get("metadata", {}).get("labels", {}).get("sbi-source-sha") != sha:
    raise SystemExit("BLOCKED: missing source-bound revision label")
conditions = revision.get("status", {}).get("conditions", [])
if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
    raise SystemExit("BLOCKED: revision not Ready")
targets = service.get("status", {}).get("traffic", [])
active = [t for t in targets if (t.get("percent") or 0) > 0]
if len(active) != 1 or active[0].get("percent") != 100:
    raise SystemExit("BLOCKED: existing production traffic is split or unknown")
baseline = active[0].get("revisionName")
if not baseline or baseline == candidate:
    raise SystemExit("BLOCKED: baseline revision cannot be confirmed")
tagged = [t for t in targets if t.get("revisionName") == candidate
          and (t.get("percent") or 0) == 0 and t.get("tag") and t.get("url")]
if len(tagged) != 1:
    raise SystemExit("BLOCKED: candidate must have one 0% traffic tag")
url = tagged[0]["url"]
parts = urlparse(url)
if parts.scheme != "https" or not (parts.hostname and parts.hostname.endswith(".run.app")):
    raise SystemExit("BLOCKED: unsafe Cloud Run candidate URL")
with open(filename, "w", encoding="utf-8") as f:
    f.write(baseline + "\n" + url.rstrip("/") + "\n")
print("IMMUTABLE_SOURCE_LABEL=PASS")
print("CURRENT_BASELINE=VERIFIED")
print("ZERO_TRAFFIC_CANDIDATE=VERIFIED")
PY

mapfile -t details < "$WORK/preflight.txt"
BASELINE="$(sed -n '1p' "$WORK/preflight.txt")"
CANARY_URL="$(sed -n '2p' "$WORK/preflight.txt")"

probe() {
  curl --silent --show-error --fail --location --max-time 20 \
    --retry 2 --retry-delay 2 "$1/login" -o /dev/null
}
probe "$CANARY_URL"
echo "CANDIDATE_LOGIN_HTTP=PASS"

PROMOTION_STARTED="yes"
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" \
  --region "$REGION" --to-revisions "$CANDIDATE=5,$BASELINE=95" --quiet
sleep 30
probe "$CANARY_URL"
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" \
  --region "$REGION" --to-revisions "$CANDIDATE=100" --quiet
gcloud run services describe "$SERVICE" --project "$PROJECT" \
  --region "$REGION" --format=json > "$WORK/final.json"
python3 - "$WORK/final.json" "$CANDIDATE" <<'PY'
import json,sys
service=json.load(open(sys.argv[1],encoding="utf-8"))
active=[t for t in service.get("status",{}).get("traffic",[]) if (t.get("percent") or 0)>0]
if len(active)!=1 or active[0].get("percent")!=100 or active[0].get("revisionName")!=sys.argv[2]:
    raise SystemExit("BLOCKED: final candidate traffic not verified")
print("REPORTING_PRODUCTION_TRAFFIC=VERIFIED")
PY
PROMOTION_STARTED="no"
echo "PRODUCTION_REPORTING_RELEASE=SUCCESS"
echo "FINANCIAL_EXECUTION=RESTRICTED"
