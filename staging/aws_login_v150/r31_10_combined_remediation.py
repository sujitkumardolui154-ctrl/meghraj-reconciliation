#!/usr/bin/env python3
"""R31.10 combined, fail-closed staged remediation verification.

1. Tests FORCE RLS / security_invoker in a transaction-rolled-back shadow
   schema on existing isolated R31 synthetic QA PostgreSQL database.
2. Uses two different real, already-authorized Firebase TEST credentials
   and tests bidirectional foreign receipt denial (R31.9 harness).
3. Verifies private QA container is still not exposed via public Caddy.
   Actual external HTTPS end-to-end is blocked pending separately approved
   mTLS route / origin configuration, NOT silently marked PASS.

Never runs DDL on sbi.*, creates users/claims, edits Caddy, or writes to
production finance sources.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from r31_real_firebase_qa_acceptance import (
    PG, QA_DB, STAGE, preflight, docker, firebase_api_key
)
from r31_9_combined_gate import signin, run_inner

ROOT = Path(__file__).resolve().parent
SQL = ROOT / "r31_10_shadow_rls.sql"
BRANCH_QA_DB = "sbi_r31_owner_qa_20261125"
EXPECTED_STAGE = "sbi-r31-auth-private-qa"
EXPECTED_PG = "sbi-synthetic-postgres-38-31"
EXPECTED_RECEIPTS = frozenset({
    "DB_R31_10_SHADOW_RLS_BIDIRECTIONAL=PASS",
    "DB_R31_10_SHADOW_RLS_CLEANUP=PASS",
})


def shadow_qa():
    if SQL.is_symlink() or not SQL.is_file():
        print("STOP=DB_R31_10_SHADOW_SQL_MISSING", flush=True)
        return False
    if (PG != EXPECTED_PG or QA_DB != BRANCH_QA_DB
            or STAGE != EXPECTED_STAGE):
        print("STOP=DB_R31_10_PG_IDENTITY_CHANGED", flush=True)
        return False
    script = SQL.read_text("utf-8")
    # All mutating SQL is confined to the transaction-rolled-back shadow
    # schema and roles, guarded by current_database and session_user.
    result = subprocess.run([
        "sudo", "-n", "docker", "exec", "-i", EXPECTED_PG,
        "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", BRANCH_QA_DB,
    ], input=script, capture_output=True, text=True, timeout=60,
       check=False)
    found = set()
    for line in result.stdout.splitlines():
        if line in EXPECTED_RECEIPTS:
            print(line, flush=True)
            found.add(line)
    if result.returncode or found != EXPECTED_RECEIPTS:
        print("STOP=DB_R31_10_SHADOW_RLS_NOT_VERIFIED", flush=True)
        return False
    # The real, existing sbi.* tables were deliberately NOT changed.
    print("DB_R31_10_EXISTING_SBI_RLS=MIGRATION_NOT_APPLIED", flush=True)
    return True


def real_two_owner_qa():
    if not sys.stdin.isatty():
        print("DB_R31_10_TWO_FIREBASE_OWNERS=NOT_TESTED_INTERACTIVE_TERMINAL_REQUIRED",
              flush=True)
        return False
    answer = input(
        "Two DIFFERENT approved Firebase test users available? [y/N]: "
    ).strip().lower()
    if answer != "y":
        print("DB_R31_10_TWO_FIREBASE_OWNERS=NOT_TESTED_SECOND_USER_NOT_READY",
              flush=True)
        return False
    tokens = []
    try:
        key = firebase_api_key()
        print("FIREBASE_TEST_ACCOUNT_1=PRIVATE_INPUT", flush=True)
        tokens.append(signin(key))
        print("FIREBASE_TEST_ACCOUNT_2=PRIVATE_INPUT_DIFFERENT_UID", flush=True)
        tokens.append(signin(key))
        status, lines = run_inner(tokens)
        needed = {
            "DB_R31_9_TWO_REAL_FIREBASE_USERS=PASS_DISTINCT_AUTHENTICATED_UIDS",
            "DB_R31_9_REAL_CROSS_ACCOUNT_RECEIPTS=PASS_BIDIRECTIONAL_404_AND_FILTERING",
            "DB_R31_9_SYNTHETIC_RECEIPT_CLEANUP=PASS",
        }
        if status == 0 and needed.issubset(set(lines)):
            print("DB_R31_10_TWO_FIREBASE_OWNERS=PASS_DISTINCT_BIDIRECTIONAL",
                  flush=True)
            return True
        print("DB_R31_10_TWO_FIREBASE_OWNERS=BLOCKED_DISTINCT_USER_OR_ISOLATION",
              flush=True)
        return False
    finally:
        tokens.clear()


def external_https_gate():
    config = docker("exec", "aws_lightsail-caddy-1",
                    "cat", "/etc/caddy/Caddyfile")
    # Never attempt to enable a public route or infer safe mTLS based on the
    # existence of HTTPS alone; verified second-party and TLS QA must happen
    # after an approved hostname, CA/cert and application Origin deployment.
    if "sbi-r31-auth-private-qa" in config or "sbi-r31-auth-qa" in config:
        print("STOP=DB_R31_10_UNAPPROVED_CADDY_QA_ROUTE_PRESENT", flush=True)
        print("DB_R31_10_EXTERNAL_HTTPS_E2E=BLOCKED_UNAPPROVED_ROUTE",
              flush=True)
        return False
    print("DB_R31_10_PUBLIC_QA_ROUTE=ABSENT_AS_REQUIRED", flush=True)
    print("DB_R31_10_EXTERNAL_HTTPS_E2E=BLOCKED_PENDING_APPROVED_MTLS_ROUTE",
          flush=True)
    return False


def main():
    print("=== DB-R31.10 COMBINED REMEDIATION PRIVATE QA ===", flush=True)
    preflight()
    rls_ok = shadow_qa()
    two_ok = real_two_owner_qa()
    https_ok = external_https_gate()
    print("DB_R31_10_PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST", flush=True)
    if rls_ok and two_ok and https_ok:
        print("STOP=DB_R31_10_MANUAL_RELEASE_REVIEW_REQUIRED", flush=True)
        return 2
    print("DB_R31_10_RELEASE_STATUS=STAGING_REMEDIATION_INCOMPLETE_PRODUCTION_BLOCKED",
          flush=True)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_10_HOST_OR_DOCKER_UNAVAILABLE", flush=True)
        raise SystemExit(2)
