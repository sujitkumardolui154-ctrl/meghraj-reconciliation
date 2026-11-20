"""Read-only Firebase-authenticated report catalog from independently certified CSVs.

This is a source-backed adapter, NOT a Firestore/financial connection.
Without a private mounted, independently approved SHA256 manifest, the catalog
displays NOT_CONNECTED and every CSV remains 503. Never fabricate report
counts, snapshot versions, invoice statuses or zero-valued report data.
Every CSV has its source, headers, count, approval and SHA256 rechecked.
"""
import os
from flask import Blueprint, Response, jsonify
from aws_readonly_snapshot_reports import load_snapshot, NotCertified

readonly_reports = Blueprint("sbi_aws_readonly_reports", __name__)

KINDS = ("unpaid", "ok", "error-value", "balance-review")
LABELS = {
    "unpaid":"Unpaid Invoice Report",
    "ok":"OK Payment Value Report",
    "error-value":"Invalid Payment Value Report",
    "balance-review":"Balance Review Report",
}


def _ready(kind):
    try:
        catalog, data = load_snapshot(kind)
        report = catalog["reports"][kind]
        return {
            "status":"AVAILABLE",
            "rows":report["rows"],
            "columns":report["columns"],
            "classification":report["classification"],
            "url":"/api/reporting/v2/" + kind + ".csv",
            "source_sha256":catalog["source_sha256"],
            "approval_receipt_id":catalog["approval_receipt_id"],
        }, data
    except NotCertified as exc:
        return {"status":"NOT_CERTIFIED","reason":str(exc)}, None


@readonly_reports.get("/api/reporting/v2")
def report_catalog():
    """A readable status, even when finance data has not been connected."""
    configured = bool(
        os.environ.get("SBI_AWS_REPORT_SNAPSHOT_DIR")
        and os.environ.get("SBI_AWS_REPORT_MANIFEST_SHA256")
    )
    if not configured:
        return jsonify(
            version="aws-source-snapshot-v1",
            source_status="NOT_CONNECTED",
            status_reason="REPORT_DATA_NOT_CONNECTED",
            summary=(
                "The AWS financial report dataset has not been connected. "
                "Connect an independently approved private 53-column invoice "
                "snapshot to enable downloads. Payment evidence uploads do "
                "not automatically create invoice reports."
            ),
            reports={k:{"status":"NOT_CONNECTED"} for k in KINDS},
            reconciliation_executed=False,
            financial_writes=False,
            financial_data_connected=False,
        )
    reports={k:_ready(k)[0] for k in KINDS}
    ready=sum(x["status"]=="AVAILABLE" for x in reports.values())
    return jsonify(
        version="aws-source-snapshot-v1",
        source_status=("READY" if ready==len(KINDS) else
                       "PARTIAL_CERTIFIED" if ready else "NOT_CERTIFIED"),
        status_reason=("ALL_REPORTS_CERTIFIED" if ready==len(KINDS)
                       else "REPORT_APPROVAL_OR_SOURCE_VERIFICATION_REQUIRED"),
        summary=(
            "Source-only approved CSV exports. Counts are from verified "
            "private 53-column files, not a live financial database."
        ),
        reports=reports,
        reconciliation_executed=False,
        financial_writes=False,
        financial_data_connected=False,
    )


@readonly_reports.get("/api/reporting/v2/<kind>.csv")
def source_report_csv(kind):
    if kind not in KINDS:
        return jsonify(error="REPORT_NOT_APPROVED",
                       financial_writes=False),404
    details,payload=_ready(kind)
    if details["status"] != "AVAILABLE" or payload is None:
        return jsonify(
            error="Report source is not independently certified",
            status="NOT_CERTIFIED",
            reason=details.get("reason","REPORT_DATA_NOT_CONNECTED"),
            financial_writes=False,
        ),503
    response=Response(payload,content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"]=(
        'attachment; filename="sbi-'+kind+'-approved-source.csv"'
    )
    response.headers["X-Report-Rows"]=str(details["rows"])
    response.headers["X-Report-Classification"]="SOURCE_REFERENCE_ONLY"
    response.headers["X-Report-Approval"]=details["approval_receipt_id"]
    response.headers["Cache-Control"]="private, no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response
