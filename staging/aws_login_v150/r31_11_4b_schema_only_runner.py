#!/usr/bin/env python3
"""R31.11.4B: verified EMPTY private QA database RLS schema ONLY.

DEFAULT: READ-ONLY audit. --apply is an operator-approved one-time transactional
migration. Never creates LOGIN roles, password files, Firebase accounts,
tenant mappings, financial records, network routes, or production writes.
R31.12 invoice/GST/reconciliation is QUARANTINED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import r31_11_4a_isolated_postgres_provision as infra

PG = "sbi-r3114-private-postgres"
DB = "sbi_r31_11_4_auth_qa_20261126"
SQL_FILE = Path(__file__).with_name("r31_11_4b_schema_only_up.sql")
APPROVE = "R3114B_SCHEMA_ONLY_PRIVATE_QA"

class BootstrapBlocked(RuntimeError):
    pass


def _psql(sql: str):
    try:
        run = subprocess.run(
            ["sudo", "-n", "docker", "exec", "-i", PG,
             "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DB],
            input=sql.encode("utf-8"),
            capture_output=True, timeout=65, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapBlocked("READONLY_QUERY_UNAVAILABLE") from None
    if run.returncode:
        raise BootstrapBlocked("GUARDED_PSQL_FAILED")
    return run.stdout.decode("utf-8", errors="strict").strip()


def _guarded_preflight():
    infra.preflight()
    if (infra.NAME, infra.DATABASE) != (PG, DB):
        raise BootstrapBlocked("PRIVATE_QA_TARGET_NOT_PINNED")
    image_id = infra.inspect_original_image()
    if not infra._exact_topology(image_id):
        raise BootstrapBlocked("PRIVATE_QA_TOPOLOGY_UNSAFE")
    catalog = infra.docker(
        "exec", PG, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", "postgres", "-c",
        "SELECT datname FROM pg_database ORDER BY datname"
    )
    if set(catalog.splitlines()) != infra.BASE_ALLOWED:
        raise BootstrapBlocked("DATABASE_CLUSTER_NOT_DEDICATED")
    config = infra.caddy_fingerprint()
    return config


def _state():
    query = """
    BEGIN READ ONLY;
    SELECT json_build_object(
     'db',current_database(),
     'schema_count',(
       SELECT count(*) FROM pg_namespace
       WHERE nspname IN ('sbi','r311_auth')),
     'source_tables',(
       SELECT count(*) FROM pg_class c JOIN pg_namespace n
         ON n.oid=c.relnamespace
       WHERE n.nspname='sbi'
         AND c.relname IN ('import_batches','payment_source_rows',
                           'payments','payment_source_status_v1')
         AND c.relkind='r'),
     'forced_rls',(
       SELECT count(*) FROM pg_class c JOIN pg_namespace n
         ON n.oid=c.relnamespace
       WHERE n.nspname='sbi'
         AND c.relname IN ('import_batches','payment_source_rows',
                           'payments','payment_source_status_v1')
         AND c.relrowsecurity AND c.relforcerowsecurity),
     'policies',(SELECT count(*) FROM pg_policies
        WHERE schemaname='sbi'
          AND tablename IN ('import_batches','payment_source_rows',
                            'payments','payment_source_status_v1')),
     'groups',(SELECT count(*) FROM pg_roles
        WHERE rolname IN ('r311_qa_tenant_a','r311_qa_tenant_b')
          AND NOT rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolcreaterole AND NOT rolcreatedb),
     'logins',(SELECT count(*) FROM pg_roles
        WHERE rolname IN ('r3113_login_a','r3113_login_b')),
     'map_table_exists',to_regclass('r311_auth.role_owner_map')
        IS NOT NULL,
     'invoker_view',COALESCE((
       SELECT 'security_invoker=true'=ANY(c.reloptions)
       FROM pg_class c
       WHERE c.oid=to_regclass('sbi.payment_received_source_v1')
     ),false),
     'user_data',(
       SELECT count(*) FROM pg_class c JOIN pg_namespace n
         ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')
     )
    )::text;
    COMMIT;
    """
    data = json.loads(_psql(query))
    if type(data) is not dict or data.get("db") != DB:
        raise BootstrapBlocked("CATALOG_IDENTITY_INVALID")
    for k in (
        "schema_count","source_tables","forced_rls","policies",
        "groups","logins","user_data"
    ):
        if type(data.get(k)) is not int:
            raise BootstrapBlocked("CATALOG_FIELD_INVALID")
    if type(data.get("map_table_exists")) is not bool or type(data.get("invoker_view")) is not bool:
        raise BootstrapBlocked("CATALOG_BOOLEAN_INVALID")
    return data


def _is_empty(state):
    return (
        state["schema_count"] == 0
        and state["source_tables"] == 0
        and state["forced_rls"] == 0
        and state["policies"] == 0
        and state["groups"] == 0
        and state["logins"] == 0
        and state["map_table_exists"] is False
        and state["invoker_view"] is False
        and state["user_data"] == 0
    )


def _is_schema_only(state):
    return (
        state["schema_count"] == 2
        and state["source_tables"] == 4
        and state["forced_rls"] == 4
        and state["policies"] == 4
        and state["groups"] == 2
        and state["logins"] == 0
        and state["map_table_exists"] is True
        and state["invoker_view"] is True
        and state["user_data"] == 0
    )


def _all_new_source_tables_empty():
    """Exact source and protected mapping rows: no real or synthetic data."""
    statement = """
    BEGIN READ ONLY;
    SELECT
       (SELECT count(*) FROM sbi.import_batches)
      +(SELECT count(*) FROM sbi.payment_source_rows)
      +(SELECT count(*) FROM sbi.payments)
      +(SELECT count(*) FROM sbi.payment_source_status_v1)
      +(SELECT count(*) FROM r311_auth.role_owner_map);
    COMMIT;
    """
    return _psql(statement) == "0"


def _sql_source():
    if (SQL_FILE.is_symlink() or not SQL_FILE.is_file()
            or not stat.S_ISREG(SQL_FILE.stat().st_mode)):
        raise BootstrapBlocked("SQL_SOURCE_UNSAFE")
    raw = SQL_FILE.read_bytes()
    if not 2000 <= len(raw) <= 30000:
        raise BootstrapBlocked("SQL_SOURCE_SIZE_INVALID")
    decoded=raw.decode("utf-8")
    if ("sbi_r31_11_4_auth_qa_20261126" not in decoded
            or "DB_R31_11_4B_SCHEMA_RLS_BOOTSTRAP" not in decoded):
        raise BootstrapBlocked("SQL_SOURCE_UNEXPECTED")
    return decoded, hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true",
                        help="One-time new QA schema migration ONLY")
    parser.add_argument("--approve",default="")
    opts=parser.parse_args(argv)
    print("=== DB-R31.11.4B PRIVATE SCHEMA-ONLY RLS PREPARATION ===",flush=True)
    try:
        caddy_before=_guarded_preflight()
        print("DB_R31_11_4B_PRIVATE_ISOLATION=PASS",flush=True)
        current=_state()
        if not _is_empty(current):
            print("DB_R31_11_4B_DATABASE_ALREADY_POPULATED_OR_MIGRATED=REVIEW_ONLY",
                  flush=True)
            if _is_schema_only(current):
                print("DB_R31_11_4B_EXISTING_SCHEMA=EXPECTED_BASIC_CATALOG_PRESENT",
                      flush=True)
            return 2
        print("DB_R31_11_4B_NEW_DATABASE=EMPTY_NO_LOGIN_ROLES",flush=True)
        sql, digest=_sql_source()
        print("DB_R31_11_4B_MIGRATION_SHA256="+digest,flush=True)
        if not opts.apply:
            print("DB_R31_11_4B_MODE=READONLY_PLAN_ONLY_NO_CHANGES",flush=True)
            return 0
        if opts.approve != APPROVE:
            raise BootstrapBlocked("EXPLICIT_SCHEMA_QA_AUTHORIZATION_REQUIRED")
        print("DB_R31_11_4B_MODE=EXPLICIT_QA_SCHEMA_ONLY_APPLY",flush=True)
        out=_psql(sql)
        if out != "DB_R31_11_4B_SCHEMA_RLS_BOOTSTRAP=PASS_NO_REAL_USERS":
            raise BootstrapBlocked("MIGRATION_ACK_UNEXPECTED")
        after=_state()
        if not _is_schema_only(after) or not _all_new_source_tables_empty():
            raise BootstrapBlocked("POST_MIGRATION_CATALOG_UNVERIFIED")
        if infra.caddy_fingerprint() != caddy_before:
            raise BootstrapBlocked("CADDY_CONFIG_CHANGED")
        infra.preflight()
        print("DB_R31_11_4B_FORCED_RLS_FOUR_TABLES=PASS",flush=True)
        print("DB_R31_11_4B_SECURITY_INVOKER_VIEW=PASS",flush=True)
        print("DB_R31_11_4B_ROLE_OWNER_MAPPING=EMPTY_NO_REAL_USERS",flush=True)
        print("DB_R31_11_4B_LOGIN_ROLES=NONE_PROVISIONED",flush=True)
        print("DB_R31_11_4B_SCHEMA_ONLY=PASS_PRIVATE_QA",flush=True)
        return 0
    except (BootstrapBlocked, infra.ProvisionBlocked, OSError,
            ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_11_4B_GUARDED_SCHEMA_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4B_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4B_PRODUCTION_WRITES=NONE_BY_RUNNER",flush=True)
        print("DB_R31_11_4B_FIREBASE_TWO_REAL_USERS=NOT_TESTED",flush=True)
        print("DB_R31_11_4B_HTTPS_E2E=NOT_TESTED",flush=True)
        print("DB_R31_11_4B_R3112_FINANCIAL_INTEGRATION=QUARANTINED",flush=True)
        print("DB_R31_11_4B_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING",
              flush=True)


if __name__=="__main__":
    raise SystemExit(main())
