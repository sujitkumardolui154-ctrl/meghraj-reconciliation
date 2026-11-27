#!/usr/bin/env python3
"""R31.13: consolidated Firebase -> PostgreSQL tenant RLS evidence gate.

AUDIT-ONLY. Reuses the established R31.11.4H and 4J QA guards, including
the prior R31.11.4I operator-reported two-real-Firebase-session receipt.
Never creates users, roles, tokens, cookies, containers, certificates or
SQL fixtures. No network listener, Caddy edit, deployment or financial write.
A PASS is NOT a production acceptance, a live external HTTPS test, or a
new in-process authentication execution.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

import r31_11_4j_combined_mtls_gate as existing

ROOT = Path(__file__).resolve().parent
ADAPTER = ROOT / "r31_11_4_runtime_rls_adapter.py"
BLUEPRINT = ROOT / "r31_11_4_runtime_rls_blueprint.py"
APP = ROOT / "app.py"

EXPECTED_DB = "sbi_r31_11_4_auth_qa_20261126"
EXPECTED_POSTGRES = "sbi-r3114-private-postgres"
EXPECTED_ROUTE = "/api/r31-private-qa/tenant-rls-source-r3114"
EXPECTED_FLAG = "private-firebase-rls-auth-acceptance-v1"


class AuditBlocked(RuntimeError):
    pass


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AuditBlocked(label)


def source_contracts() -> None:
    """Defensive source review; not a substitute for real session testing."""
    for p in (ADAPTER, BLUEPRINT, APP):
        require(p.is_file() and not p.is_symlink(), "SOURCE_FILE_MISSING")
    adapter = ADAPTER.read_text("utf-8")
    blueprint = BLUEPRINT.read_text("utf-8")
    app = APP.read_text("utf-8")
    for value in (adapter, blueprint, app):
        ast.parse(value)
    required_adapter = (
        f'QA_DB = "{EXPECTED_DB}"',
        f'QA_HOST = "{EXPECTED_POSTGRES}"',
        f'ENABLE_FLAG = "{EXPECTED_FLAG}"',
        'r311_auth.current_tenant_uid()',
        "row_security_active('sbi.import_batches')",
        "row_security_active('sbi.payment_source_rows')",
        "row_security_active('sbi.payments')",
        "row_security_active('sbi.payment_source_status_v1')",
        "options=\"-c default_transaction_read_only=on\"",
        'cur.execute("SET TRANSACTION READ ONLY")',
        "if len(item) != 5 or item[0] != uid:",
        "return output",
    )
    for needle in required_adapter:
        require(needle in adapter, "ADAPTER_SECURITY_CONTRACT_CHANGED")
    require("SET ROLE " not in adapter and
            "SET SESSION AUTHORIZATION " not in adapter,
            "UNSAFE_ROLE_SWITCH_IN_ADAPTER")
    require("WHERE owner_uid =" not in adapter,
            "ADAPTER_OWNER_FILTER_WOULD_OBSCURE_RLS")
    require("g, jsonify, request" in blueprint and
            'getattr(g, "dil_user", None)' in blueprint and
            EXPECTED_ROUTE in blueprint and
            "request.args.get(\"limit\", \"20\")" in blueprint and
            "production_financial_writes=False" in blueprint,
            "ROUTE_TRUST_BOUNDARY_CHANGED")
    require("SBI_R31_11_4_RUNTIME_ENABLED" in app and
            "SBI_R31_PRIVATE_STAGING_ENABLED" in app,
            "FEATURE_FLAG_GUARD_CHANGED")
    print("DB_R31_13_ADAPTER_CONTRACT=PASS_SOURCE_READONLY_GUARDED", flush=True)
    print("DB_R31_13_BACKEND_TRUST=PASS_FIREBASE_SESSION_OBJECT_ONLY_SOURCE_CONTRACT",
          flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="R31.13 consolidated private read-only gate")
    p.add_argument("--source-sha", required=True)
    args = p.parse_args(argv)
    print("=== DB-R31.13 FIREBASE TO POSTGRES TENANT RLS HANDOVER ===", flush=True)
    try:
        require(re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is not None,
                "SOURCE_SHA_INVALID")
        # The shared guard re-audits private PG, two existing Firebase
        # Admin users, owner maps, local receipt metadata, and unchanged Caddy.
        # No second password login or new Flask test session is created.
        existing.audit_baseline(args.source_sha)
        source_contracts()
        print("DB_R31_13_TWO_FIREBASE_TO_PG_SESSIONS=PASS_PRIOR_4I_LOCAL_OPERATOR_RECEIPT",
              flush=True)
        print("DB_R31_13_POSTGRES_TENANT_ISOLATION=PASS_CURRENT_4H_READONLY_AUDIT",
              flush=True)
        print("DB_R31_13_RUNTIME_INTEGRATION=PRIVATE_IN_PROCESS_QA_ONLY_NO_LIVE_ROUTE",
              flush=True)
        print("DB_R31_13_SECURITY_HANDOVER=PASS_EVIDENCE_READY_FOR_REVIEW_ONLY",
              flush=True)
        return 0
    except Exception:
        # No raw cloud, Firebase, role-mapping or secret details in output.
        print("STOP=DB_R31_13_READONLY_BINDING_REVIEW_REQUIRED", flush=True)
        return 2
    finally:
        print("DB_R31_13_REAL_EXPIRED_REVOKED_FIREBASE_SESSION=NOT_TESTED", flush=True)
        print("DB_R31_13_EXTERNAL_MTLS_HTTPS=NOT_TESTED", flush=True)
        print("DB_R31_13_PRODUCTION_RUNTIME_DEPLOYMENT=NOT_APPROVED", flush=True)
        print("DB_R31_13_FINANCIAL_APPLY=LOCKED", flush=True)
        print("DB_R31_13_PRODUCTION_RELEASE=BLOCKED", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
