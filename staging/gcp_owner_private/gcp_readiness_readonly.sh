#!/usr/bin/env bash
# READ ONLY: Phase 2B Cloud Run readiness. No deploy, IAM changes or traffic.
set -euo pipefail

PROJECT="${PROJECT:-meghraj-reconciliation}"
REGION="${REGION:-asia-south1}"
PROD_SERVICE="${PROD_SERVICE:-sbi-dashboard}"
STAGING_SERVICE="${STAGING_SERVICE:-sbi-owner-private-stage-v1}"

die() { echo "PHASE2B_READY=NO; BLOCKER=$1" >&2; exit 2; }
command -v gcloud >/dev/null 2>&1 || die "GCLOUD_CLI_MISSING"
[[ "$PROJECT" == "meghraj-reconciliation" ]] || die "PROJECT_NOT_APPROVED"
[[ "$REGION" == "asia-south1" ]] || die "REGION_NOT_APPROVED"
[[ "$PROD_SERVICE" != "$STAGING_SERVICE" ]] || die "SERVICE_NAME_COLLISION"
case "$STAGING_SERVICE" in
  sbi-dashboard|sbi-supervisor-backend|sbi-reconciliation-api) die "PRODUCTION_SERVICE_PROTECTED";;
esac

ACCOUNT="$(gcloud auth list --filter='status:ACTIVE' --format='value(account)' | head -n 1)"
[[ -n "$ACCOUNT" ]] || die "AUTHORIZED_GCP_IDENTITY_NOT_CONNECTED"
gcloud projects describe "$PROJECT" --format='value(projectId)' >/dev/null ||
  die "PROJECT_ACCESS_FAILED"

PROD_JSON="$(mktemp)"
STAGE_JSON="$(mktemp)"
trap 'rm -f "$PROD_JSON" "$STAGE_JSON"' EXIT
gcloud run services describe "$PROD_SERVICE" --project "$PROJECT" --region "$REGION" --format=json > "$PROD_JSON" ||
  die "PRODUCTION_BASELINE_UNAVAILABLE"
# Stage existence must be assessed, not assumed. A failure may be permissions.
if gcloud run services describe "$STAGING_SERVICE" --project "$PROJECT" --region "$REGION" --format=json > "$STAGE_JSON" 2>/dev/null; then
  STAGE_PRESENT="YES"
else
  STAGE_PRESENT="UNKNOWN_OR_NOT_FOUND"
fi
python3 - "$PROD_JSON" "$STAGE_JSON" "$STAGE_PRESENT" <<'PY'
import json,sys
prod=json.load(open(sys.argv[1]))
stage=json.load(open(sys.argv[2])) if sys.argv[3]=="YES" else {}
template=prod.get("spec",{}).get("template",{}).get("spec",{})
containers=template.get("containers") or []
status=prod.get("status") or {}
print("PHASE2B_GCP_READ_ACCESS=PASS")
print("PROD_SERVICE_NAME="+str(prod.get("metadata",{}).get("name","UNAVAILABLE")))
print("PROD_READY_REVISION="+str(status.get("latestReadyRevisionName","UNAVAILABLE")))
print("PROD_CONTAINER_IMAGE_PRESENT="+str(bool(containers and containers[0].get("image"))).upper())
print("STAGING_SERVICE_PRESENT="+sys.argv[3])
if stage:
    s=stage.get("spec",{}).get("template",{}).get("spec",{})
    print("STAGING_IDENTITY_SET="+str(bool(s.get("serviceAccountName"))).upper())
print("NEW_SOURCE_BUILT_REGISTRY_DIGEST=NOT_VERIFIED")
print("STAGING_IAM_ONLY_AND_INTERNAL_INGRESS=NOT_VERIFIED")
print("STAGING_SA_FINANCIAL_WRITE_DENIAL=NOT_VERIFIED")
print("STAGING_CLOUD_RUN_DEPLOYMENT=NOT_VERIFIED")
print("FINANCIAL_DATABASE_WRITES=0")
print("PRODUCTION_RELEASE=BLOCKED")
PY
