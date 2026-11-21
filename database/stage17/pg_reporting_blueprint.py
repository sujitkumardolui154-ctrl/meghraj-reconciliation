"""Stage 17 PostgreSQL report endpoint; DENY-BY-DEFAULT until an audited
PR129 authentication callback is configured. Never exposes unverified SQL.
"""
from flask import Blueprint, current_app, jsonify
from sbi_pg_reporting import read_report_counts

pg_reporting_blueprint = Blueprint("sbi_postgres_reporting_stage17", __name__)


@pg_reporting_blueprint.before_request
def require_verified_authorization():
    auth = current_app.config.get("SBI_PG_REPORT_AUTH_CHECK")
    # Do not use a request header, query parameter, or unauthenticated token.
    # No built-in bypass: approval must come from existing server-side auth.
    if not callable(auth):
        return jsonify({"error": "postgres_reporting_not_enabled"}), 403
    try:
        allowed = auth()
    except Exception:
        allowed = False
    if allowed is not True:
        return jsonify({"error": "forbidden"}), 403


@pg_reporting_blueprint.get("/api/reporting/v2/postgresql-summary")
def postgres_summary():
    try:
        data = read_report_counts()
    except Exception:
        current_app.logger.warning("PostgreSQL reporting unavailable")
        return jsonify({"error": "reporting_unavailable"}), 503
    return jsonify({
        "source": "sbi_reconciliation_main",
        "mode": "read_only",
        **data.as_dict(),
    })
