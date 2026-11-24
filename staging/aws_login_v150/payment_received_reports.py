"""R31 source-only SOL-wise payment received report and future-engine feed contract.

Authenticated AWS dashboard Blueprint; no financial allocation or settlement.
No need for a Finance certificate to deploy this calculation/report feature.
"""
from __future__ import annotations
from contextlib import closing
from flask import Blueprint, Response, g, jsonify, request
from payment_evidence_upload import _connection,_store
from payment_received_ledger import (
    aggregate_sol_payment_report, report_csv_bytes, source_payment_rows,
)

payment_received_reports=Blueprint("sbi_payment_received_reports",__name__)


def _read():
    owner=str(g.dil_user.uid)
    base=_store()
    with closing(_connection(base)) as conn:
        return aggregate_sol_payment_report(conn,owner)


@payment_received_reports.get("/api/payment-received/sol-report")
def sol_payment_report():
    try:
        result=_read()
    except Exception:
        return jsonify(error="Private payment received report unavailable",
                       financial_writes=False,
                       reconciliation_executed=False),503
    return jsonify(
        report=result["report"],
        source=result["source"],
        sol_groups=result["sol_groups"],
        totals=result["totals"],
        reconciliation_executed=result["reconciliation_executed"],
        master_v251_matrix_v239_connected=False,
        matched_requires_independent_engine_evidence=True,
        new_invoice_upload_can_reuse_saved_payment_inputs=True,
        automatic_invoice_matching_enabled=False,
        formal_financial_certificate_required_for_report_deploy=False,
        financial_writes=False,
    )


@payment_received_reports.get("/api/payment-received/sol-report.csv")
def export_sol_payment_csv():
    try:
        data=report_csv_bytes(_read(),detail=False)
    except Exception:
        return jsonify(error="Private payment received CSV unavailable"),503
    return Response(
        data,mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":'attachment; filename="SBI_SOL_WISE_PAYMENT_TALLY_REPORT.csv"',
            "Cache-Control":"private, no-store",
            "X-Reconciliation-Engine":"NOT_CONNECTED",
        },
    )


@payment_received_reports.get("/api/payment-received/payment-details.csv")
def export_payment_details_csv():
    try:
        data=report_csv_bytes(_read(),detail=True)
    except Exception:
        return jsonify(error="Private payment received details unavailable"),503
    return Response(
        data,mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":'attachment; filename="SBI_PAYMENT_RECEIVED_ROW_DETAILS.csv"',
            "Cache-Control":"private, no-store",
            "X-Reconciliation-Engine":"NOT_CONNECTED",
        },
    )
