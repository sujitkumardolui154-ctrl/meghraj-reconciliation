#!/usr/bin/env bash
# Read-only coverage audit for existing *approved* 53-column CSV exports.
# Does not bypass Firebase: requires the verified MASTER dashboard report-viewer
# entitlement before invoking the existing local certified source reader.
# Reports metadata only; never prints invoice data, credentials or source paths.
set -Eeuo pipefail
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true
test "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET"

echo '=== PR129 AWS APPROVED REPORT COVERAGE ==='
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from dashboard_sessions import MASTER_UID, MASTER_EMAIL, is_master, firebase_app
from firebase_admin import auth
from sbi_report_access import can_view_report

try:
    user = auth.get_user(MASTER_UID, app=firebase_app())
    authorized = (
        user.uid == MASTER_UID
        and (user.email or "").casefold() == MASTER_EMAIL.casefold()
        and is_master(user)
        and can_view_report(user, {"uid": user.uid})
    )
except Exception as exc:
    print("MASTER_IDENTITY_VERIFICATION=UNAVAILABLE")
    print("ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(3)

if not authorized:
    print("STOP: EXPLICIT_REPORT_VIEWER_PERMISSION_REQUIRED")
    raise SystemExit(4)
print("MASTER_REPORT_VIEWER_PERMISSION=VERIFIED")

try:
    from app import app
    # Resolve the reader from the LIVE registered handler to avoid relying on
    # a guessed private helper name. Historical source uses _ready(kind).
    route = next((r for r in app.url_map.iter_rules()
                  if str(r) == "/api/reporting/v2/<kind>.csv"), None)
    if route is None:
        raise RuntimeError("CERTIFIED_REPORT_ROUTE_NOT_REGISTERED")
    handler = app.view_functions[route.endpoint]
    scope = handler.__globals__
    reader = scope.get("_ready")
    kinds = scope.get("KINDS")
    if not callable(reader):
        print("READER_READY_PRESENT=" + str(callable(scope.get("_ready"))).upper())
        print("READER_READ_PRESENT=" + str(callable(scope.get("_read"))).upper())
        raise RuntimeError("CERTIFIED_SOURCE_READER_NOT_IDENTIFIED")
    if not isinstance(kinds, (tuple, list, dict, set, frozenset)):
        raise RuntimeError("CERTIFIED_KINDS_NOT_IDENTIFIED")
    print("CERTIFIED_REPORT_INTERFACE=READY")
    print("REPORT_CATEGORIES=" + ",".join(sorted(str(k) for k in kinds)))
except Exception as exc:
    print("CERTIFIED_REPORT_INTERFACE=UNAVAILABLE")
    print("INTERFACE_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(5)

usable = 0
total = 0
for kind in ("all-invoices", "unpaid", "ok", "error-value", "balance-review"):
    if kind not in kinds:
        print("REPORT=" + kind + " STATUS=NOT_CONFIGURED")
        continue
    try:
        details, payload = reader(kind)
        if not isinstance(details, dict):
            raise RuntimeError("Invalid report source metadata")
        status = str(details.get("status", "UNKNOWN"))
        rows = details.get("rows")
        receipt = bool(details.get("approval_receipt_id"))
        data = isinstance(payload, bytes) and bool(payload)
        print("REPORT=" + kind
              + " STATUS=" + status
              + " ROWS=" + (str(rows) if isinstance(rows, int) else "UNKNOWN")
              + " APPROVAL_RECEIPT_PRESENT=" + str(receipt).upper()
              + " VERIFIED_BYTES_PRESENT=" + str(data).upper())
        total += 1
        if status == "AVAILABLE" and receipt and data:
            usable += 1
    except Exception as exc:
        print("REPORT=" + kind + " STATUS=SOURCE_ERROR"
              + " ERROR_TYPE=" + type(exc).__name__)
print("APPROVED_REPORTS_AVAILABLE=" + str(usable) + "/" + str(total))
print("SOURCE_SCOPE=APPROVED_PRIVATE_CSV_EXPORTS_NOT_LIVE_FINANCIAL_DATABASE")
print("INVOICE_NUMBERS_PRINTED=NONE")
print("SOURCE_FILES_MODIFIED=NONE")
print("FINANCIAL_DATABASE_WRITES=NONE")
print("PR129_AWS_REPORT_COVERAGE_INSPECTION=COMPLETE")
PY
