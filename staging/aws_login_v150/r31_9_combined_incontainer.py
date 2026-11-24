"""R31.9 isolated RLS audit + two authentic Firebase-user isolation QA.

Runs inside existing pinned R31.6 QA container. No finance DB writes, no
changes to roles, schema, Firebase accounts, or Caddy routing. Only two
disposable synthetic SQLite receipt-index records are created and removed.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import secrets
import sys
import uuid

from app import app, SITE_ORIGIN
from dashboard_sessions import SESSION_COOKIE, firebase_app
from firebase_admin import auth
from payment_evidence_upload import _connection, _store
from r31_stage_blueprint import _connect

DOMAIN = "sbi-preview.13-232-241-221.sslip.io"
BASE = {"base_url": SITE_ORIGIN}


def emit(key: str, value: str):
    print("DB_R31_9_" + key + "=" + value, flush=True)


def fault(exc: Exception) -> str:
    typ = type(exc).__name__
    return ("ERROR_" + typ.upper()) if (
        typ.isascii() and typ.isalnum() and len(typ) <= 48
    ) else "ERROR_OTHER"


def rls_audit() -> bool:
    """Read-only catalog/privilege audit; never asserts effective policy."""
    conn = _connect("report")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("""SELECT current_database(),current_user,
                  has_table_privilege(current_user,'sbi.payment_received_source_v1','SELECT'),
                  has_table_privilege(current_user,'sbi.import_batches','SELECT'),
                  has_table_privilege(current_user,'sbi.payments','SELECT'),
                  has_table_privilege(current_user,'sbi.payments','INSERT'),
                  has_table_privilege(current_user,'sbi.payments','UPDATE'),
                  has_table_privilege(current_user,'sbi.payments','DELETE')""")
                expected = (
                    "sbi_r31_owner_qa_20261125", "sbi_r31_ownerqa_report",
                    True, False, False, False, False, False,
                )
                if tuple(cur.fetchone()) != expected:
                    emit("REPORT_PRIVILEGES", "FAIL_CATALOG_MISMATCH")
                    emit("RLS_EFFECTIVE_TENANT_GUARD", "BLOCKED_ROLE_MISMATCH")
                    return False
                emit("REPORT_PRIVILEGES", "PASS_READONLY_ROLE")
                cur.execute("""SELECT c.relname,c.relkind,
                           c.relrowsecurity,c.relforcerowsecurity
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='sbi' AND c.relname IN
                    ('import_batches','payment_source_rows','payments')""")
                rows = {name: (kind, bool(enabled), bool(forced))
                        for name, kind, enabled, forced in cur.fetchall()}
                required = ("import_batches", "payment_source_rows", "payments")
                if len(rows) != 3 or any(
                    rows[n][0] not in ("r", "p") for n in required if n in rows
                ):
                    emit("RLS_CATALOG", "BLOCKED_TABLE_SET_MISMATCH")
                    emit("RLS_EFFECTIVE_TENANT_GUARD", "NOT_VERIFIED")
                    return False
                if not all(rows[n][1] for n in required):
                    emit("RLS_CATALOG", "NOT_ENABLED_ALL_TABLES")
                    emit("RLS_EFFECTIVE_TENANT_GUARD", "NOT_VERIFIED")
                    return False
                # RLS flags do not prove effective tenant-specific policy,
                # especially if a view is evaluated with owner privileges.
                emit("RLS_CATALOG", "ENABLED_CATALOG_ONLY")
                emit("RLS_EFFECTIVE_TENANT_GUARD", "NOT_VERIFIED_BY_CATALOG")
                return False
    finally:
        conn.close()


def login(token):
    client = app.test_client()
    csrf_response = client.get("/auth/csrf", **BASE)
    if csrf_response.status_code != 200:
        raise RuntimeError("QA_CSRF_START_FAILED")
    csrf = csrf_response.get_json(silent=True)
    csrf = csrf.get("csrf_token") if type(csrf) is dict else None
    if type(csrf) is not str or len(csrf) != 64:
        raise RuntimeError("QA_CSRF_MISSING")
    response = client.post(
        "/auth/session", json={"idToken": token},
        headers={"Origin": SITE_ORIGIN, "X-DIL-CSRF": csrf}, **BASE
    )
    if response.status_code != 200:
        raise RuntimeError("QA_SESSION_FAILED")
    cookie = client.get_cookie(SESSION_COOKIE, domain=DOMAIN)
    if cookie is None:
        raise RuntimeError("QA_SESSION_COOKIE_MISSING")
    claims = auth.verify_session_cookie(
        cookie.value, check_revoked=True, app=firebase_app()
    )
    user = auth.get_user(claims["uid"], app=firebase_app())
    if user.disabled or (user.custom_claims or {}).get("dil_dashboard") is not True:
        raise RuntimeError("QA_AUTHORIZED_CLAIM_MISSING")
    if client.get("/api/r31-private-qa/status", **BASE).status_code != 200:
        raise RuntimeError("QA_PRIVATE_AUTHORIZATION_MISSING")
    return client, csrf, claims["uid"]


def cleanup_receipts(receipts):
    if not receipts:
        return
    with closing(_connection(_store())) as conn, conn:
        for rid, uid in receipts:
            deleted = conn.execute(
                "DELETE FROM receipts WHERE id=? AND owner_uid=?", (rid, uid)
            )
            if deleted.rowcount != 1:
                raise RuntimeError("QA_CLEANUP_INCOMPLETE")


def make_receipts(owners):
    """Disposable metadata-only rows, not user files or bank records."""
    result = []
    for owner in owners:
        rid = uuid.uuid4().hex
        try:
            with closing(_connection(_store())) as conn, conn:
                conn.execute("""INSERT INTO receipts
                    (id,owner_uid,filename,source_name,sha256,created_utc,
                     source_rows,valid_rows,review_rows,credit_total,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid,owner,rid+".xlsx","r31-9-synthetic.xlsx",
                     secrets.token_hex(32),datetime.now(timezone.utc).isoformat(),
                     1,1,0,"1.00","STAGED_FOR_REVIEW"))
            result.append((rid,owner))
        except Exception:
            cleanup_receipts(result)
            raise
    return result


def cross_owner_test(tokens):
    if len(tokens) != 2:
        emit("TWO_REAL_FIREBASE_USERS", "NOT_TESTED_SECOND_ACCOUNT_UNAVAILABLE")
        return False
    a, b = login(tokens[0]), login(tokens[1])
    if a[2] == b[2]:
        emit("TWO_REAL_FIREBASE_USERS", "FAIL_SAME_FIREBASE_UID")
        return False
    emit("TWO_REAL_FIREBASE_USERS", "PASS_DISTINCT_AUTHENTICATED_UIDS")
    receipts = []
    try:
        receipts = make_receipts((a[2], b[2]))
        for (client, csrf, _), own, foreign in (
            (a,receipts[0][0],receipts[1][0]),
            (b,receipts[1][0],receipts[0][0])
        ):
            listing = client.get("/api/payment-evidence/uploads", **BASE)
            if listing.status_code != 200:
                raise RuntimeError("QA_RECEIPT_LIST_FAILED")
            payload = listing.get_json(silent=True)
            entries = payload.get("evidence", []) if type(payload) is dict else []
            visible = {e.get("receipt_id") for e in entries if type(e) is dict}
            if own not in visible or foreign in visible:
                raise RuntimeError("QA_CROSS_RECEIPT_LIST_LEAK")
            foreign_get = client.get(
                "/api/payment-evidence/uploads/" + foreign, **BASE
            )
            foreign_sync = client.post(
                "/api/r31-private-qa/receipts/" + foreign + "/sync",
                headers={"Origin": SITE_ORIGIN, "X-DIL-CSRF": csrf}, **BASE
            )
            if foreign_get.status_code != 404 or foreign_sync.status_code != 404:
                raise RuntimeError("QA_CROSS_RECEIPT_GET_SYNC_LEAK")
            raw = client.get("/api/r31-private-qa/sol-report", **BASE)
            forged = client.get(
                "/api/r31-private-qa/sol-report?owner_uid=" + foreign,
                headers={"X-Owner-Uid": foreign}, **BASE
            )
            if (raw.status_code != 200 or forged.status_code != 200
                    or raw.get_json() != forged.get_json()):
                raise RuntimeError("QA_OWNER_HEADER_QUERY_SPOOF")
        emit("REAL_CROSS_ACCOUNT_RECEIPTS", "PASS_BIDIRECTIONAL_404_AND_FILTERING")
        return True
    finally:
        if receipts:
            cleanup_receipts(receipts)
            emit("SYNTHETIC_RECEIPT_CLEANUP", "PASS")


def main():
    raw = sys.stdin.buffer.read(32001)
    if not raw or len(raw) > 32000:
        emit("AUTH_PAYLOAD", "ERROR_INVALID_LENGTH")
        return 2
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError):
        emit("AUTH_PAYLOAD", "ERROR_INVALID_JSON")
        return 2
    tokens = doc.get("id_tokens") if type(doc) is dict else None
    if not isinstance(tokens, list) or len(tokens) not in (0, 2) or any(
        type(t) is not str or len(t) < 200 or len(t) > 12000 for t in tokens
    ):
        emit("AUTH_PAYLOAD", "ERROR_INVALID_TOKENS")
        return 2
    print("=== DB-R31.9 ISOLATED COMBINED SECURITY GATE ===", flush=True)
    try:
        rls_audit()
    except Exception as exc:
        emit("RLS_AUDIT", fault(exc))
    try:
        cross_owner_test(tokens)
    except Exception as exc:
        emit("CROSS_ACCOUNT", fault(exc))
    emit("PG_FINANCIAL_WRITES", "NONE_BY_TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
