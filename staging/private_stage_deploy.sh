#!/usr/bin/env bash
# Private, isolated Cloud Run staging from a currently deployed image.
# Creates a DIFFERENT service. Never updates production service traffic or financial data.
set -euo pipefail
PROJECT="${PROJECT:-meghraj-reconciliation}"
REGION="${REGION:-asia-south1}"
SOURCE_SERVICE="${SOURCE_SERVICE:-sbi-dashboard}"
STAGE_SERVICE="${STAGE_SERVICE:-sbi-dashboard-private-stage}"
STAGE_SA="${STAGE_SA:-}"
APPLY="${APPLY:-0}"

die() { echo "BLOCKED: $*" >&2; exit 1; }
command -v gcloud >/dev/null || die "gcloud is required"
[[ "$SOURCE_SERVICE" != "$STAGE_SERVICE" ]] || die "Staging service must be different from production"
[[ "$STAGE_SA" == *"@"* ]] || die "Set STAGE_SA to dedicated least-privilege service account; must not be production account"
gcloud iam service-accounts describe "$STAGE_SA" --project "$PROJECT" >/dev/null ||
  die "Dedicated staging service account does not exist"
SOURCE_JSON="$(mktemp)"
trap 'rm -f "$SOURCE_JSON"' EXIT
gcloud run services describe "$SOURCE_SERVICE" --project "$PROJECT" --region "$REGION" --format=json > "$SOURCE_JSON"
IMAGE="$(python3 - "$SOURCE_JSON" <<'PY'
import json,sys
data=json.load(open(sys.argv[1]))
spec=data.get("spec",{}).get("template",{}).get("spec",{})
containers=spec.get("containers",[])
if len(containers)!=1 or not containers[0].get("image"):
    raise SystemExit("BLOCKED: unable to identify one source container image")
print(containers[0]["image"])
PY
)"
PROD_SA="$(python3 - "$SOURCE_JSON" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get("spec",{}).get("template",{}).get("spec",{}).get("serviceAccountName",""))
PY
)"
[[ "$STAGE_SA" != "$PROD_SA" ]] || die "Staging and production service accounts must differ"
if gcloud run services describe "$STAGE_SERVICE" --project "$PROJECT" --region "$REGION" >/dev/null 2>&1; then
  die "Stage service already exists: refusing to mutate it"
fi
echo "=== PRIVATE STAGING DEPLOYMENT PLAN ==="
echo "PROJECT=$PROJECT"
echo "REGION=$REGION"
echo "SOURCE_SERVICE=$SOURCE_SERVICE"
echo "STAGE_SERVICE=$STAGE_SERVICE"
echo "SOURCE_IMAGE=$IMAGE"
echo "STAGE_SERVICE_ACCOUNT=$STAGE_SA"
echo "FINANCIAL_RELEASE_STATUS=REVIEW_REQUIRED"
echo "FINANCIAL_DATABASE_WRITES=DISALLOWED_BY_DESIGN"
echo "PRODUCTION_TRAFFIC_CHANGES=0"
echo "STAGING_VISIBILITY=IAM_AUTHENTICATED_ONLY"
if [[ "$APPLY" != 1 ]]; then
 echo "DRY_RUN=TRUE"
 echo "NEXT=Review staging account permissions and rerun with APPLY=1"
 exit 0
fi
# This deploys a separate service, not a revision of the existing production service.
# Stage SA must have NO financial database write access; this script does not assign IAM roles.
gcloud run deploy "$STAGE_SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE" --service-account "$STAGE_SA" \
  --no-allow-unauthenticated --ingress all \
  --set-env-vars "STAGING_RELEASE_ALLOWED=true,FINANCIAL_WRITES_DISABLED=true,RECONCILIATION_EXECUTION_ENABLED=false" \
  --quiet
gcloud run services describe "$STAGE_SERVICE" --project "$PROJECT" --region "$REGION" \
  --format="table(metadata.name,status.url,spec.template.spec.serviceAccountName)"
echo "STAGE_DEPLOYED=TRUE"
echo "FINANCIAL_RELEASE_STATUS=REVIEW_REQUIRED"
echo "PRODUCTION_TRAFFIC_CHANGES=0"
