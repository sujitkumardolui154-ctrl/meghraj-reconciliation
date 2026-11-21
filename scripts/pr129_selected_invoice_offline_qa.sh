#!/usr/bin/env bash
# Offline-only QA of uploaded random invoice-number selection.
# No cloud credentials, no network, no financial writes, no public deployment.
set -Eeuo pipefail
REPO='/home/ubuntu/sbi-bulk-report-integration/repo'
cd "$REPO"
test "$(git branch --show-current)" = 'ui/bulk-report-reports-tab-20261121'

echo '=== RANDOM INVOICE NUMBER BULK REPORT — OFFLINE QA ==='
IMAGE="$(sudo docker inspect sbi-bulk-reports-v1-stage --format '{{.Image}}')"
test -n "$IMAGE"
sudo docker run --rm \
  --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/code:/backend \
  -v "$REPO/dashboard_source:/code:ro" \
  -v "$REPO/backend_source:/backend:ro" \
  -w /code "$IMAGE" \
  python -m unittest -v \
    test_invoice_number_selection \
    test_bulk_report_selection \
    test_bulk_report_combined_excel \
    test_invoice_selection_report

echo 'SELECTED_INVOICE_OFFLINE_QA=PASS'
echo 'DATABASE_LOOKUP=NOT_TESTED'
echo 'AWS_PUBLIC_DEPLOYMENT=NOT_PERFORMED'
echo 'FINANCIAL_WRITES=NONE'
