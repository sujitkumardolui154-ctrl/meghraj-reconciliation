#!/usr/bin/env bash
# Run ONLY in authenticated GOOGLE CLOUD SHELL after cloning PR129 branch.
# Deploys a NEW authenticated read-only invoice-lookup staging service.
# NO production service revision, public app, database rows or finance writes.
# Intentionally does NOT grant Firestore read access until route IAM QA passes.
set -Eeuo pipefail

PROJECT=meghraj-reconciliation
REGION=asia-south1
SERVICE=sbi-invoice-lookup-stage
READER=sbi-invoice-lookup-reader
CALLER='firebase-adminsdk-fbsvc@meghraj-reconciliation.iam.gserviceaccount.com'
READER_EMAIL="$READER@$PROJECT.iam.gserviceaccount.com"

command -v gcloud >/dev/null || { echo 'STOP: RUN_IN_GCLOUD_SHELL'; exit 1; }
[ "$(git branch --show-current)" = 'ui/bulk-report-reports-tab-20261121' ] || {
  echo 'STOP: WRONG_GITHUB_BRANCH'; exit 1;
}
[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo 'STOP: UNCOMMITTED_SOURCE_CHANGES'; exit 1;
}
[ "$(gcloud config get-value project 2>/dev/null)" = "$PROJECT" ] || {
  echo 'STOP: WRONG_GCP_PROJECT'; exit 1;
}
if gcloud run services describe "$SERVICE" --region "$REGION" \
    --project "$PROJECT" --format="value(metadata.name)" >/dev/null 2>&1; then
  echo 'STOP: STAGE_SERVICE_ALREADY_EXISTS_DO_NOT_REPLACE'
  exit 1
fi
echo 'TARGET_SERVICE=NEW_ISOLATED_STAGE_ONLY'
echo 'EXISTING_SUPERVISOR_BACKEND=UNMODIFIED'

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
bash scripts/pr129_package_isolated_lookup_stage.sh "$WORK/source.tar.gz"
mkdir "$WORK/src"
tar -xzf "$WORK/source.tar.gz" -C "$WORK/src"
test -s "$WORK/src/main.py"
test -s "$WORK/src/invoice_import_contract.json"
grep -q 'def invoice_lookup_stage(request)' "$WORK/src/main.py"
grep -q '^functions-framework' "$WORK/src/requirements.txt"

if ! gcloud iam service-accounts describe "$READER_EMAIL" \
    --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$READER" \
    --display-name="PR129 isolated invoice lookup reader" \
    --project="$PROJECT"
fi
# No project-wide datastore.viewer granted automatically.
echo 'FIRESTORE_ACCESS_ROLE=NOT_GRANTED_IN_THIS_STEP'

cd "$WORK/src"
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source=. \
  --function=invoice_lookup_stage \
  --base-image=python312 \
  --service-account="$READER_EMAIL" \
  --no-allow-unauthenticated \
  --invoker-iam-check \
  --ingress=all \
  --max-instances=1 \
  --min-instances=0 \
  --concurrency=1 \
  --memory=512Mi \
  --timeout=300s \
  --quiet

URL="$(gcloud run services describe "$SERVICE" \
  --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
case "$URL" in
  https://*.run.app) ;;
  *) echo 'STOP: UNEXPECTED_STAGE_URL'; exit 1 ;;
esac

# Verify second-layer caller identity, independent of Cloud Run IAM.
gcloud run services update "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --update-env-vars="INVOICE_LOOKUP_AUDIENCE=$URL,INVOICE_LOOKUP_ALLOWED_CALLERS=$CALLER" \
  --quiet
gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:$CALLER" \
  --role="roles/run.invoker" \
  --quiet

echo "NEW_STAGING_URL=$URL"
gcloud run services get-iam-policy "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --format='yaml(bindings)'
echo 'STAGING_SERVICE_DEPLOYMENT=COMPLETE'
echo 'EXISTING_CLOUD_RUN_BACKEND=UNCHANGED'
echo 'EXISTING_AWS_PUBLIC_APPLICATION=UNCHANGED'
echo 'FIRESTORE_READ_ROLE=NOT_GRANTED_BY_SCRIPT'
echo 'LOOKUP_DATABASE_ROWS=NOT_READ'
echo 'FINANCIAL_WRITES=NONE'
