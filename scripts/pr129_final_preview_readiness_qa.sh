#!/usr/bin/env bash
# PR129 final preview-only, READ-ONLY readiness check for SBI Bulk Reports.
# No deploy, docker restart, IAM change, Firestore financial read/write,
# real invoice content, Firebase mutation, or Caddy change.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
CONTAINER=sbi-bulk-report-pr129-https-preview
NETWORK=sbi_pr129_preview_net
HOST=pr129.13-232-241-221.sslip.io
cd "$REPO"

echo '=== PR129 SELECTED INVOICE BULK REPORT — FINAL PREVIEW QA ==='
test "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121 || {
  echo 'FAIL_WRONG_BRANCH'; exit 1;
}
test -z "$(git status --porcelain --untracked-files=no)" || {
  echo 'FAIL_TRACKED_WORKTREE_DIRTY'; exit 1;
}
test "$(sudo docker inspect "$CONTAINER" --format '{{.State.Running}}')" = true || {
  echo 'FAIL_PREVIEW_NOT_RUNNING'; exit 1;
}
test "$(sudo docker inspect "$CONTAINER" --format '{{.HostConfig.NetworkMode}}')" = "$NETWORK" || {
  echo 'FAIL_UNEXPECTED_CONTAINER_NETWORK'; exit 1;
}

echo '=== RUNNING PREVIEW SOURCE HASH PARITY ==='
for file in bulk_reports.py bulk_report_excel.py aws_verified_invoice_lookup.py; do
  expected="$(sha256sum "dashboard_source/$file" | awk '{print $1}')"
  actual="$(sudo docker exec "$CONTAINER" sha256sum "/app/$file" | awk '{print $1}')"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL_RUNNING_PREVIEW_HASH_MISMATCH=$file"
    echo 'DO_NOT_PROMOTE=YES'
    exit 1
  fi
  echo "PREVIEW_SOURCE_HASH_MATCH=$file"
done

echo '=== OFFLINE SYNTHETIC REGRESSION QA ==='
IMAGE="$(sudo docker inspect sbi-bulk-reports-v1-stage --format '{{.Image}}')"
test -n "$IMAGE" || { echo 'FAIL_STAGING_TEST_IMAGE_MISSING'; exit 1; }
sudo docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/code:/backend \
  -v "$REPO/dashboard_source:/code:ro" \
  -v "$REPO/backend_source:/backend:ro" \
  -w /code "$IMAGE" \
  python -B -m unittest -v \
    test_invoice_number_selection \
    test_bulk_report_selection \
    test_bulk_report_combined_excel \
    test_aws_verified_invoice_lookup \
    test_invoice_selection_report

echo 'OFFLINE_SELECTED_INVOICE_REGRESSION_QA=PASS'
echo '=== EXISTING PREVIEW ROUTE, AUTH, AND EXPORT CONTRACT QA ==='
sudo docker exec -i -w /app "$CONTAINER" python -B - <<'PY'
from pathlib import Path
from types import SimpleNamespace
from app import app
import bulk_report_excel as exp
from sbi_report_access import can_view_report

ui = Path("/app/index.html").read_text(encoding="utf-8")
routes = {str(r): set(r.methods) for r in app.url_map.iter_rules()}
expected_routes = (
    "/api/bulk-report/select-invoices-excel",
    "/api/bulk-report/generate-excel",
)
for path in expected_routes:
    assert "POST" in routes.get(path, set()), "Missing authenticated report POST route"
assert "GET" in routes.get("/api/bulk-report/status", set())
for marker in ('id="bulk-selected-form"', 'id="bulk-report-form"',
               'id="dil-imports"', 'id="dil-tower-panel"'):
    assert marker in ui, "Existing dashboard feature missing"

marker = Path("/app/pr129_aws_invoice_lookup.enabled")
assert marker.is_file() and marker.read_text(encoding="utf-8") == "AWS_FIRESTORE_READONLY_PR129\n"
assert len(exp.AMOUNT_COLUMN_INDEXES) >= 10
assert 12 not in exp.AMOUNT_COLUMN_INDEXES
assert 6 not in exp.AMOUNT_COLUMN_INDEXES
assert exp.DATE_COLUMN_FORMATS == {
    4: "mmmm yyyy", 5: "dd/mm/yyyy", 21: "dd/mm/yyyy",
    23: "dd/mm/yyyy", 36: "dd/mm/yyyy",
}
assert exp._excel_money("2.4299999999999997") == 2.43
assert exp._excel_money("43.739999999999995") == 43.74
assert exp._excel_money("CREDIT NOTE") is None
assert exp._excel_date("2023-10-17T00:00:00").strftime("%d/%m/%Y") == "17/10/2023"
assert exp._excel_date("Mar-May 2026") is None

# Synthetic permission test, not a Firebase mutation or an identity spoof.
user = SimpleNamespace(
    uid="synthetic-check-only", disabled=False,
    custom_claims={"dil_dashboard": True, "sbi_report_viewer": False},
)
identity = {"uid": "synthetic-check-only"}
assert not can_view_report(user, identity)
user.custom_claims["sbi_report_viewer"] = True
assert can_view_report(user, identity)
user.disabled = True
assert not can_view_report(user, identity)

print("RUNNING_PREVIEW_REPORT_ROUTES=PASS")
print("RUNNING_PREVIEW_EXISTING_TABS=PASS")
print("RUNNING_PREVIEW_AWS_LOOKUP_MARKER=PASS")
print("RUNNING_PREVIEW_MONEY_AND_DATE_CONTRACT=PASS")
print("RUNNING_PREVIEW_REPORT_VIEWER_AUTH_GUARD=PASS")
print("DATABASE_RECORDS_READ_BY_THIS_QA=NONE")
PY

echo '=== ANONYMOUS HTTPS ACCESS MUST REMAIN DENIED ==='
login="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
  -sS --max-time 10 -o /dev/null -w '%{http_code}' \
  "https://$HOST/login")"
test "$login" = 200 || { echo "FAIL_LOGIN_HTTP=$login"; exit 1; }
for route in /auth/me /api/bulk-report/status /api/bulk-report/select-invoices-excel; do
  status="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    "https://$HOST$route")"
  case "$status" in
    401|403) echo "ANONYMOUS_ROUTE_DENIED=$route HTTP=$status" ;;
    *) echo "FAIL_ANONYMOUS_ROUTE_ACCESS=$route HTTP=$status"; exit 1 ;;
  esac
done

echo 'PR129_FINAL_PREVIEW_READONLY_QA=PASS'
echo 'REPORT_EXPORT_MONEY_AND_DATE_QA=PASS'
echo 'INVOICE_MATCH_AND_DUPLICATE_QA=PASS'
echo 'PREVIEW_SOURCE_PARITY=PASS'
echo 'EXISTING_REPORT_TABS=PASS'
echo 'ANONYMOUS_REPORT_ACCESS=DENIED'
echo 'REAL_INVOICE_UPLOAD=PREVIOUSLY_USER_CONFIRMED_NOT_REPEATED_BY_QA'
echo 'PRODUCTION_RELEASE=NOT_APPROVED'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'AWS_PRODUCTION_SERVICES=UNCHANGED'
