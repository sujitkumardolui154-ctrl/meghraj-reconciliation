#!/usr/bin/env python3
"""R31 protected Firebase Admin -> QA PG role mapping identity-only audit.

Read-only. No tokens/passwords, no login retries, no DB mutations or secrets
printed. Enter the TWO previously tested QA login emails locally with hidden
prompts to attest which accounts were used in the prior HTTPS test.
"""
from __future__ import annotations
import argparse
import getpass
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
AWS_QA=ROOT/"staging"/"aws_login_v150"
sys.path.insert(0,str(AWS_QA))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_postgres_tenant_rls_catalog_readonly as catalog

ROLE_NAMES=("r3113_login_a","r3113_login_b")
EMAIL_RE=re.compile(r"[^@\s]{1,100}@[^@\s]{1,180}\Z")

class Blocked(Exception):
    pass

def operator_emails():
    if not sys.stdin.isatty():
        raise Blocked("INTERACTIVE_TERMINAL_REQUIRED")
    print("Enter the SAME two QA emails used in the recent successful HTTPS test.")
    print("Inputs are hidden locally; no emails, UIDs, passwords or tokens printed.")
    emails=[]
    for i in (1,2):
        email=getpass.getpass(f"Previously tested QA employee {i} email (hidden): ").strip().casefold()
        if len(email)>254 or not EMAIL_RE.fullmatch(email):
            raise Blocked("QA_EMAIL_FORMAT_INVALID")
        emails.append(email)
    if emails[0]==emails[1]:
        raise Blocked("QA_IDENTITIES_NOT_DISTINCT")
    return emails

def compare_records(records,emails,role_map):
    if type(records) is not list or len(records)!=2 or type(role_map) is not dict:
        return "REVIEW_REQUIRED"
    expected={}
    approved_emails=set()
    for rec in records:
        if type(rec) is not dict or set(rec)!={"db_role","uid","email"}:
            return "REVIEW_REQUIRED"
        role,uid,email=rec["db_role"],rec["uid"],rec["email"]
        if (type(role) is not str or role not in ROLE_NAMES
            or type(uid) is not str or not uid
            or type(email) is not str or not EMAIL_RE.fullmatch(email)):
            return "REVIEW_REQUIRED"
        if role in expected or email.casefold() in approved_emails:
            return "REVIEW_REQUIRED"
        expected[role]=uid
        approved_emails.add(email.casefold())
    if set(expected)!=set(ROLE_NAMES) or len(set(expected.values()))!=2:
        return "REVIEW_REQUIRED"
    if set(emails)!=approved_emails:
        return "QA_HTTPS_EMPLOYEE_PAIR_NOT_IN_APPROVAL_RECORD"
    if expected!=role_map:
        return "QA_DB_OWNER_MAPPING_MISMATCH"
    return "PASS_APPROVED_PAIR_MATCHES_PROTECTED_DB_MAP"

def read_role_map():
    # Aggregates only privileged *QA* role mapping names/UIDs into local RAM.
    # Never logs or prints raw psql output, identifiers, host state or errors.
    sql=("BEGIN READ ONLY; "
         "SELECT db_role::text,owner_uid FROM r311_auth.role_owner_map "
         "ORDER BY db_role; COMMIT;")
    try:
        p=subprocess.run(
            ["sudo","-n","docker","exec",catalog.PG,"psql","-X","-qAt",
             "-v","ON_ERROR_STOP=1","-U","postgres","-d",catalog.DB,
             "-c",sql],
            capture_output=True,text=True,timeout=30,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Blocked("QA_DATABASE_MAP_QUERY_UNAVAILABLE") from None
    if p.returncode:
        raise Blocked("QA_DATABASE_MAP_QUERY_UNAVAILABLE")
    lines=[x for x in p.stdout.splitlines() if x.startswith("r3113_login_")]
    if len(lines)!=2:
        raise Blocked("QA_DATABASE_MAP_COUNT_UNEXPECTED")
    result={}
    for line in lines:
        pieces=line.split("|")
        if len(pieces)!=2 or pieces[0] not in ROLE_NAMES or not pieces[1]:
            raise Blocked("QA_DATABASE_MAP_FORMAT_INVALID")
        if pieces[0] in result:
            raise Blocked("QA_DATABASE_MAP_ROLE_DUPLICATE")
        result[pieces[0]]=pieces[1]
    return result

def get_current_approved_records():
    # Use the existing R31.11.4C protected local approval receipt and real
    # Firebase Admin read-only get_user() / claims revalidation. This has no
    # password or ID-token sign-in step and no write operations.
    try:
        import r31_11_4c_firebase_bound_login_roles as approved
        records=approved._approved_users()
    except Exception:
        raise Blocked("QA_FIREBASE_ADMIN_APPROVAL_RECHECK_UNAVAILABLE") from None
    return records

def run(sha):
    print("=== R31 EXISTING-URL FIREBASE TO PG OWNER BINDING READONLY ===")
    try:
        catalog.pinned(sha)
        pg=catalog.inspect("container",catalog.PG)
        net=catalog.inspect("network",catalog.NET)
        if not catalog.topology(pg,net):
            raise Blocked("QA_PRIVATE_POSTGRES_TOPOLOGY_CHANGED")
        state=catalog.database_catalog()
        if catalog.classify(state)!="PASS_RESTRICTED_CATALOG_ONLY":
            raise Blocked("QA_RESTRICTED_ROLE_CATALOG_CHANGED")
    except catalog.Refused:
        raise Blocked("QA_BASELINE_CATALOG_NOT_VERIFIED") from None
    print("R31_BINDING_SOURCE_QA_CATALOG=PASS_PINNED_READONLY")
    emails=operator_emails()
    records=get_current_approved_records()
    role_map=read_role_map()
    verdict=compare_records(records,emails,role_map)
    print("R31_BINDING_APPROVED_FIREBASE_TO_PG="+verdict)
    if verdict!="PASS_APPROVED_PAIR_MATCHES_PROTECTED_DB_MAP":
        raise Blocked("QA_IDENTITY_ROLE_MAPPING_REVIEW_REQUIRED")
    print("R31_BINDING_EMPLOYEE_EMAILS=LOCAL_OPERATOR_ATTESTATION_ONLY")
    print("R31_BINDING_LIVE_HTTPS_IDENTITY_TO_DB=NOT_PROVED_BY_THIS_CHECK")
    print("R31_BINDING_TWO_WAY_RLS_HTTP=NOT_TESTED")
    print("R31_BINDING_NO_DATABASE_CHANGES=PASS_READONLY")
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-sha",required=True)
    args=p.parse_args()
    try:
        status=run(args.source_sha)
    except Blocked as err:
        label=str(err)
        print("STOP=R31_BINDING_"+label if re.fullmatch(r"[A-Z0-9_]{3,90}",label)
              else "STOP=R31_BINDING_REVIEW_REQUIRED")
        status=2
    except (ValueError,TypeError,UnicodeError,OSError):
        print("STOP=R31_BINDING_REVIEW_REQUIRED")
        status=2
    finally:
        print("R31_BINDING_FINANCIAL_APPLY=LOCKED")
        print("R31_BINDING_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(status)
