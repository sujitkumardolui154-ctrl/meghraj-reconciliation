#!/usr/bin/env python3
"""R31 existing-URL owner-scoped PostgreSQL read-only QA catalog preflight.

Only Docker inspection + PostgreSQL BEGIN READ ONLY metadata queries against
the explicitly isolated synthetic QA database. No SQL modifications, no
account tokens, Firebase sign-ins, credentials, Caddy changes or deployments.
PASS for a catalog is NOT live two-owner RLS acceptance via HTTPS.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PG="sbi-r3114-private-postgres"
NET="sbi-r3114-private-isolated"
DB="sbi_r31_11_4_auth_qa_20261126"
TARGET="https://sbi-preview.13-232-241-221.sslip.io/login"

QUERY=r"""
BEGIN READ ONLY;
SELECT json_build_object(
 'db',current_database(),
 'pg16',current_setting('server_version_num')::integer BETWEEN 160000 AND 169999,
 'login_roles', (SELECT count(*) FROM pg_roles WHERE rolname IN
    ('r3113_login_a','r3113_login_b') AND rolcanlogin AND
    NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb),
 'member_pairs', (SELECT count(*) FROM pg_auth_members m JOIN pg_roles a
    ON a.oid=m.member JOIN pg_roles b ON b.oid=m.roleid WHERE
    ((a.rolname='r3113_login_a' AND b.rolname='r311_qa_tenant_a') OR
     (a.rolname='r3113_login_b' AND b.rolname='r311_qa_tenant_b'))
    AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option),
 'all_member_links', (SELECT count(*) FROM pg_auth_members m JOIN pg_roles a
    ON a.oid=m.member WHERE a.rolname IN ('r3113_login_a','r3113_login_b')),
 'mappings', (SELECT count(*) FROM r311_auth.role_owner_map),
 'mapped_distinct', (SELECT count(DISTINCT owner_uid) FROM r311_auth.role_owner_map
    WHERE db_role IN ('r3113_login_a','r3113_login_b')),
 'forced_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname='sbi' AND c.relname IN
    ('import_batches','payment_source_rows','payments','payment_source_status_v1')
    AND c.relrowsecurity AND c.relforcerowsecurity),
 'select_policies', (SELECT count(*) FROM pg_policies
    WHERE schemaname='sbi' AND policyname IN
    ('r311_batch_read','r311_source_read','r311_payment_read','r311_status_read')
    AND cmd='SELECT' AND permissive='PERMISSIVE'),
 'other_policies', (SELECT count(*) FROM pg_policies
    WHERE schemaname='sbi' AND policyname NOT IN
    ('r311_batch_read','r311_source_read','r311_payment_read','r311_status_read')),
 'invoker_view', (SELECT count(*) FROM pg_class c
    WHERE c.oid=to_regclass('sbi.payment_received_source_v1')
    AND 'security_invoker=true'=ANY(c.reloptions)),
 'mapping_readers', (SELECT count(*) FROM pg_roles r
    WHERE r.rolname IN ('r3113_login_a','r3113_login_b') AND
    has_table_privilege(r.oid,'r311_auth.role_owner_map','SELECT')),
 'writer_roles', (SELECT count(*) FROM pg_roles r
    WHERE r.rolname IN ('r3113_login_a','r3113_login_b') AND
    (has_table_privilege(r.oid,'sbi.import_batches','INSERT') OR
     has_table_privilege(r.oid,'sbi.import_batches','UPDATE') OR
     has_table_privilege(r.oid,'sbi.import_batches','DELETE') OR
     has_table_privilege(r.oid,'sbi.payment_source_rows','INSERT') OR
     has_table_privilege(r.oid,'sbi.payment_source_rows','UPDATE') OR
     has_table_privilege(r.oid,'sbi.payment_source_rows','DELETE') OR
     has_table_privilege(r.oid,'sbi.payments','INSERT') OR
     has_table_privilege(r.oid,'sbi.payments','UPDATE') OR
     has_table_privilege(r.oid,'sbi.payments','DELETE') OR
     has_table_privilege(r.oid,'sbi.payment_source_status_v1','INSERT') OR
     has_table_privilege(r.oid,'sbi.payment_source_status_v1','UPDATE') OR
     has_table_privilege(r.oid,'sbi.payment_source_status_v1','DELETE'))),
 'data_rows', (SELECT count(*) FROM sbi.import_batches) +
     (SELECT count(*) FROM sbi.payment_source_rows) +
     (SELECT count(*) FROM sbi.payments) +
     (SELECT count(*) FROM sbi.payment_source_status_v1)
)::text;
COMMIT;
"""

class Refused(Exception):
    pass

def run(args,timeout=25):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Refused("COMMAND_UNAVAILABLE") from None
    if p.returncode:
        raise Refused("READONLY_COMMAND_FAILED")
    return p.stdout

def pinned(sha):
    if re.fullmatch(r"[0-9a-f]{40}",sha) is None:
        raise Refused("SOURCE_SHA_INVALID")
    if run(["git","-C",str(ROOT),"rev-parse","HEAD"]).strip()!=sha:
        raise Refused("SOURCE_SHA_MISMATCH")
    if run(["git","-C",str(ROOT),"status","--porcelain"]).strip():
        raise Refused("SOURCE_WORKTREE_DIRTY")
    try:
        policy=json.loads((ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json").read_text("utf-8"))
    except (OSError,ValueError):
        raise Refused("DEPLOYMENT_POLICY_UNAVAILABLE") from None
    if (policy.get("user_required_url")!=TARGET or
        policy.get("financial_apply")!="LOCKED" or
        policy.get("production_release")!="BLOCKED" or
        policy.get("actual_deployment_performed") is not False):
        raise Refused("DEPLOYMENT_TARGET_OR_LOCK_CHANGED")

def topology(pg,net):
    if (type(pg) is not dict or type(net) is not dict):
        return False
    h=pg.get("HostConfig") or {}
    networks=(pg.get("NetworkSettings") or {}).get("Networks") or {}
    return (pg.get("State",{}).get("Running") is True and
        h.get("Privileged") is False and
        h.get("PortBindings") in (None,{}) and
        set(networks)=={NET} and
        net.get("Internal") is True and net.get("Attachable") is False)

def inspect(kind,name):
    data=json.loads(run(["sudo","-n","docker",kind,"inspect",name]))
    if type(data) is not list or len(data)!=1 or type(data[0]) is not dict:
        raise Refused("QA_DOCKER_METADATA_INVALID")
    return data[0]

def database_catalog():
    sql=run(["sudo","-n","docker","exec","-i",PG,"psql",
             "-X","-qAt","-v","ON_ERROR_STOP=1",
             "-U","postgres","-d",DB,"-c",QUERY],timeout=30)
    lines=[line for line in sql.splitlines() if line.startswith("{") and line.endswith("}")]
    if len(lines)!=1:
        raise Refused("QA_CATALOG_RESULT_INVALID")
    try:
        obj=json.loads(lines[0])
    except ValueError:
        raise Refused("QA_CATALOG_RESULT_INVALID") from None
    return obj

def classify(value):
    if type(value) is not dict or value.get("db")!=DB or value.get("pg16") is not True:
        return "REVIEW_REQUIRED"
    expected={"login_roles":2,"member_pairs":2,"all_member_links":2,
       "mappings":2,"mapped_distinct":2,"forced_tables":4,
       "select_policies":4,"other_policies":0,"invoker_view":1,
       "mapping_readers":0,"writer_roles":0,"data_rows":0}
    if any(type(value.get(k)) is not int or value[k]!=v for k,v in expected.items()):
        return "REVIEW_REQUIRED"
    return "PASS_RESTRICTED_CATALOG_ONLY"

def main(sha):
    print("=== R31 EXISTING-URL POSTGRES TENANT RLS READONLY AUDIT ===",flush=True)
    pinned(sha)
    print("R31_RLS_SOURCE_AND_EXISTING_URL=PASS_PINNED",flush=True)
    pg=inspect("container",PG)
    net=inspect("network",NET)
    if not topology(pg,net):
        raise Refused("QA_POSTGRES_ISOLATION_CHANGED")
    print("R31_RLS_PRIVATE_QA_POSTGRES=PASS_ISOLATED_UNPUBLISHED",flush=True)
    catalog=database_catalog()
    verdict=classify(catalog)
    print("R31_RLS_QA_ROLE_MAPPING_POLICIES="+verdict,flush=True)
    if verdict!="PASS_RESTRICTED_CATALOG_ONLY":
        raise Refused("QA_ROLE_MAPPING_OR_RLS_REVIEW_REQUIRED")
    print("R31_RLS_QA_DATA=ZERO_ROWS_TWO_MAPPINGS",flush=True)
    print("R31_RLS_PREVIOUS_FIREBASE_TWO_USER_HTTPS=OPERATOR_REPORTED_PASS_SEPARATE_TEST",flush=True)
    print("R31_RLS_SAME_TWO_FIREBASE_USERS_BOUND_TO_DB=NOT_VERIFIED",flush=True)
    print("R31_RLS_CROSS_TENANT_HTTPS_A_TO_B=NOT_TESTED",flush=True)
    print("R31_RLS_CROSS_TENANT_HTTPS_B_TO_A=NOT_TESTED",flush=True)
    print("R31_RLS_SYNTHETIC_ROW_BOUNDARY=HISTORICAL_SCOPE_ONLY_NOT_REPLAYED",flush=True)
    print("R31_RLS_REAL_HTTP_ENDPOINT=NOT_DEPLOYED_OR_PROVEN_BY_THIS_AUDIT",flush=True)
    print("R31_RLS_MODE=READONLY_CATALOG_NO_FINANCIAL_DATA",flush=True)
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-sha",required=True)
    args=p.parse_args()
    try:
        code=main(args.source_sha)
    except Refused as exc:
        label=str(exc)
        if not re.fullmatch(r"[A-Z0-9_]{3,90}",label):
            label="AUDIT_REVIEW_REQUIRED"
        print("STOP=R31_RLS_"+label,flush=True)
        code=2
    except (ValueError,TypeError,UnicodeError,OSError):
        print("STOP=R31_RLS_READONLY_AUDIT_REVIEW_REQUIRED",flush=True)
        code=2
    finally:
        print("R31_RLS_FINANCIAL_APPLY=LOCKED",flush=True)
        print("R31_RLS_PRODUCTION_RELEASE=BLOCKED",flush=True)
    raise SystemExit(code)
