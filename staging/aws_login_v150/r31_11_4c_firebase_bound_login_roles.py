#!/usr/bin/env python3
"""R31.11.4C: Firebase-approved two-tenant read-only LOGIN provisioning.

Default: READ-ONLY PLAN, NO FINANCIAL WRITES. --prepare-users securely verifies
two existing, distinct, non-admin Firebase test identities via Firebase Admin
and stores a mode-0600 LOCAL receipt (never credentials or token). It does not
create Firebase users or alter claims.

--apply requires an explicit separate QA-only approval and re-verifies both
users. Creates two least-privileged password-authenticated PostgreSQL roles
plus exactly two protected session_user -> Firebase UID mappings in the
already verified isolated R31.11.4 database. Passwords are randomly generated,
delivered via stdin to psql, and stored ONLY in chmod-0600 mode files for the
unprivileged stage API UID. No Caddy, staging deployment, or financial Apply.
"""
from __future__ import annotations

import argparse
from contextlib import suppress
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory

import r31_11_4b_schema_only_runner as schema
import r31_11_4a_isolated_postgres_provision as infra

DB = "sbi_r31_11_4_auth_qa_20261126"
PG = "sbi-r3114-private-postgres"
PROJECT = "meghraj-reconciliation"
MANIFEST_DIR = Path("/home/ubuntu/sbi-r3114c-firebase-approval")
MANIFEST = MANIFEST_DIR / "two-approved-accounts.json"
SECRET_DIR = Path("/home/ubuntu/sbi-r3114c-app-secrets")
APP_UID = 10001
APP_GID = 10001
APPROVE = "R3114C_TWO_VERIFIED_TEST_USERS_QA_ONLY"
ROLES = ("r3113_login_a", "r3113_login_b")
GROUPS = ("r311_qa_tenant_a", "r311_qa_tenant_b")
UID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
EMAIL_RE = re.compile(r"[^@\s]{1,100}@[^@\s]{1,180}\Z")
EXPECTED_DB = "sbi_r31_11_4_auth_qa_20261126"


class ProvisionBlocked(RuntimeError):
    """No sensitive information or raw database/Firebase error in exception."""


def _private_text(path, maxbytes=8192):
    if path.is_symlink() or not path.is_file():
        raise ProvisionBlocked("MISSING_OR_LINKED_PRIVATE_APPROVAL")
    details = path.stat()
    if (details.st_uid != os.geteuid() or
            stat.S_IMODE(details.st_mode) != 0o600 or
            not 1 <= details.st_size <= maxbytes):
        raise ProvisionBlocked("PRIVATE_APPROVAL_FILE_PERMISSIONS")
    return path.read_text("utf-8")


def _make_file(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _admin_api():
    """Only existing ADC for the EXACT dashboard project; never API key login."""
    # dashboard_sessions has the authoritative project constant.
    path = Path(__file__).resolve().parents[2] / "dashboard_source"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        import dashboard_sessions as sessions
        from firebase_admin import auth
        if sessions.PROJECT != PROJECT:
            raise ProvisionBlocked("FIREBASE_PROJECT_MISMATCH")
        app = sessions.firebase_app()
        if app.project_id != PROJECT:
            raise ProvisionBlocked("ADMIN_SDK_PROJECT_MISMATCH")
    except ProvisionBlocked:
        raise
    except Exception:
        raise ProvisionBlocked("FIREBASE_ADMIN_NOT_AVAILABLE") from None
    return auth, app


def _assert_user(user, expected_email=None, expected_uid=None):
    uid = getattr(user, "uid", None)
    email = getattr(user, "email", None)
    claims = getattr(user, "custom_claims", None) or {}
    if (type(uid) is not str or UID_RE.fullmatch(uid) is None
            or type(email) is not str or EMAIL_RE.fullmatch(email) is None
            or getattr(user, "disabled", True) is not False
            or getattr(user, "email_verified", False) is not True
            or type(claims) is not dict
            or claims.get("dil_dashboard") is not True
            or claims.get("dil_admin") is True
            or (expected_uid is not None and uid != expected_uid)
            or (expected_email is not None and
                email.casefold() != expected_email.casefold())):
        raise ProvisionBlocked("FIREBASE_TEST_ACCOUNT_NOT_APPROVED")
    return {"uid": uid, "email": email.casefold()}


def _verify_admin_pair(records, *, api=None):
    if api is None:
        api = _admin_api()
    auth, app = api
    users = []
    for rec in records:
        if type(rec) is not dict or set(rec) != {"db_role", "uid", "email"}:
            raise ProvisionBlocked("APPROVAL_RECORD_INVALID")
        if rec["db_role"] != ROLES[len(users)]:
            raise ProvisionBlocked("APPROVAL_ROLE_ORDER_INVALID")
        try:
            user = auth.get_user(rec["uid"], app=app)
        except Exception:
            raise ProvisionBlocked("APPROVED_FIREBASE_USER_NOT_VERIFIABLE") from None
        users.append(_assert_user(user,rec["email"],rec["uid"]))
    if len(users) != 2 or users[0]["uid"] == users[1]["uid"] \
            or users[0]["email"] == users[1]["email"]:
        raise ProvisionBlocked("TWO_DISTINCT_FIREBASE_USERS_REQUIRED")
    return users


def _approved_users():
    try:
        doc = json.loads(_private_text(MANIFEST))
    except (UnicodeError, ValueError, OSError):
        raise ProvisionBlocked("APPROVAL_RECEIPT_INVALID") from None
    if (type(doc) is not dict
            or set(doc) != {"version", "project", "test_users"}
            or doc["version"] != 1 or doc["project"] != PROJECT
            or type(doc["test_users"]) is not list
            or len(doc["test_users"]) != 2):
        raise ProvisionBlocked("APPROVAL_RECEIPT_INVALID")
    _verify_admin_pair(doc["test_users"])
    return doc["test_users"]


def prepare_users(*, emails=None, api=None):
    # A *local* receipt is not independent approval, but blocks accidental
    # provisioning from merely a single / unapproved Firebase identity.
    if MANIFEST_DIR.exists() or MANIFEST_DIR.is_symlink():
        raise ProvisionBlocked("PRIVATE_APPROVAL_ALREADY_EXISTS_REVIEW")
    if emails is None:
        emails = (
            getpass.getpass("Existing approved Firebase QA email A (hidden): "),
            getpass.getpass("Existing approved Firebase QA email B (hidden): "),
        )
    if (len(emails) != 2 or any(type(e) is not str
            or EMAIL_RE.fullmatch(e) is None for e in emails)
            or emails[0].casefold() == emails[1].casefold()):
        raise ProvisionBlocked("TWO_DISTINCT_TEST_EMAILS_REQUIRED")
    auth, app = api if api is not None else _admin_api()
    records = []
    for role,email in zip(ROLES,emails):
        try:
            user = auth.get_user_by_email(email, app=app)
        except Exception:
            raise ProvisionBlocked("APPROVED_FIREBASE_USER_NOT_VERIFIABLE") from None
        u = _assert_user(user,email)
        records.append({"db_role":role, "uid":u["uid"], "email":u["email"]})
    _verify_admin_pair(records,api=(auth,app))
    MANIFEST_DIR.mkdir(mode=0o700)
    os.chmod(MANIFEST_DIR,0o700)
    data = json.dumps({"version":1,"project":PROJECT,
                       "test_users":records},separators=(",",":"))
    _make_file(MANIFEST,data.encode())
    if _private_text(MANIFEST) != data:
        raise ProvisionBlocked("LOCAL_APPROVAL_WRITE_VERIFY_FAILED")
    print("DB_R31_11_4C_FIREBASE_TWO_DISTINCT_TEST_USERS=PASS_ADMIN_READONLY",
          flush=True)
    print("DB_R31_11_4C_PRIVATE_ACCOUNT_RECEIPT=MODE0600_NO_TOKENS",
          flush=True)


def _db_read(sql):
    try:
        run = subprocess.run(
            ["sudo","-n","docker","exec","-i",PG,
             "psql","-X","-qAt","-v","ON_ERROR_STOP=1",
             "-U","postgres","-d",DB],
            input=sql.encode(),capture_output=True,timeout=35,check=False,
        )
    except (OSError,subprocess.TimeoutExpired):
        raise ProvisionBlocked("PRIVATE_DB_UNAVAILABLE") from None
    if run.returncode:
        raise ProvisionBlocked("PRIVATE_DB_READ_REFUSED")
    return run.stdout.decode("utf-8",errors="strict").strip()


def _db_apply(sql):
    # The SQL contains generated private passwords: ONLY stdin, NEVER argv,
    # GitHub, Caddy, Docker env, terminal history or process output.
    try:
        run = subprocess.run(
            ["sudo","-n","docker","exec","-i",PG,
             "psql","-X","-qAt","-v","ON_ERROR_STOP=1",
             "-U","postgres","-d",DB],
            input=sql.encode(),capture_output=True,timeout=65,check=False,
        )
    except (OSError,subprocess.TimeoutExpired):
        raise ProvisionBlocked("PRIVATE_ROLE_BOOTSTRAP_UNAVAILABLE") from None
    if run.returncode or run.stdout.strip() != b"R3114C_PRIVATE_ROLE_MAP_COMMITTED":
        raise ProvisionBlocked("PRIVATE_ROLE_BOOTSTRAP_NOT_CONFIRMED")


def _catalog_counts():
    query = """
    BEGIN READ ONLY;
    SELECT json_build_object(
      'db',current_database(),
      'role_count',(SELECT count(*) FROM pg_roles
         WHERE rolname IN ('r3113_login_a','r3113_login_b')),
      'group_count',(SELECT count(*) FROM pg_roles
         WHERE rolname IN ('r311_qa_tenant_a','r311_qa_tenant_b')
         AND NOT rolcanlogin AND NOT rolinherit AND NOT rolsuper
         AND NOT rolbypassrls),
      'maps',(SELECT count(*) FROM r311_auth.role_owner_map),
      'data_rows',(
        (SELECT count(*) FROM sbi.import_batches)
        +(SELECT count(*) FROM sbi.payment_source_rows)
        +(SELECT count(*) FROM sbi.payments)
        +(SELECT count(*) FROM sbi.payment_source_status_v1)),
      'policy_count',(SELECT count(*) FROM pg_policies
         WHERE schemaname='sbi' AND cmd='SELECT'),
      'forced_rls',(SELECT count(*) FROM pg_class c JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='sbi'
        AND c.relname IN ('import_batches','payment_source_rows',
                          'payments','payment_source_status_v1')
        AND c.relrowsecurity AND c.relforcerowsecurity)
    )::text;
    COMMIT;
    """
    try:
        data=json.loads(_db_read(query))
    except (ValueError,UnicodeError):
        raise ProvisionBlocked("PRIVATE_CATALOG_INVALID") from None
    if (type(data) is not dict or data.get("db") != DB
            or any(type(data.get(x)) is not int for x in
                ("role_count","group_count","maps","data_rows",
                 "policy_count","forced_rls"))):
        raise ProvisionBlocked("PRIVATE_CATALOG_INVALID")
    return data


def _schema_is_ready(c):
    return (c["role_count"] == 0 and c["group_count"] == 2
            and c["maps"] == 0 and c["data_rows"] == 0
            and c["policy_count"] == 4 and c["forced_rls"] == 4)


def _quote_uid(uid):
    if type(uid) is not str or UID_RE.fullmatch(uid) is None:
        raise ProvisionBlocked("UNSAFE_FIREBASE_UID")
    return "'" + uid + "'"


def _quote_password(pwd):
    if (type(pwd) is not str or not 40 <= len(pwd) <= 120
            or re.fullmatch(r"[A-Za-z0-9_-]+",pwd) is None):
        raise ProvisionBlocked("UNSAFE_GENERATED_PASSWORD")
    return "'" + pwd + "'"


def build_provision_sql(records, passwords):
    if (len(records) != 2 or len(passwords) != 2
            or [r["db_role"] for r in records] != list(ROLES)
            or len({r["uid"] for r in records}) != 2
            or len(set(passwords)) != 2):
        raise ProvisionBlocked("QA_BOOTSTRAP_INPUT_INVALID")
    uid_a,uid_b=(_quote_uid(r["uid"]) for r in records)
    pw_a,pw_b=(_quote_password(p) for p in passwords)
    # Hardcoded identifiers; escaped bounded values; no raw user SQL.
    return f"""
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='40s';
DO $guard$
BEGIN
 IF current_database()<>'{DB}'
    OR current_user<>'postgres' OR session_user<>'postgres'
    OR current_setting('server_version_num')::int < 160000
    OR current_setting('server_version_num')::int >= 170000
    OR to_regclass('r311_auth.role_owner_map') IS NULL
    OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN
        ('r3113_login_a','r3113_login_b'))
    OR EXISTS (SELECT 1 FROM r311_auth.role_owner_map)
    OR EXISTS (SELECT 1 FROM sbi.import_batches)
    OR EXISTS (SELECT 1 FROM sbi.payment_source_rows)
    OR EXISTS (SELECT 1 FROM sbi.payments)
    OR EXISTS (SELECT 1 FROM sbi.payment_source_status_v1)
    OR (SELECT count(*) FROM pg_policies
        WHERE schemaname='sbi' AND cmd='SELECT')<>4
    OR (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='sbi'
          AND c.relname IN ('import_batches','payment_source_rows',
                            'payments','payment_source_status_v1')
          AND c.relrowsecurity AND c.relforcerowsecurity)<>4
 THEN RAISE EXCEPTION 'R3114C_DATABASE_STATE_NOT_APPROVED'; END IF;
END $guard$;
CREATE ROLE r3113_login_a LOGIN INHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD {pw_a};
CREATE ROLE r3113_login_b LOGIN INHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD {pw_b};
GRANT r311_qa_tenant_a TO r3113_login_a
  WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;
GRANT r311_qa_tenant_b TO r3113_login_b
  WITH INHERIT TRUE, SET FALSE, ADMIN FALSE;
INSERT INTO r311_auth.role_owner_map(db_role,owner_uid) VALUES
 ('r3113_login_a',{uid_a}),('r3113_login_b',{uid_b});
-- This is a wholly dedicated private QA Postgres cluster with no other app
-- databases. Remove inherited PUBLIC CONNECT to unrelated cluster databases.
REVOKE CONNECT ON DATABASE postgres,template1 FROM PUBLIC;
REVOKE CONNECT ON DATABASE {DB} FROM PUBLIC;
GRANT CONNECT ON DATABASE {DB} TO r3113_login_a,r3113_login_b;
DO $proof$
DECLARE n int;
BEGIN
 SELECT count(*) INTO n FROM pg_auth_members m
 JOIN pg_roles member ON member.oid=m.member
 JOIN pg_roles granted ON granted.oid=m.roleid
 WHERE ((member.rolname='r3113_login_a' AND granted.rolname='r311_qa_tenant_a')
     OR (member.rolname='r3113_login_b' AND granted.rolname='r311_qa_tenant_b'))
   AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option;
 IF n<>2
    OR (SELECT count(*) FROM r311_auth.role_owner_map)<>2
    OR (SELECT count(DISTINCT owner_uid) FROM r311_auth.role_owner_map)<>2
    OR (SELECT count(*) FROM pg_roles
        WHERE rolname IN ('r3113_login_a','r3113_login_b')
        AND rolcanlogin AND rolinherit AND NOT rolsuper
        AND NOT rolbypassrls AND NOT rolcreatedb
        AND NOT rolcreaterole)<>2
 THEN RAISE EXCEPTION 'R3114C_ROLE_MAPPING_PROOF_FAILED'; END IF;
END $proof$;
COMMIT;
SELECT 'R3114C_PRIVATE_ROLE_MAP_COMMITTED';
"""


def _secret_bundle(records,passwords):
    # File paths match the *non-root* private R31.11.4 candidate adapter.
    if SECRET_DIR.exists() or SECRET_DIR.is_symlink():
        raise ProvisionBlocked("QA_APP_SECRET_BUNDLE_ALREADY_EXISTS")
    SECRET_DIR.mkdir(mode=0o700)
    os.chmod(SECRET_DIR,0o700)
    bindings=[]
    for i,(record,password) in enumerate(zip(records,passwords)):
        suffix = "a" if i == 0 else "b"
        path=SECRET_DIR/f"r3114-owner-{suffix}.env"
        secret_path=f"/run/secrets/r3114-owner-{suffix}.env"
        payload=(
            f"PGHOST={PG}\nPGPORT=5432\nPGDATABASE={DB}\n"
            f"PGUSER={ROLES[i]}\nPGPASSWORD={password}\n"
        ).encode()
        _make_file(path,payload)
        bindings.append({
            "firebase_uid":record["uid"],"pg_login_role":ROLES[i],
            "secret_path":secret_path,
        })
    mapping={"version":1,"database":DB,"bindings":bindings}
    _make_file(SECRET_DIR/"r3114-tenant-bindings.json",
               json.dumps(mapping,separators=(",",":")).encode())
    return [SECRET_DIR/f"r3114-owner-{x}.env" for x in ("a","b")] + [
        SECRET_DIR/"r3114-tenant-bindings.json"]


def _seal_app_secrets(paths):
    # The candidate Dockerfile explicitly pins USER 10001:10001.
    dockerfile=Path(__file__).with_name("Dockerfile.r31_11_4_private_candidate")
    if "USER 10001:10001" not in dockerfile.read_text("utf-8"):
        raise ProvisionBlocked("STAGING_APP_RUNTIME_UID_UNVERIFIED")
    paths_to_seal = list(paths) + [SECRET_DIR]
    for item in paths_to_seal:
        run=subprocess.run(
            ["sudo","-n","chown","--",f"{APP_UID}:{APP_GID}",str(item)],
            capture_output=True,timeout=15,check=False)
        if run.returncode:
            raise ProvisionBlocked("QA_APP_SECRET_OWNER_SET_FAILED")
    for path in paths:
        st=path.stat()
        if path.is_symlink() or not stat.S_ISREG(st.st_mode) \
                or stat.S_IMODE(st.st_mode)!=0o600 \
                or st.st_uid!=APP_UID or st.st_gid!=APP_GID:
            raise ProvisionBlocked("QA_APP_SECRET_MODE_OR_OWNER_INVALID")
    st=SECRET_DIR.stat()
    if (stat.S_IMODE(st.st_mode)!=0o700 or st.st_uid!=APP_UID
            or st.st_gid!=APP_GID):
        raise ProvisionBlocked("QA_APP_SECRET_DIR_OWNER_INVALID")


def _verify_after(records):
    from r31_11_4_private_runtime_readiness import _restricted_role_state
    check=_restricted_role_state()
    # Do not trust catalog counts alone. Explicitly verify two distinct
    # configured UIDs against protected mapping without exposing UIDs.
    expected=tuple(r["uid"] for r in records)
    check_count=_db_read(f"""
    BEGIN READ ONLY;
    SELECT count(*) FROM r311_auth.role_owner_map WHERE
      (db_role='r3113_login_a' AND owner_uid={_quote_uid(expected[0])}) OR
      (db_role='r3113_login_b' AND owner_uid={_quote_uid(expected[1])});
    COMMIT;
    """)
    if (check_count!="2" or check["login_roles"] != 2
            or check["membership_pairs"] != 2
            or check["all_memberships"] != 2
            or check["group_roles"] != 2
            or check["distinct_owner_mappings"] != 2
            or check["raw_mapping_readers"] != 0
            or check["forced_rls"] != 4
            or check["invoker_view"] != 1
            or check["writer_grants"] != 0):
        raise ProvisionBlocked("QA_POST_PROVISION_ROLE_CATALOG_INVALID")


def apply_roles(records, caddy_before):
    # Never overwrite; if interrupted, stop for independent review.
    if SECRET_DIR.exists() or SECRET_DIR.is_symlink():
        raise ProvisionBlocked("QA_APP_SECRET_BUNDLE_ALREADY_EXISTS")
    # Validate no input is echoed in subprocess argv or stdout.
    passwords=(secrets.token_urlsafe(48),secrets.token_urlsafe(48))
    files=_secret_bundle(records,passwords)
    _db_apply(build_provision_sql(records,passwords))
    _seal_app_secrets(files)
    _verify_after(records)
    if infra.caddy_fingerprint()!=caddy_before:
        raise ProvisionBlocked("CADDY_CONFIG_CHANGED")
    infra.preflight()
    print("DB_R31_11_4C_RESTRICTED_PASSWORD_LOGINS=PASS_TWO_REAL_USERS",
          flush=True)
    print("DB_R31_11_4C_DB_SESSION_USER_UID_MAPPING=PASS_TWO_DISTINCT",
          flush=True)
    print("DB_R31_11_4C_APP_SECRETS=MODE0600_UID10001_NOT_DEPLOYED",
          flush=True)
    print("DB_R31_11_4C_DML_PRIVILEGES=DENIED",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-users",action="store_true",
                        help="Read-only Firebase account verification; save local 0600 receipt")
    parser.add_argument("--apply",action="store_true",
                        help="Create two QA-only password roles; requires exact approval")
    parser.add_argument("--approve",default="")
    opts=parser.parse_args(argv)
    print("=== DB-R31.11.4C FIREBASE-BOUND LOGIN ROLE READINESS ===",flush=True)
    try:
        if opts.prepare_users and opts.apply:
            raise ProvisionBlocked("MUTUALLY_EXCLUSIVE_OPERATIONS")
        if opts.prepare_users:
            prepare_users()
            return 0
        caddy_before=schema._guarded_preflight()
        if not schema._is_schema_only(schema._state()):
            raise ProvisionBlocked("R3114B_SCHEMA_ONLY_NOT_VERIFIED")
        if not schema._all_new_source_tables_empty():
            raise ProvisionBlocked("QA_DATA_OR_MAPPING_ALREADY_PRESENT")
        catalog=_catalog_counts()
        if not _schema_is_ready(catalog):
            raise ProvisionBlocked("QA_ALREADY_MIGRATED_OR_UNEXPECTED")
        print("DB_R31_11_4C_RLS_SCHEMA=PASS_4B_READONLY",flush=True)
        print("DB_R31_11_4C_ROLE_MAPPING=EMPTY_NO_LOGINS",flush=True)
        if not MANIFEST.exists() and not MANIFEST.is_symlink():
            print("DB_R31_11_4C_TWO_APPROVED_FIREBASE_USERS=PENDING_LOCAL_VERIFICATION",
                  flush=True)
            if opts.apply:
                raise ProvisionBlocked("TWO_VERIFIED_USERS_REQUIRED")
            print("DB_R31_11_4C_MODE=READONLY_PLAN_ONLY_NO_CHANGES",flush=True)
            return 0
        approved=_approved_users()  # real Admin SDK get_user() twice
        print("DB_R31_11_4C_TWO_APPROVED_FIREBASE_USERS=PASS_READONLY_ADMIN",
              flush=True)
        if not opts.apply:
            print("DB_R31_11_4C_MODE=READONLY_PLAN_ONLY_NO_CHANGES",flush=True)
            return 0
        if opts.approve != APPROVE:
            raise ProvisionBlocked("EXPLICIT_TWO_USER_QA_APPROVAL_REQUIRED")
        print("DB_R31_11_4C_MODE=AUTHORIZED_PRIVATE_QA_ROLE_CREATION",
              flush=True)
        apply_roles(approved,caddy_before)
        return 0
    except (ProvisionBlocked, schema.BootstrapBlocked, infra.ProvisionBlocked,
            ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_11_4C_FALLBACK_DENIED_MANUAL_REVIEW_REQUIRED",
              flush=True)
        return 2
    finally:
        print("DB_R31_11_4C_FIREBASE_ACCOUNTS_CREATED=NONE",flush=True)
        print("DB_R31_11_4C_RUNTIME_ADAPTER=NOT_DEPLOYED",flush=True)
        print("DB_R31_11_4C_EXTERNAL_MTLS_HTTPS=PENDING",flush=True)
        print("DB_R31_11_4C_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4C_R3112_FINANCIAL_INTEGRATION=QUARANTINED",flush=True)
        print("DB_R31_11_4C_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING",
              flush=True)


if __name__=="__main__":
    raise SystemExit(main())
