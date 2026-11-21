"""Dedicated PR129 read-only invoice lookup Cloud Run function.

Its sole data endpoint is POST /reports/invoice-selection. No import, apply,
reconciliation, database update or other supervisor endpoints are mounted.
Cloud Run IAM remains mandatory; invoice_selection_report additionally verifies
the allow-listed caller ID token.
"""
import functions_framework
from flask import jsonify


@functions_framework.http
def invoice_lookup_stage(request):
    path = request.path.rstrip("/") or "/"
    if path in ("/", "/health"):
        if request.method != "GET":
            return jsonify(error="Method not allowed"), 405
        response = jsonify(
            service="sbi-invoice-lookup-stage",
            status="RUNNING",
            financial_execution_enabled=False,
            reconciliation_executed=False,
            financial_writes=False,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    if path == "/reports/invoice-selection":
        from invoice_selection_report import handle_invoice_selection
        return handle_invoice_selection(request)
    return jsonify(error="Not found"), 404
