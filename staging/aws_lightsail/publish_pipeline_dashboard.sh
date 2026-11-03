#!/usr/bin/env bash
# Source-pinned read-only PUBLIC preview dashboard release.
# Only the sbi-preview compose service is replaced; Caddy and financial systems untouched.
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ "$(id -u)" -eq 0 && $# -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || { echo "BLOCKED: root and full reviewed SHA required"; exit 2; }
SHA="$1"
SHORT="$(printf '%.12s' "$SHA")"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || { echo "BLOCKED: source SHA differs"; exit 2; }
[[ "$(git -C "$ROOT" remote get-url origin)" == "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git" ]] || { echo "BLOCKED: origin differs"; exit 2; }
REMOTE="$(git -C "$ROOT" ls-remote origin refs/heads/aws/lightsail-preview-20261102 | awk '{print $1}')"
[[ "$REMOTE" == "$SHA" ]] || { echo "BLOCKED: not current reviewed AWS branch"; exit 2; }
for p in staging/aws_lightsail/publish_pipeline_dashboard.sh staging/railway_public/app.py staging/railway_public/pipeline.html staging/railway_public/pipeline_data.py staging/railway_public/Dockerfile staging/aws_lightsail/preview_auth_env.py; do
  git -C "$ROOT" show "$SHA:$p" | cmp -s - "$ROOT/$p" || { echo "BLOCKED: reviewed source mismatch"; exit 2; }
done
cd "$ROOT/staging/aws_lightsail"
[[ -f .env ]] || { echo "BLOCKED: original public .env missing"; exit 2; }
docker compose config --quiet
exec 9>/run/lock/sbi-public-pipeline.lock
flock -n 9 || { echo "BLOCKED: another public release in progress"; exit 2; }
NAME="$(docker compose ps -q sbi-preview)"
[[ -n "$NAME" && "$(docker inspect "$NAME" --format '{{.State.Running}}')" == true ]] || { echo "BLOCKED: public preview not running"; exit 2; }
[[ "$(docker inspect "$NAME" --format '{{index .Config.Labels "com.docker.compose.service"}}')" == "sbi-preview" ]] || { echo "BLOCKED: wrong service"; exit 2; }
[[ "$(docker inspect "$NAME" --format '{{len .Mounts}}')" == 0 ]] || { echo "BLOCKED: mounted data detected"; exit 2; }
OLD="$(docker inspect "$NAME" --format '{{.Image}}')"
TAG="$(docker inspect "$NAME" --format '{{.Config.Image}}')"
[[ "$TAG" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]{3,200}$ && "$TAG" != sha256:* ]] || { echo "BLOCKED: unsafe image tag"; exit 2; }
docker image inspect "$OLD" >/dev/null
BACKUP="sbi-public-pipeline-backup:$SHORT"
CANDIDATE="sbi-public-pipeline-candidate:$SHORT"
PROBE="sbi-public-pipeline-probe"
! docker inspect "$PROBE" >/dev/null 2>&1 || { echo "BLOCKED: probe name already exists"; exit 2; }
AUTHFILE="$(mktemp /run/sbi-public-auth.XXXXXXXX)"
docker inspect "$NAME" --format '{{json .Config.Env}}' | python3 "$ROOT/staging/aws_lightsail/preview_auth_env.py" "$AUTHFILE" || { rm -f "$AUTHFILE"; echo "BLOCKED: existing login unavailable"; exit 2; }
CHANGED=0
RELEASE_AUDIT_DIR="/var/log/sbi-public-dashboard"
install -d -o root -g root -m 0700 "$RELEASE_AUDIT_DIR"
RELEASE_AUDIT="$RELEASE_AUDIT_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$SHORT-$.json"
NEW_IMAGE=""
ROLLBACK_RESULT="not_needed"
write_receipt() {
  local outcome="$1"
  RECEIPT_PATH="$RELEASE_AUDIT" RECEIPT_STATUS="$outcome" RELEASE_SHA="$SHA" \
  RELEASE_OLD_IMAGE="$OLD" RELEASE_NEW_IMAGE="$NEW_IMAGE" RELEASE_ROLLBACK="$ROLLBACK_RESULT" \
  RELEASE_BACKUP="$BACKUP" python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, os
path=Path(os.environ["RECEIPT_PATH"])
report={
    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "target": "aws-public-preview",
    "source_sha": os.environ["RELEASE_SHA"],
    "version": "git-" + os.environ["RELEASE_SHA"][:12],
    "status": os.environ["RECEIPT_STATUS"],
    "previous_image": os.environ["RELEASE_OLD_IMAGE"],
    "new_image": os.environ["RELEASE_NEW_IMAGE"] or None,
    "rollback": os.environ["RELEASE_ROLLBACK"],
    "backup_tag": os.environ["RELEASE_BACKUP"],
    "financial_writes": False,
    "evidence_scope": "public preview host local receipt; not GitHub Actions",
}
with path.open("x", encoding="utf-8") as f:
    json.dump(report, f, sort_keys=True, indent=2)
    f.write("\\n")
path.chmod(0o600)
PY
  sha256sum "$RELEASE_AUDIT" > "$RELEASE_AUDIT.sha256"
  chmod 0600 "$RELEASE_AUDIT.sha256"
}
verify_container() {
  docker exec "$1" python -c '
import base64, json, os, urllib.request, urllib.error
token=base64.b64encode((os.environ["PREVIEW_USERNAME"]+":"+os.environ["PREVIEW_PASSWORD"]).encode()).decode()
def get(path, login=True):
    headers={"Authorization":"Basic "+token} if login else {}
    req=urllib.request.Request("http://127.0.0.1:8080"+path,headers=headers)
    try: return urllib.request.urlopen(req,timeout=20)
    except urllib.error.HTTPError as e: return e
with get("/healthz",False) as r: assert r.status==200
with get("/",False) as r: assert r.status==401
with get("/") as r: assert r.status==200 and b"All stages. One control center." in r.read(100000)
with get("/api/pipeline/status") as r:
    assert r.status==200 and json.load(r)["financial_api_connected"] is False
with get("/api/upload") as r: assert r.status==403
with get("/api/pipeline/version") as r:
    version=json.load(r)
    assert r.status==200
    assert version["source_sha"]==os.environ["SBI_SOURCE_SHA"]
    assert version["channel"]=="aws-public-preview"
'
}
finish() {
  code=$?
  trap - EXIT
  docker rm -f "$PROBE" >/dev/null 2>&1 || true
  rm -f "$AUTHFILE"
  if (( code != 0 )); then
    if (( CHANGED == 1 )); then
      echo "PUBLIC_PREVIEW_ROLLBACK=STARTED"
      ROLLBACK_RESULT="attempted"
      docker tag "$OLD" "$TAG" || true
      if docker compose up -d --no-deps --no-build --force-recreate sbi-preview &&
         [[ "$(docker inspect "$(docker compose ps -q sbi-preview)" --format '{{.Image}}')" == "$OLD" ]]; then
        ROLLBACK_RESULT="previous_image_restored"
        echo "PUBLIC_PREVIEW_ROLLBACK=PREVIOUS_IMAGE_RESTORED"
      else
        ROLLBACK_RESULT="manual_review_required"
        echo "PUBLIC_PREVIEW_ROLLBACK=MANUAL_REVIEW_REQUIRED"
      fi
    fi
    write_receipt "failure" || echo "AUDIT_RECEIPT=WRITE_FAILED"
    echo "PUBLIC_RELEASE_AUDIT=$RELEASE_AUDIT"
  fi
  exit "$code"
}
trap finish EXIT
docker tag "$OLD" "$BACKUP"
echo "ORIGINAL_PUBLIC_IMAGE_PRESERVED=YES"
docker build --pull --build-arg SBI_SOURCE_SHA="$SHA" --build-arg SBI_RELEASE_CHANNEL=aws-public-preview -t "$CANDIDATE" "$ROOT/staging/railway_public"
docker run -d --name "$PROBE" -p 127.0.0.1:18085:8080 --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 256m --env-file "$AUTHFILE" -e PORT=8080 "$CANDIDATE" >/dev/null
for i in $(seq 1 20); do
  if docker exec "$PROBE" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=2)' >/dev/null 2>&1; then break; fi
  sleep 1
done
verify_container "$PROBE" || { echo "BLOCKED: dashboard candidate failed auth/health/API gate"; exit 2; }
echo "CANDIDATE_DASHBOARD=PASS"
docker rm -f "$PROBE" >/dev/null
CHANGED=1
docker tag "$CANDIDATE" "$TAG"
docker compose up -d --no-deps --no-build --force-recreate sbi-preview
NEW="$(docker compose ps -q sbi-preview)"
[[ -n "$NEW" ]] || { echo "PUBLIC_PREVIEW_DEPLOY=FAIL"; exit 1; }
[[ "$(docker inspect "$NEW" --format '{{.Image}}')" == "$(docker image inspect "$CANDIDATE" --format '{{.Id}}')" ]] || { echo "PUBLIC_PREVIEW_IMAGE_MISMATCH"; exit 1; }
for i in $(seq 1 20); do
  if docker exec "$NEW" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=2)' >/dev/null 2>&1; then break; fi
  sleep 1
done
verify_container "$NEW"
NEW_IMAGE="$(docker inspect "$NEW" --format '{{.Image}}')"
write_receipt "success"
CHANGED=0
echo "PUBLIC_RELEASE_AUDIT=$RELEASE_AUDIT"
echo "PUBLIC_RELEASE_VERSION=git-$SHORT"
echo "PUBLIC_PIPELINE_DASHBOARD=DEPLOYED"
echo "PREVIOUS_IMAGE_BACKUP=$BACKUP"
echo "PRODUCTION_CADDY=UNMODIFIED"
echo "FINANCIAL_WRITES=DISABLED"
echo "PUBLIC_URL=https://sbi-preview.13-232-241-221.sslip.io/"
