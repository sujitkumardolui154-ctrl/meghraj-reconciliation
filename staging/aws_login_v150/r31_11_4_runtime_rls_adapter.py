"""DB-R31.11.4 Firebase-session -> restricted Postgres-login RLS adapter.

Staging QA only, READ ONLY, feature-flagged; intentionally no credentials,
Firebase UIDs or role grants embedded in GitHub. NO shared-report fallback.

A dedicated isolated R31.11.4 PostgreSQL service is mandatory. This adapter
MUST NOT be pointed at the existing R31.11 synthetic clone. It needs new,
dedicated per-Firebase-user database LOGIN roles, independently provisioned by
an authorized DBA with a protected session_user -> owner_uid mapping and
read-only role membership. No automatic ALTER ROLE or CREATE ROLE permitted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

QA_DB = "sbi_r31_11_4_auth_qa_20261126"
QA_HOST = "sbi-r3114-private-postgres"
QA_PORT = "5432"
MAP_PATH = Path("/run/secrets/r3114-tenant-bindings.json")
ROLE_RE = re.compile(r"r3113_login_[a-z][a-z0-9_]{0,31}\Z")
SECRET_RE = re.compile(r"/run/secrets/r3114-[a-z0-9_-]{1,48}\.env\Z")
ENABLE_FLAG = "private-firebase-rls-auth-acceptance-v1"

SECURITY_SQL = """SELECT
 current_database(),session_user,current_user,
 current_setting('transaction_read_only'),
 r311_auth.current_tenant_uid(),
 r.rolcanlogin,r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,
 row_security_active('sbi.import_batches'),
 row_security_active('sbi.payment_source_rows'),
 row_security_active('sbi.payments'),
 row_security_active('sbi.payment_source_status_v1'),
 has_table_privilege(current_user,'sbi.payments','INSERT'),
 has_table_privilege(current_user,'sbi.payments','UPDATE'),
 has_table_privilege(current_user,'sbi.payments','DELETE'),
 has_table_privilege(current_user,'sbi.import_batches','INSERT'),
 has_table_privilege(current_user,'sbi.import_batches','UPDATE'),
 has_table_privilege(current_user,'sbi.import_batches','DELETE')
 FROM pg_catalog.pg_roles AS r WHERE r.rolname=session_user"""

# Do NOT filter by the caller-supplied owner UID. RLS *must* constrain rows.
READ_SQL = """SELECT owner_uid, source_row_number, raw_sol,
 source_status, credit_paise
 FROM sbi.payment_received_source_v1
 ORDER BY source_row_number
 LIMIT %s"""

EXPORTED = ("source_row_number", "raw_sol", "source_status", "credit_paise")


class RuntimeRLSBlocked(RuntimeError):
    """Fail closed; never expose DB errors, credentials or private UID."""


def _secure_file(path: Path, max_size: int) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeRLSBlocked("QA_SECRET_FILE_UNAVAILABLE")
    s = path.stat()
    if (s.st_uid != os.geteuid()
            or stat.S_IMODE(s.st_mode) != 0o600
            or s.st_size < 1 or s.st_size > max_size):
        raise RuntimeRLSBlocked("QA_SECRET_FILE_PERMISSIONS")
    return path.read_text(encoding="utf-8")


def _binding_for_uid(trusted_uid: str, *, path=MAP_PATH) -> tuple[str, Path]:
    # Only the already-validated user object from Firebase session middleware
    # may supply trusted_uid. Never accept uid, role or secret path over HTTP.
    if (type(trusted_uid) is not str or not 1 <= len(trusted_uid) <= 200
            or any(ord(x) < 33 or ord(x) > 126 for x in trusted_uid)):
        raise RuntimeRLSBlocked("QA_FIREBASE_UID_INVALID")
    try:
        doc = json.loads(_secure_file(path, 8192))
    except (UnicodeError, ValueError, OSError):
        raise RuntimeRLSBlocked("QA_BINDING_CONFIG_INVALID") from None
    if (type(doc) is not dict or set(doc) != {"version", "database", "bindings"}
            or doc["version"] != 1 or doc["database"] != QA_DB
            or type(doc["bindings"]) is not list
            or not 1 <= len(doc["bindings"]) <= 8):
        raise RuntimeRLSBlocked("QA_BINDING_CONFIG_INVALID")
    uids, roles, secrets = set(), set(), set()
    selected = None
    for row in doc["bindings"]:
        if type(row) is not dict or set(row) != {"firebase_uid", "pg_login_role", "secret_path"}:
            raise RuntimeRLSBlocked("QA_BINDING_CONFIG_INVALID")
        uid, role, secret = (
            row["firebase_uid"], row["pg_login_role"], row["secret_path"]
        )
        if (type(uid) is not str or not 1 <= len(uid) <= 200
                or type(role) is not str or ROLE_RE.fullmatch(role) is None
                or type(secret) is not str or SECRET_RE.fullmatch(secret) is None
                or uid in uids or role in roles or secret in secrets):
            raise RuntimeRLSBlocked("QA_BINDING_CONFIG_INVALID")
        uids.add(uid)
        roles.add(role)
        secrets.add(secret)
        if uid == trusted_uid:
            selected = (role, Path(secret))
    if selected is None:
        raise RuntimeRLSBlocked("QA_FIREBASE_UID_NOT_PROVISIONED")
    return selected


def _login_secret(path: Path, expected_role: str) -> str:
    raw = _secure_file(path, 1024)
    lines = raw.splitlines()
    values = {}
    for line in lines:
        if line.count("=") != 1:
            raise RuntimeRLSBlocked("QA_LOGIN_SECRET_INVALID")
        key, value = line.split("=", 1)
        if key in values or key not in {"PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"}:
            raise RuntimeRLSBlocked("QA_LOGIN_SECRET_INVALID")
        values[key] = value
    if (len(values) != 5 or values["PGHOST"] != QA_HOST
            or values["PGPORT"] != QA_PORT or values["PGDATABASE"] != QA_DB
            or values["PGUSER"] != expected_role
            or not 12 <= len(values["PGPASSWORD"]) <= 256):
        raise RuntimeRLSBlocked("QA_LOGIN_SECRET_INVALID")
    return values["PGPASSWORD"]


def _assert_rls_identity(row, trusted_uid: str, expected_role: str) -> None:
    if (row is None or len(row) != 20
        or tuple(row[0:5]) != (QA_DB, expected_role, expected_role, "on", trusted_uid)
        or row[5] is not True  # Actual dedicated LOGIN (not NOLOGIN test role)
        or any(value is not False for value in row[6:9])  # Super, bypass, create role
        or row[9] is not False  # CREATEDB
        or any(value is not True for value in row[10:14])
        or any(value is not False for value in row[14:20])):
        raise RuntimeRLSBlocked("QA_TENANT_ROLE_VERIFICATION_FAILED")


def read_tenant_source_only(verified_firebase_user, *, limit: int = 20,
                            connect=None, map_path=MAP_PATH):
    """Return source-only synthetic QA rows after DB-enforced RLS verification.

    'verified_firebase_user' MUST be g.dil_user from install_sessions(app).
    Test injection of connect/map_path is strictly for offline regression.
    """
    if os.environ.get("SBI_R31_11_4_RUNTIME_ENABLED") != ENABLE_FLAG:
        raise RuntimeRLSBlocked("QA_RUNTIME_FEATURE_DISABLED")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise RuntimeRLSBlocked("QA_PAGINATION_INVALID")
    uid = getattr(verified_firebase_user, "uid", None)
    claims = getattr(verified_firebase_user, "custom_claims", None) or {}
    if not isinstance(claims, dict) or claims.get("dil_dashboard") is not True:
        raise RuntimeRLSBlocked("QA_FIREBASE_ROLE_NOT_APPROVED")
    role, secret_path = _binding_for_uid(uid, path=map_path)
    password = _login_secret(secret_path, role)
    if connect is None:
        import psycopg
        connect = psycopg.connect
    try:
        with connect(host=QA_HOST, port=int(QA_PORT), dbname=QA_DB,
                     user=role, password=password, connect_timeout=5,
                     options="-c default_transaction_read_only=on") as connection:
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(SECURITY_SQL)
                identity = cur.fetchone()
                _assert_rls_identity(identity, uid, role)
                cur.execute(READ_SQL, (limit,))
                result = cur.fetchall()
                if len(result) > limit:
                    raise RuntimeRLSBlocked("QA_QUERY_RESULT_EXCEEDED_LIMIT")
                output = []
                for item in result:
                    if len(item) != 5 or item[0] != uid:
                        raise RuntimeRLSBlocked("QA_RLS_OWNER_ISOLATION_FAILED")
                    output.append(dict(zip(EXPORTED, item[1:])))
                return output
    except RuntimeRLSBlocked:
        raise
    except Exception:
        # Never log passwords, Firebase IDs, database details or source rows.
        raise RuntimeRLSBlocked("QA_RESTRICTED_DATABASE_UNAVAILABLE") from None
    finally:
        password = None
