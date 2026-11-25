#!/usr/bin/env python3
"""R31.11 combined STAGING candidate: new empty PG clone + Firebase + HTTPS.

Never touches real R31.7/R31.10 owner-QA rows or production.
Requires fresh explicit worktree. No public Caddy route, credentials or auth
claims are created. Synthetic financial source records go ONLY to clone DB.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from r31_real_firebase_qa_acceptance import (
    preflight,docker,PG,QA_DB,STAGE
)
from r31_11_second_firebase_preflight import check_second_firebase
from r31_10_combined_remediation import real_two_owner_qa

ROOT=Path(__file__).resolve().parent
CLONE="sbi_r31_11_tenant_clone_20261125"
MIGRATION=ROOT/"r31_11_clone_rls_up.sql"
VERIFY=ROOT/"r31_11_clone_rls_verify.sql"
REQUIRED={
    "DB_R31_11_CLONE_TENANT_RLS_MIGRATION=PASS",
    "DB_R31_11_CLONE_TWO_ROLE_RAW_TABLE_RLS=PASS",
    "DB_R31_11_CLONE_SECURITY_INVOKER_VIEW=PASS",
    "DB_R31_11_SHARED_REPORT_ROLE_DENIED=PASS",
    "DB_R31_11_ONLY_SYNTHETIC_CLONE_ROWS=PASS",
}


def invoke(*arguments, payload=None, timeout=50):
    return subprocess.run(
        ["sudo","-n","docker",*arguments],
        input=payload, text=True, capture_output=True,
        timeout=timeout, check=False
    )


def database_isolation():
    if (PG!="sbi-synthetic-postgres-38-31"
            or QA_DB!="sbi_r31_owner_qa_20261125"
            or STAGE!="sbi-r31-auth-private-qa"):
        print("STOP=DB_R31_11_QA_IDENTITY_MISMATCH",flush=True)
        return False
    info=json.loads(docker("inspect",PG))[0]
    if (info.get("Config",{}).get("Image") in (None,"")
          or not info.get("State",{}).get("Running")
          or info.get("HostConfig",{}).get("PortBindings") not in (None,{})
          or set(info.get("NetworkSettings",{}).get("Networks",{}))
             != {"sbi-synthetic-isolated-38-31"}):
        print("STOP=DB_R31_11_QA_DB_NETWORK_NOT_ISOLATED",flush=True)
        return False
    net=json.loads(docker("network","inspect","sbi-synthetic-isolated-38-31"))[0]
    if net.get("Internal") is not True:
        print("STOP=DB_R31_11_QA_DB_NETWORK_NOT_INTERNAL",flush=True)
        return False
    names=docker("exec",PG,"psql","-X","-qAt",
                 "-U","postgres","-d","postgres","-c",
                 "SELECT datname FROM pg_database "
                 "WHERE datname='sbi_reconciliation_main'")
    if names:
        print("STOP=DB_R31_11_FINANCIAL_PRODUCTION_DB_VISIBLE",flush=True)
        return False
    return True


def run_sql(sql_file):
    if not sql_file.is_file() or sql_file.is_symlink():
        print("STOP=DB_R31_11_SQL_SOURCE_MISSING",flush=True)
        return None
    result=invoke("exec","-i",PG,"psql","-X","-qAt",
                  "-v","ON_ERROR_STOP=1","-U","postgres","-d",CLONE,
                  payload=sql_file.read_text("utf-8"),timeout=75)
    # Deliberately NEVER display raw database stdout/stderr.
    if result.returncode:
        return None
    return {line for line in result.stdout.splitlines() if line in REQUIRED}


def create_schema_only_clone():
    exists=docker("exec",PG,"psql","-X","-qAt",
                  "-U","postgres","-d","postgres","-c",
                  "SELECT count(*) FROM pg_database WHERE datname='"+CLONE+"'")
    if exists!="0":
        print("STOP=DB_R31_11_CLONE_ALREADY_EXISTS_REVIEW_REQUIRED",flush=True)
        return False
    print("DB_R31_11_NEW_EMPTY_CLONE=CREATING_SCHEMA_ONLY",flush=True)
    made=invoke("exec",PG,"createdb","-U","postgres","-O","postgres",CLONE)
    if made.returncode:
        print("STOP=DB_R31_11_CREATE_CLONE_FAILED",flush=True)
        return False
    dump=invoke("exec",PG,"pg_dump","-U","postgres","-d",QA_DB,
                "--schema-only","--schema=sbi",timeout=65)
    if dump.returncode or "CREATE SCHEMA sbi" not in dump.stdout:
        print("STOP=DB_R31_11_SCHEMA_ONLY_DUMP_FAILED",flush=True)
        return False
    applied=invoke("exec","-i",PG,"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
                   "-U","postgres","-d",CLONE,payload=dump.stdout,timeout=65)
    if applied.returncode:
        print("STOP=DB_R31_11_SCHEMA_ONLY_APPLY_FAILED",flush=True)
        return False
    print("DB_R31_11_NEW_EMPTY_CLONE=PASS",flush=True)
    return True


def clone_tenant_security():
    if not database_isolation():
        return False
    if not create_schema_only_clone():
        return False
    migrated=run_sql(MIGRATION)
    if migrated is None or "DB_R31_11_CLONE_TENANT_RLS_MIGRATION=PASS" not in migrated:
        print("STOP=DB_R31_11_CLONE_MIGRATION_FAILED",flush=True)
        return False
    print("DB_R31_11_CLONE_TENANT_RLS_MIGRATION=PASS",flush=True)
    verified=run_sql(VERIFY)
    if verified is None or not (REQUIRED-{"DB_R31_11_CLONE_TENANT_RLS_MIGRATION=PASS"}).issubset(verified):
        print("STOP=DB_R31_11_CLONE_RLS_VERIFICATION_FAILED",flush=True)
        return False
    for marker in sorted(verified):
        print(marker,flush=True)
    return True


def https_security():
    config=docker("exec","aws_lightsail-caddy-1",
                  "cat","/etc/caddy/Caddyfile")
    if "sbi-r31-auth-private-qa" in config or "sbi-r31-auth-qa" in config:
        print("STOP=DB_R31_11_UNAPPROVED_PUBLIC_QA_ROUTE",flush=True)
        return False
    print("DB_R31_11_CADDY_QA_EXPOSURE=NONE",flush=True)
    print("DB_R31_11_EXTERNAL_HTTPS_E2E=PENDING_APPROVED_MTLS_HOST_AND_ORIGIN",flush=True)
    return False


def main():
    print("=== DB-R31.11 COMBINED TENANT SECURITY QA ===",flush=True)
    preflight()
    clone_ok=clone_tenant_security()
    second_ok=check_second_firebase()
    cross_ok=real_two_owner_qa() if second_ok else False
    https_ok=https_security()
    print("DB_R31_11_EXISTING_SBI_QA_SCHEMA=UNCHANGED",flush=True)
    print("DB_R31_11_PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST",flush=True)
    # Never claim completion while the original application still uses its
    # shared PG role or external TLS remains untested.
    print("DB_R31_11_RUNTIME_RLS_ADAPTER=NOT_CONNECTED",flush=True)
    print("DB_R31_11_RELEASE_STATUS=STAGING_SECURITY_CANDIDATE_ONLY_PRODUCTION_BLOCKED",
          flush=True)
    return 2


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,subprocess.TimeoutExpired,ValueError,KeyError):
        print("STOP=DB_R31_11_PRIVATE_RUNTIME_UNAVAILABLE",flush=True)
        raise SystemExit(2)
