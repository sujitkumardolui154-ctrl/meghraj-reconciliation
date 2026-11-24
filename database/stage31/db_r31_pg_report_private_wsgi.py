"""R31 central PostgreSQL report route overlay for PRIVATE Firebase staging.

Existing AWS login application's real dashboard_sessions.install_sessions()
remains the sole cookie revocation and auth authority. This overlay replaces
ONLY the three existing R31 payment-report handlers in an isolated stage.
It never installs unauthenticated routes, changes Caddy or writes a table.
No automatic source uploads or reconciliation occur here.

Activating this on real central production, changing the QA DB credentials,
or claiming this is a verified deployed endpoint is expressly unsupported.
"""
from __future__ import annotations
from contextlib import closing
from decimal import Decimal
import os
import re

from flask import Response, g, jsonify, request
from db_r31_pg_sol_report_readonly import (
    DB_QA,ROLE_QA,sol_summary,payment_details,safe_csv,
)

STAGE="DB_R31_PG_SOL_REPORT_PRIVATE_STAGE"
SHA=re.compile(r"[0-9a-f]{40}\Z")
ROUTES={
    "/api/payment-received/sol-report":"sol",
    "/api/payment-received/sol-report.csv":"sol_csv",
    "/api/payment-received/payment-details.csv":"detail_csv",
}


class PrivateStageRefusal(ValueError):
    pass


def _configured():
    return (
        os.environ.get("SBI_R31_PG_REPORT_STAGING_ENABLED")=="true"
        and os.environ.get("SBI_FINANCIAL_APPLY")=="LOCKED"
        and os.environ.get("PGDATABASE")==DB_QA
        and os.environ.get("PGUSER")==ROLE_QA
        and bool(os.environ.get("SBI_R31_REPORT_DSN"))
    )


def _pg():
    if not _configured():
        raise PrivateStageRefusal("QA_REPORT_STAGE_NOT_CONFIGURED")
    import psycopg
    return psycopg.connect(os.environ["SBI_R31_REPORT_DSN"],autocommit=True,
                           connect_timeout=5)


def _identity():
    """UID from actual verified Firebase middleware, not request headers."""
    user=getattr(g,"dil_user",None)
    identity=getattr(g,"dil_identity",None)
    if user is None or type(identity) is not dict:
        return None
    uid=getattr(user,"uid",None)
    claims=getattr(user,"custom_claims",None) or {}
    if (type(uid) is not str or not uid or identity.get("uid")!=uid or
            getattr(user,"disabled",True) is not False or
            claims.get("dil_dashboard") is not True):
        return None
    # Only a dedicated report-viewer claim, or the actual master account.
    # Normal dashboard logins are not automatically entitled to bank data.
    from dashboard_sessions import is_master
    if claims.get("sbi_report_viewer") is not True and not is_master(user):
        return None
    return uid


def _page():
    try:
        limit=int(request.args.get("limit","100"))
        offset=int(request.args.get("offset","0"))
    except (TypeError,ValueError,OverflowError):
        raise PrivateStageRefusal("PAGINATION_INVALID") from None
    if not 1<=limit<=1000 or not 0<=offset<=10000000:
        raise PrivateStageRefusal("PAGINATION_INVALID")
    return limit,offset


def _safe_reply(payload,status=200):
    response=jsonify(payload)
    response.status_code=status
    response.headers["Cache-Control"]="private, no-store"
    response.headers["X-Financial-Apply"]="LOCKED"
    response.headers["X-Reconciliation-Engine"]="NOT_CONNECTED"
    return response


def _sol_ui(report):
    """Retain R31 UI's existing fields; do not fabricate verified matches."""
    groups=[]
    for row in report["records"]:
        paise=row["credit_paise"]
        if type(paise) is not int or paise<0:
            raise PrivateStageRefusal("CREDIT_AMOUNT_UNEXPECTED")
        groups.append({
            "sol_id":row["sol_id"],
            "branch_name":row["branch_name"],
            "payment_rows":row["payment_rows"],
            "credit_total":format(Decimal(paise)/Decimal(100),".2f"),
            "matched":0,  # 0 verified *because no allocation ledger exists*.
            "not_calculated":row["not_calculated"],
            "excluded":row["excluded"],
            "held_for_review":row["held_for_review"],
            "verified_matched_status_available":False,
        })
    t=report["page_totals"]
    return {
        "report":"SOL_WISE_PAYMENT_RECEIVED",
        "source":"CENTRAL_POSTGRESQL_PAYMENT_SOURCE_VIEW",
        "stage":STAGE,
        "sol_groups":groups,
        "totals":{
            "payment_rows":t["payment_rows"],
            "matched":0,
            "not_calculated":t["not_calculated"],
            "excluded":t["excluded"],
            "held_for_review":t["held_for_review"],
        },
        "report_totals_scope":"CURRENT_PAGE_ONLY",
        "limit":report["limit"],"offset":report["offset"],
        "matched_requires_independent_engine_evidence":True,
        "reconciliation_executed":False,
        "master_v251_matrix_v239_connected":False,
        "new_invoice_upload_can_reuse_saved_payment_inputs":False,
        "automatic_invoice_matching_enabled":False,
        "formal_financial_certificate_required_for_report_deploy":False,
        "financial_writes":False,
    }


def _serve(kind):
    if not _configured():
        return _safe_reply({
            "error":"Private PostgreSQL SOL payment reporting is unavailable",
            "stage":STAGE,"financial_writes":False},503)
    uid=_identity()
    if uid is None:
        return _safe_reply({"error":"Report viewer authorization required"},403)
    try:
        limit,offset=_page()
        with closing(_pg()) as conn:
            if kind in ("sol","sol_csv"):
                report=sol_summary(conn,trusted_owner_uid=uid,
                                   limit=limit,offset=offset)
            else:
                report=payment_details(conn,trusted_owner_uid=uid,
                                       limit=limit,offset=offset)
        if kind=="sol":
            return _safe_reply(_sol_ui(report))
        contents=safe_csv(report["records"],detail=kind=="detail_csv")
    except PrivateStageRefusal:
        return _safe_reply({"error":"Private report request invalid"},422)
    except Exception:
        # Do not leak bank payment rows, DSN, host or owner ID in any
        # exception response, log or browser.
        return _safe_reply({"error":"Private PostgreSQL report not available"},503)
    filename=("SBI_SOL_WISE_PAYMENT_TALLY_REPORT.csv" if kind=="sol_csv" else
              "SBI_PAYMENT_RECEIVED_ROW_DETAILS.csv")
    return Response(contents,mimetype="text/csv; charset=utf-8",headers={
        "Content-Disposition":f'attachment; filename="{filename}"',
        "Cache-Control":"private, no-store",
        "X-Financial-Apply":"LOCKED",
        "X-Reconciliation-Engine":"NOT_CONNECTED",
    })


def attach_private_stage_report(app):
    """After importing the untouched R31 Flask app, replace 3 exact views.

    No extra public routes are registered. Global before_request Firebase
    session verification from the original app continues to run first.
    """
    if not _configured():
        raise PrivateStageRefusal("QA_REPORT_STAGE_NOT_CONFIGURED")
    if app.extensions.get("r31_pg_report_private_overlay"):
        raise PrivateStageRefusal("QA_REPORT_STAGE_ALREADY_INSTALLED")
    replace={}
    for route,kind in ROUTES.items():
        selected=[r for r in app.url_map.iter_rules()
                  if r.rule==route and "GET" in r.methods
                  and "POST" not in r.methods
                  and r.endpoint.startswith("sbi_payment_received_reports.")]
        if len(selected)!=1:
            raise PrivateStageRefusal("ORIGINAL_R31_REPORT_ROUTE_REQUIRED")
        replace[selected[0].endpoint]=kind
    if len(replace)!=3:
        raise PrivateStageRefusal("ORIGINAL_REPORT_ENDPOINT_COUNT_INVALID")
    for endpoint,kind in replace.items():
        def handler(_kind=kind):
            return _serve(_kind)
        handler.__name__="db_r31_pg_private_"+kind
        app.view_functions[endpoint]=handler
    app.extensions["r31_pg_report_private_overlay"]=True
    return tuple(sorted(replace))


def staging_app_from_original():
    """Import only in the explicit isolated staging service."""
    if not _configured():
        raise PrivateStageRefusal("QA_REPORT_STAGE_NOT_CONFIGURED")
    from app import app
    attach_private_stage_report(app)
    return app
