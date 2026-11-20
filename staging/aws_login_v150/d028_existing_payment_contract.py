"""D-028 existing Payment Evidence UI/API source contract — no live access.

This is a source-code compatibility check for the previously developed upload
screen in PR #119. It does not scan old finance files, calculate payment values,
start Flask, make HTTP requests, open SQLite, write a receipt or deploy AWS.

Source analysis is NOT proof that the same routes are live in AWS.
"""
import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HEADERS = ('"Description"', '"SOL ID"', '"Credit Amount"')
ROUTES = {
    ("get", "/api/payment-evidence/template"),
    ("post", "/api/payment-evidence/upload"),
    ("get", "/api/payment-evidence/uploads"),
    ("get", "/api/payment-evidence/uploads/<receipt_id>"),
}
UI_MARKERS = {
    'id="dil-db-payments-button"',
    'id="dil-payment-upload-form"',
    'id="dil-payment-evidence-file"',
    'id="dil-payment-preview"',
    'id="dil-payment-reconcile"',
    'id="dil-payment-receipt-list"',
}
REQUIRED_INTEGRATION_REFERENCES = (
    "/api/payment-evidence/template",
    "/api/payment-evidence/upload",
    "/api/payment-evidence/uploads",
    "Description | SOL ID | Credit Amount",
    "X-DIL-CSRF",
)


class ExistingPaymentEvidenceContractBlocked(ValueError):
    pass


def _route_methods(source):
    ast_tree = ast.parse(source)
    seen = set()
    for function in ast.walk(ast_tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in function.decorator_list:
            if not (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "payment_evidence"):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            seen.add((decorator.func.attr, decorator.args[0].value))
    return seen


def assess_existing_interface(html_source, app_source, upload_source):
    """Check exact existing UI and route wiring at SOURCE level only."""
    blockers = []
    for element in UI_MARKERS:
        if html_source.count(element) != 1:
            blockers.append("MISSING_OR_DUPLICATE_EXISTING_UI_ID")
            break
    for reference in REQUIRED_INTEGRATION_REFERENCES:
        if reference not in html_source:
            blockers.append("UI_ENDPOINT_OR_HEADER_CONTRACT_MISMATCH")
            break
    if 'id="dil-payment-reconcile" disabled' not in html_source:
        blockers.append("FINANCIAL_RUN_CONTROL_MUST_REMAIN_DISABLED")
    found = _route_methods(upload_source)
    if not ROUTES <= found:
        blockers.append("PAYMENT_EVIDENCE_HANDLER_ROUTE_MISMATCH")
    if 'HEADERS = ("Description", "SOL ID", "Credit Amount")' not in upload_source:
        blockers.append("FIXED_3_COLUMN_TEMPLATE_REQUIRED")
    if "app.register_blueprint(payment_evidence)" not in app_source:
        blockers.append("EXISTING_APP_BLUEPRINT_NOT_REGISTERED")
    if "install_sessions(app)" not in app_source:
        blockers.append("SESSION_HOOK_NOT_PRESENT_IN_SOURCE")
    if "csrf_valid()" not in upload_source:
        blockers.append("SOURCE_CSRF_GUARD_NOT_PRESENT")
    if "g.dil_user.uid" not in upload_source:
        blockers.append("OWNER_RECEIPT_SCOPING_NOT_PRESENT")
    if ("SBI_PAYMENT_EVIDENCE_DIR" not in upload_source
            or 'receipts.sqlite3' not in upload_source):
        blockers.append("NONFINANCIAL_STAGING_RECEIPT_STORE_MISSING")
    if ("def disabled_financial_api(" not in app_source
            or '"financial_execution_enabled=False' not in app_source):
        # Static assertions are necessary but not sufficient for runtime denial.
        blockers.append("FINANCIAL_API_DENY_CONTRACT_MISSING")
    if blockers:
        raise ExistingPaymentEvidenceContractBlocked(",".join(sorted(set(blockers))))
    return {
        "result": "SOURCE_COMPATIBILITY_ONLY_PASS",
        "existing_payment_reconciliation_ui": "REUSE_NOT_REBUILD",
        "fixed_payment_upload_headers": ["Description", "SOL ID", "Credit Amount"],
        "existing_routes_found": len(ROUTES),
        "existing_UI_duplicate_created": False,
        "legacy_PAYMNENT_input_schema": "NOT_USED_BY_THIS_3_COLUMN_UI",
        "d027_12_column_synthetic_adapter": "NOT_CONNECTED_INCOMPATIBLE",
        "real_firebase_login": "NOT_TESTED_BY_SOURCE_CHECK",
        "aws_route": "NOT_VERIFIED",
        "historical_financial_records": "NOT_READ",
        "reconciliation_execution": "NOT_PERFORMED",
        "financial_writes": "NOT_PERFORMED",
        "production_traffic": "UNCHANGED",
        "owner_logic_only_policy": "PRESERVED",
    }


def source_check(root=REPO):
    root = Path(root)
    return assess_existing_interface(
        (root / "dashboard_source/index.html").read_text(encoding="utf-8"),
        (root / "staging/aws_login_v150/app.py").read_text(encoding="utf-8"),
        (root / "staging/aws_login_v150/payment_evidence_upload.py").read_text(
            encoding="utf-8"),
    )


if __name__ == "__main__":
    print(json.dumps(source_check(), sort_keys=True))
