"""DB-R31.11.3 restricted staging route, disabled unless explicitly enabled.

Depends on the already-installed Firebase verify_session_cookie -> g.dil_user
middleware. No public route is created in Caddy; no financial mutations.
"""
from __future__ import annotations
import os
from flask import Blueprint, g, jsonify, request

from r31_11_3_runtime_rls_adapter import (
    ENABLE_FLAG, read_tenant_source_only, RuntimeRLSBlocked,
)

runtime_tenant_rls = Blueprint("r3113_runtime_tenant_rls", __name__)


@runtime_tenant_rls.get("/api/r31-private-qa/tenant-rls-source")
def qa_tenant_rls_source():
    if (os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED")
            != "isolated-ownerqa-firebase-csrf-v1"
            or os.environ.get("SBI_R31_11_3_RUNTIME_ENABLED") != ENABLE_FLAG):
        return jsonify(error="Private runtime RLS not enabled"), 503
    # install_sessions(app) verified Firebase cookie & claims first;
    # request arguments/headers are NEVER a source of tenant identity.
    user = getattr(g, "dil_user", None)
    if user is None:
        return jsonify(error="Authenticated dashboard session required"), 401
    supplied = request.args.get("limit", "20")
    if not supplied.isdecimal() or not 1 <= len(supplied) <= 3:
        return jsonify(error="Invalid pagination"), 400
    try:
        rows = read_tenant_source_only(user, limit=int(supplied))
    except RuntimeRLSBlocked:
        # Intentionally uniform; do not reveal role mapping or DB error.
        return jsonify(error="Restricted tenant QA not ready",
                       financial_execution_enabled=False), 503
    return jsonify(
        report="R31_11_3_DB_ENFORCED_TENANT_SOURCE_ONLY",
        rows=rows,
        reconciliation_status="NOT_CALCULATED",
        invoice_generation_enabled=False,
        gst_generation_enabled=False,
        financial_execution_enabled=False,
        production_financial_writes=False,
    )
