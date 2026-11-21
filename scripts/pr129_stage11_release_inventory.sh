#!/usr/bin/env bash
# PR129 Stage 11 — read-only release candidate inventory.
# Checks whether the WORKING preview is also baked into an immutable Docker image.
# No deployments, no image builds, no container restart or mutation,
# no Firebase/Firestore queries, no financial writes and no secrets printed.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
cd "$REPO"

echo '=== STAGE 11 — SBI BULK REPORT RELEASE INVENTORY ==='
test "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121 || {
    echo "STOP_WRONG_GIT_BRANCH"; exit 1;
}
test -z "$(git status --porcelain --untracked-files=no)" || {
    echo "STOP_TRACKED_WORKTREE_CHANGES"; exit 1;
}
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true || {
    echo "STOP_PREVIEW_CONTAINER_NOT_RUNNING"; exit 1;
}
test "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" || {
    echo "STOP_WRONG_PREVIEW_NETWORK"; exit 1;
}

echo "GIT_COMMIT=$(git rev-parse HEAD)"
echo "PREVIEW_IMAGE_ID=$(sudo docker inspect "$C" --format '{{.Image}}')"
echo "PREVIEW_IMAGE_REFERENCE=$(sudo docker inspect "$C" --format '{{.Config.Image}}')"
echo "PREVIEW_RESTART_POLICY=$(sudo docker inspect "$C" --format '{{.HostConfig.RestartPolicy.Name}}')"

# Verified deployed code must equal the branch before identifying provenance.
echo '=== VERIFIED PREVIEW SOURCE ==='
FILES="bulk_reports.py bulk_report_excel.py aws_verified_invoice_lookup.py bulk_report_selection.py invoice_number_selection.py invoice_source_schema.py sbi_report_access.py"
for file in $FILES; do
  localfile="dashboard_source/$file"
  test -f "$localfile" || { echo "STOP_REPO_FILE_MISSING=$file"; exit 1; }
  src="$(sha256sum "$localfile" | awk '{print $1}')"
  runtime="$(sudo docker exec "$C" sha256sum "/app/$file" | awk '{print $1}')"
  if [ "$src" != "$runtime" ]; then
    echo "STOP_SOURCE_MISMATCH=$file"
    exit 1
  fi
  echo "SOURCE_PARITY=$file:PASS"
done

# docker diff is read-only. A changed/added application file in the container
# writable layer is NOT reliably restored by re-creating from its image.
# Use exact app filenames, not secrets or source content.
echo '=== CONTAINER WRITABLE-LAYER PROVENANCE ==='
DIFF="$(sudo docker diff "$C")"
runtime_changes=0
for file in $FILES; do
  if printf '%s\n' "$DIFF" | grep -Eq "^[AC] /app/$file$"; then
    echo "CONTAINER_WRITABLE_LAYER_CHANGE=$file"
    runtime_changes=$((runtime_changes+1))
  fi
done
if printf '%s\n' "$DIFF" | grep -Eq '^[AC] /app/pr129_aws_invoice_lookup\.enabled$'; then
  echo "CONTAINER_WRITABLE_LAYER_CHANGE=pr129_aws_invoice_lookup.enabled"
  runtime_changes=$((runtime_changes+1))
fi
echo "RUNTIME_ONLY_ARTIFACT_COUNT=$runtime_changes"

# Print count and destinations only, never host paths/source or secrets.
sudo docker inspect "$C" --format \
  'MOUNT_DESTINATIONS={{range .Mounts}}{{.Destination}};{{end}}'
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from pathlib import Path
import os
from app import app
flag=Path("/app/pr129_aws_invoice_lookup.enabled")
print("AWS_DIRECT_LOOKUP_FLAG_PRESENT="+str(flag.is_file()).upper())
print("AWS_DIRECT_LOOKUP_FLAG_VALID="+str(
    flag.is_file() and flag.read_text() == "AWS_FIRESTORE_READONLY_PR129\n"
).upper())
print("EXTERNAL_LOOKUP_BACKEND_CONFIGURED="+str(bool(os.environ.get("INVOICE_LOOKUP_BACKEND"))).upper())
routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
print("SELECTED_INVOICE_REPORT_ROUTE="+str(
    "POST" in routes.get("/api/bulk-report/select-invoices-excel",set())).upper())
PY

if [ "$runtime_changes" -gt 0 ]; then
  echo 'IMMUTABLE_RELEASE_ARTIFACT=NOT_PROVEN'
  echo 'NEXT_GATE=BUILD_REPRODUCIBLE_IMAGE_WITH_CODE_AND_LOOKUP_CONFIGURATION'
else
  echo 'IMMUTABLE_RELEASE_ARTIFACT=IMAGE_CONTENT_STILL_REQUIRES_BUILD_ATTESTATION'
  echo 'NEXT_GATE=VERIFY_IMAGE_BUILD_AND_ROLLBACK_PIN'
fi
echo 'STAGE11_RELEASE_INVENTORY=COMPLETE'
echo 'PRODUCTION_DEPLOYMENT=NOT_PERFORMED'
echo 'FIRESTORE_READS_AND_WRITES_BY_THIS_CHECK=NONE'
echo 'FINANCIAL_WRITES=NONE'
