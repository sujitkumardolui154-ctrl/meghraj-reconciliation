#!/usr/bin/env python3
"""DB-R31.11.4H: one-command combined read-only R31.11.4E + 4G QA.

Runs live AWS *metadata and read-only DB* checks, Firebase Admin get_user()
reverification for both previously approved test accounts, and verifies the
original Caddy fingerprint from the operator's last successful 4G run.

Never starts/restarts containers, creates networks, logs in with passwords,
validates a genuine session cookie, exposes a port, reads private secret
contents, alters data or Caddy, or claims HTTPS/mTLS accepted.

4F two genuine Firebase session-to-PG receipts remain evidence-not-provided,
even when every combined read-only test passes. R31.12 is ACTIVE_QA_DESIGN
only; production financial Apply remains LOCKED.
"""
from __future__ import annotations

import argparse
import re

import r31_11_4e_session_binding_readiness as e
import r31_11_4g_mtls_readonly_preflight as g

EXPECTED_4G_CADDY_SHA256 = (
    "61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b"
)
BASELINE_QA_DB = "sbi_r31_11_4_auth_qa_20261126"
BASELINE_QA_PG = "sbi-r3114-private-postgres"
BASELINE_QA_NET = "sbi-r3114-private-isolated"


class CombinedBlocked(RuntimeError):
    """Fail-closed stable code, never a raw cloud or secret error."""


def require(ok, code):
    if not ok:
        raise CombinedBlocked(code)


def check_repo_and_scope(sha):
    require(type(sha) is str and re.fullmatch("[0-9a-f]{40}",sha) is not None,
            "SOURCE_SHA_INVALID")
    # Reuse 4G exact git HEAD, clean checkout and invalid-hostname template.
    g.check_source(sha)
    require(g.QA_DB == BASELINE_QA_DB
            and g.POSTGRES == BASELINE_QA_PG
            and g.QA_NETWORK == BASELINE_QA_NET,
            "QA_DATABASE_TARGET_CHANGED")
    print("DB_R31_11_4H_SOURCE_AND_QA_SCOPE=PASS_PINNED",flush=True)


def run_combined(sha):
    check_repo_and_scope(sha)
    # The previous R31.11.4E source/infra guard and RLS/role catalog are
    # re-run as read-only checks; never 4A/4B/4C provisioning functions.
    e._candidate_source_guards()
    e.infra.preflight()
    e._read_only_qa_catalog()
    print("DB_R31_11_4H_PRIVATE_PG16_RLS_AND_ROLE_GRANTS=PASS_READONLY",flush=True)

    approved=e.roles._approved_users()
    require(type(approved) is list and len(approved)==2
            and approved[0]["uid"]!=approved[1]["uid"]
            and approved[0]["email"]!=approved[1]["email"],
            "FIREBASE_TEST_IDENTITIES_NOT_DISTINCT")
    print("DB_R31_11_4H_TWO_REAL_FIREBASE_USER_RECORDS=PASS_ADMIN_READONLY",flush=True)

    # This does not read credential content and does not create sessions.
    e._secure_metadata()
    e._no_private_qa_runtime_deployment()
    print("DB_R31_11_4H_SECRET_METADATA_AND_RUNTIME_ABSENCE=PASS",flush=True)

    g.check_database_isolation()
    print("DB_R31_11_4H_QA_EVIDENCE_ROWS=ZERO_OWNER_MAPS_TWO",flush=True)

    fingerprint=g.caddy_preflight()
    require(fingerprint==EXPECTED_4G_CADDY_SHA256,
            "CADDY_BASELINE_MISMATCH")
    print("DB_R31_11_4H_CADDY=PASS_MATCH_PREVIOUS_4G_SHA256",flush=True)

    g.ephemeral_cleanup()
    print("DB_R31_11_4H_4F_TEMP_CONTAINER_NETWORK_ADC=PASS_ABSENT",flush=True)

    # Verify original Caddy config and DB evidence remained unchanged even
    # during the read-only checks; this is NOT a runtime HTTP/mTLS test.
    require(g.caddy_preflight()==fingerprint,
            "CADDY_CHANGED_DURING_COMBINED_QA")
    g.check_database_isolation()
    print("DB_R31_11_4H_AFTER_QA_CADDY_AND_DATABASE=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4H_COMBINED_READONLY_SECURITY=PASS",flush=True)


def main(argv=None):
    p=argparse.ArgumentParser(description="R31.11.4H combined QA/read-only only")
    p.add_argument("--source-sha",required=True)
    args=p.parse_args(argv)
    print("=== DB-R31.11.4H COMBINED READONLY SECURITY QA ===",flush=True)
    try:
        run_combined(args.source_sha)
        return 0
    except Exception:
        # Never disclose raw OAuth, Firebase, UID, Caddy, SQL or Docker data.
        print("STOP=DB_R31_11_4H_COMBINED_READONLY_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4H_REAL_FIREBASE_SESSION_E2E=EVIDENCE_NOT_PROVIDED",flush=True)
        print("DB_R31_11_4H_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4H_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4H_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4H_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
