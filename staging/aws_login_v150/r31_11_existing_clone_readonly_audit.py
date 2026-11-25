#!/usr/bin/env python3
"""R31.11 existing-clone READ-ONLY resume: never recreate, repair or migrate.

For an existing isolated R31.11 schema-only clone, report whether its
catalog migration and disposable 2-owner fixture are complete, and (only
when exact known synthetic evidence is present) verify actual RLS reads
under both restricted PostgreSQL sessions.

NEVER calls createdb, pg_dump, DDL, INSERT/UPDATE/DELETE, Caddy reload,
Firebase sign-in, account creation, reconciliation or financial Apply.
Does not change existing QA database, cloned rows, or production.
"""
from __future__ import annotations

import json
import subprocess

from r31_real_firebase_qa_acceptance import PG, QA_DB, STAGE, preflight, docker

CLONE = "sbi_r31_11_tenant_clone_20261125"
EXPECTED_PG = "sbi-synthetic-postgres-38-31"
EXPECTED_QA = "sbi_r31_owner_qa_20261125"
EXPECTED_STAGE = "sbi-r31-auth-private-qa"
SOURCE_TABLES = frozenset({
    "import_batches", "payment_source_rows", "payments",
    "payment_source_status_v1",
})
POLICIES = frozenset({
    ("import_batches", "r311_batch_read"),
    ("payment_source_rows", "r311_source_read"),
    ("payments", "r311_payment_read"),
    ("payment_source_status_v1", "r311_status_read"),
})
ROLES = frozenset({"r311_qa_tenant_a", "r311_qa_tenant_b"})

CATALOG_SQL = r"""
SELECT json_build_object(
    'database',current_database(),
    'tables',(
        SELECT COALESCE(json_agg(json_build_object(
            'table',c.relname,'rls',c.relrowsecurity,'forced',c.relforcerowsecurity
        )),'[]'::json)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='sbi'
        AND c.relname IN (
            'import_batches','payment_source_rows','payments',
            'payment_source_status_v1'
        ) AND c.relkind IN ('r','p')
    ),
    'policies',(
        SELECT COALESCE(json_agg(json_build_object(
            'table',tablename,'name',policyname,'cmd',cmd,
            'roles',roles,'qual',qual,'with_check',with_check,
            'permissive',permissive
        )),'[]'::json) FROM pg_policies
        WHERE schemaname='sbi'
          AND tablename IN (
             'import_batches','payment_source_rows','payments',
             'payment_source_status_v1'
          )
    ),
    'view_exists',to_regclass('sbi.payment_received_source_v1') IS NOT NULL,
    'invoker_view',COALESCE((
        SELECT 'security_invoker=true'=ANY(c.reloptions)
        FROM pg_class c WHERE c.oid=to_regclass('sbi.payment_received_source_v1')
    ),false),
    'shared_view_select',CASE
        WHEN to_regclass('sbi.payment_received_source_v1') IS NULL
          OR NOT EXISTS(SELECT 1 FROM pg_roles
              WHERE rolname='sbi_r31_ownerqa_report')
        THEN true
        ELSE has_table_privilege(
          'sbi_r31_ownerqa_report',
          'sbi.payment_received_source_v1','SELECT'
        )
    END,
    'map_exists',to_regclass('r311_auth.role_owner_map') IS NOT NULL,
    'function_secure',COALESCE((
        SELECT p.prosecdef AND
          p.proconfig @> ARRAY['search_path=pg_catalog, r311_auth']::text[]
        FROM pg_proc p
        WHERE p.oid=to_regprocedure('r311_auth.current_tenant_uid()')
    ),false),
    'roles',(
        SELECT COALESCE(json_agg(json_build_object(
            'role',rolname,'login',rolcanlogin,'inherit',rolinherit,
            'super',rolsuper,'bypass',rolbypassrls
        )),'[]'::json)
        FROM pg_roles WHERE rolname IN (
          'r311_qa_tenant_a','r311_qa_tenant_b'
        )
    )
)::text;
"""

COUNTS_SQL = r"""
SELECT json_build_object(
    'batches',(SELECT count(*) FROM sbi.import_batches),
    'source_rows',(SELECT count(*) FROM sbi.payment_source_rows),
    'payments',(SELECT count(*) FROM sbi.payments),
    'status',(SELECT count(*) FROM sbi.payment_source_status_v1),
    'expected_batches',(SELECT count(*) FROM sbi.import_batches
        WHERE (owner_uid='r311-synthetic-owner-a'
            AND id='11111111-1111-4111-8111-111111111111'::uuid)
           OR (owner_uid='r311-synthetic-owner-b'
            AND id='22222222-2222-4222-8222-222222222222'::uuid)),
    'expected_rows',(SELECT count(*) FROM sbi.payment_source_rows
        WHERE id IN ('33333333-3333-4333-8333-333333333333'::uuid,
                     '44444444-4444-4444-8444-444444444444'::uuid)),
    'expected_payments',(SELECT count(*) FROM sbi.payments
        WHERE (id='55555555-5555-4555-8555-555555555555'::uuid
               AND credit_paise=11800)
           OR (id='66666666-6666-4666-8666-666666666666'::uuid
               AND credit_paise=35700)),
    'expected_status',(SELECT count(*) FROM sbi.payment_source_status_v1
        WHERE source_row_id IN (
             '33333333-3333-4333-8333-333333333333'::uuid,
             '44444444-4444-4444-8444-444444444444'::uuid)),
    'map_rows', (SELECT count(*) FROM r311_auth.role_owner_map),
    'map_exact', (SELECT count(*) FROM r311_auth.role_owner_map WHERE
       (db_role='r311_qa_tenant_a'
        AND owner_uid='r311-synthetic-owner-a')
       OR (db_role='r311_qa_tenant_b'
        AND owner_uid='r311-synthetic-owner-b'))
)::text;
"""

ROLE_SQL = r"""
SELECT json_build_object(
    'database',current_database(),
    'role',session_user,
    'uid_ok',r311_auth.current_tenant_uid()=
        CASE WHEN session_user='r311_qa_tenant_a'
             THEN 'r311-synthetic-owner-a'
             ELSE 'r311-synthetic-owner-b' END,
    'all_rls',row_security_active('sbi.import_batches')
        AND row_security_active('sbi.payment_source_rows')
        AND row_security_active('sbi.payments')
        AND row_security_active('sbi.payment_source_status_v1'),
    'batches',(SELECT count(*) FROM sbi.import_batches),
    'source_rows',(SELECT count(*) FROM sbi.payment_source_rows),
    'payments',(SELECT count(*) FROM sbi.payments),
    'statuses',(SELECT count(*) FROM sbi.payment_source_status_v1),
    'view_rows',(SELECT count(*) FROM sbi.payment_received_source_v1),
    'foreign_batches',(SELECT count(*) FROM sbi.import_batches WHERE owner_uid<>
        CASE WHEN session_user='r311_qa_tenant_a'
             THEN 'r311-synthetic-owner-a'
             ELSE 'r311-synthetic-owner-b' END)
)::text;
"""


def query_as_superuser(dbname, sql):
    # Never log raw stdout/stderr; each query returns one JSON object or fails.
    script = "BEGIN READ ONLY;\n" + sql + "\nCOMMIT;\n"
    proc = subprocess.run(
        ["sudo", "-n", "docker", "exec", "-i", EXPECTED_PG,
         "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", dbname],
        input=script, capture_output=True, text=True,
        timeout=35, check=False,
    )
    if proc.returncode:
        raise RuntimeError("READONLY_PSQL_FAILED")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("READONLY_RESULT_SHAPE")
    obj = json.loads(lines[0])
    if type(obj) is not dict:
        raise RuntimeError("READONLY_RESULT_TYPE")
    return obj


def role_read(role):
    if role not in ROLES:
        raise RuntimeError("UNAPPROVED_ROLE")
    script = ("SET SESSION AUTHORIZATION " + role + ";\n"
              "BEGIN READ ONLY;\n" + ROLE_SQL
              + "\nCOMMIT;\nRESET SESSION AUTHORIZATION;\n")
    proc = subprocess.run(
        ["sudo", "-n", "docker", "exec", "-i", EXPECTED_PG,
         "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", CLONE],
        input=script, capture_output=True, text=True,
        timeout=35, check=False,
    )
    if proc.returncode:
        raise RuntimeError("READONLY_ROLE_SESSION_FAILED")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("ROLE_RESULT_SHAPE")
    return json.loads(lines[0])


def catalog_complete(catalog):
    tables = catalog.get("tables", [])
    if (type(tables) is not list or len(tables) != 4
            or {x.get("table") for x in tables} != SOURCE_TABLES
            or not all(x.get("rls") is True and x.get("forced") is True
                       for x in tables)):
        return False
    policies = catalog.get("policies", [])
    if (type(policies) is not list or len(policies) != 4
            or {(x.get("table"), x.get("name")) for x in policies} != POLICIES):
        return False
    for policy in policies:
        qual = policy.get("qual")
        if (policy.get("cmd") != "SELECT"
                or policy.get("permissive") != "PERMISSIVE"
                or set(policy.get("roles", [])) != ROLES
                or type(qual) is not str
                or "r311_auth.current_tenant_uid()" not in qual
                or policy.get("with_check") is not None):
            return False
    roles = catalog.get("roles", [])
    if (type(roles) is not list or len(roles) != 2
            or {x.get("role") for x in roles} != ROLES
            or any(x.get("login") is not False
                   or x.get("inherit") is not False
                   or x.get("super") is not False
                   or x.get("bypass") is not False for x in roles)):
        return False
    return (
        catalog.get("database") == CLONE
        and catalog.get("invoker_view") is True
        and catalog.get("shared_view_select") is False
        and catalog.get("map_exists") is True
        and catalog.get("function_secure") is True
    )


def known_fixture(counts):
    return (
        all(counts.get(k) == 2 for k in (
            "batches", "source_rows", "payments", "status",
            "expected_batches", "expected_rows", "expected_payments",
            "expected_status", "map_rows", "map_exact"
        ))
    )


def checked_role_result(record, role):
    return (
        type(record) is dict
        and record.get("database") == CLONE
        and record.get("role") == role
        and record.get("uid_ok") is True
        and record.get("all_rls") is True
        and all(record.get(field) == 1 for field in (
            "batches", "source_rows", "payments", "statuses", "view_rows"
        ))
        and record.get("foreign_batches") == 0
    )


def main():
    print("=== DB-R31.11 EXISTING CLONE READ-ONLY RESUME ===", flush=True)
    if (PG != EXPECTED_PG or QA_DB != EXPECTED_QA
            or STAGE != EXPECTED_STAGE):
        print("STOP=DB_R31_11_AUDIT_RUNTIME_IDENTITY_CHANGED", flush=True)
        return 2
    preflight()
    # The preflight pins container image and private network. Avoid bypassing it.
    dbs = docker("exec", EXPECTED_PG, "psql", "-X", "-qAt",
                 "-U", "postgres", "-d", "postgres", "-c",
                 "SELECT count(*) FROM pg_database WHERE datname='" + CLONE + "'")
    if dbs != "1":
        print("DB_R31_11_CLONE_RESUME=MISSING_OR_AMBIGUOUS_NO_CREATION",
              flush=True)
        return 2
    print("DB_R31_11_EXISTING_CLONE=FOUND_READONLY", flush=True)
    catalog = query_as_superuser(CLONE, CATALOG_SQL)
    tables = catalog.get("tables", [])
    if (len(tables) != 4
            or {t.get("table") for t in tables} != SOURCE_TABLES):
        print("DB_R31_11_CLONE_RESUME=INCOMPLETE_SCHEMA_REVIEW_REQUIRED",
              flush=True)
        return 2
    if not catalog_complete(catalog):
        print("DB_R31_11_CLONE_RESUME=SCHEMA_PRESENT_RLS_NOT_CERTIFIED",
              flush=True)
        return 2
    print("DB_R31_11_CLONE_RLS_CATALOG=PASS_RESTRICTED_POLICY_SHAPE",
          flush=True)
    counts = query_as_superuser(CLONE, COUNTS_SQL)
    if all(counts.get(k) == 0 for k in (
        "batches", "source_rows", "payments", "status"
    )):
        print("DB_R31_11_CLONE_RESUME=RLS_MIGRATED_EMPTY_NO_ISOLATION_FIXTURE",
              flush=True)
        return 2
    if not known_fixture(counts):
        print("DB_R31_11_CLONE_RESUME=UNKNOWN_ROWS_NO_TEST_EXECUTION",
              flush=True)
        return 2
    print("DB_R31_11_SYNTHETIC_FIXTURE=EXACT_TWO_OWNERS", flush=True)
    for role in sorted(ROLES):
        if not checked_role_result(role_read(role), role):
            print("DB_R31_11_CLONE_ROLE_READS=BLOCKED_CROSS_OWNER_OR_UNEXPECTED",
                  flush=True)
            return 2
    print("DB_R31_11_CLONE_ROLE_READS=PASS_BIDIRECTIONAL_READONLY",
          flush=True)
    print("DB_R31_11_ORIGINAL_QA_AND_PRODUCTION_WRITES=NONE_BY_AUDIT",
          flush=True)
    print("DB_R31_11_FIREBASE_TWO_REAL_USERS=NOT_TESTED_BY_AUDIT", flush=True)
    print("DB_R31_11_EXTERNAL_HTTPS_E2E=NOT_TESTED_BY_AUDIT", flush=True)
    print("DB_R31_11_RUNTIME_RLS_ADAPTER=NOT_CONNECTED", flush=True)
    print("DB_R31_11_RELEASE_STATUS=SECURITY_QA_ONLY_PRODUCTION_BLOCKED",
          flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_11_READONLY_CLONE_AUDIT_UNAVAILABLE", flush=True)
        raise SystemExit(2)
