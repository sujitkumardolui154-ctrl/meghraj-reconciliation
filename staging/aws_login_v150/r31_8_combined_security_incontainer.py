"""DB-R31.8 real Firebase private combined owner/role/HTTPS guard QA.

Executes only in the previously passed R31.6 isolated Docker staging image.
No public port, no Caddy edit, no creation of Firebase accounts/claims, no
financial allocation. One synthetic *foreign owner* receipt exists only in the
isolated SQLite receipt index and is deleted in finally. PostgreSQL is READ
ONLY for this test; no source or payment writes.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal
from pathlib import Path
import json
import os
import secrets
import sqlite3
import sys
import uuid

from flask import g
from app import app, SITE_ORIGIN
from dashboard_sessions import CSRF_COOKIE, SESSION_COOKIE
from payment_evidence_upload import _store, _connection
from r31_db_r31_owner_source_adapter import QA_DB, authenticated_owner
from r31_stage_blueprint import _connect, QA_REPORT_ROLE
from r31_db_r31_owner_report_adapter import sol_summary, payment_details

EXPECTED_FEDERATION = "meghraj-reconciliation"
EXPECTED_EMAIL = "" # Do not hardcode email or print identities.
TARGET_STATUS = "NOT_CALCULATED"


def stop(code):
    print("STOP=DB_R31_8_" + code, flush=True)
    raise SystemExit(2)


def require(ok,code):
    if not ok:
        stop(code)


def http_status(resp,expected,code):
    require(resp.status_code==expected,code+"_HTTP_"+str(resp.status_code))


def private_db_role_snapshot():
    """Read-only privilege metadata; no actual INSERT/UPDATE statements."""
    report=_connect("report")
    try:
        with report:
            with report.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("""SELECT current_database(),current_user,
                    has_table_privilege(current_user,'sbi.payment_received_source_v1','SELECT'),
                    has_table_privilege(current_user,'sbi.import_batches','SELECT'),
                    has_table_privilege(current_user,'sbi.payments','SELECT'),
                    has_table_privilege(current_user,'sbi.payments','INSERT'),
                    has_table_privilege(current_user,'sbi.payments','UPDATE'),
                    has_table_privilege(current_user,'sbi.payments','DELETE')""")
                snap=tuple(cur.fetchone())
                require(snap==(QA_DB,QA_REPORT_ROLE,True,False,False,False,False,False),
                        "REPORT_ROLE_NOT_LEAST_PRIVILEGE")
                cur.execute("""SELECT c.relrowsecurity,c.relforcerowsecurity
                    FROM pg_class c WHERE c.oid='sbi.import_batches'::regclass""")
                rls=tuple(cur.fetchone())
                require(rls in ((False,False),(True,False),(True,True)),
                        "UNKNOWN_RLS_METADATA")
                cur.execute("""SELECT count(DISTINCT owner_uid) FROM
                    sbi.payment_received_source_v1 WHERE owner_uid IS NOT NULL""")
                owners=int(cur.fetchone()[0])
                return rls,owners
    finally:
        report.close()


def report_snapshot(user):
    # psycopg 3 connection context closes on exit in the existing adapters;
    # use one private restricted connection per read-only report.
    conn=_connect("report")
    try:
        summaries=sol_summary(conn,user,limit=1000,offset=0)
    finally:
        conn.close()
    conn=_connect("report")
    try:
        details=payment_details(conn,user,limit=1000,offset=0)
    finally:
        conn.close()
    return summaries,details


def private_cookie_assertions(client,csrf_response,session_response):
    for response,cookie_name in (
        (csrf_response,CSRF_COOKIE),(session_response,SESSION_COOKIE)
    ):
        cookies=response.headers.getlist("Set-Cookie")
        matching=[x for x in cookies if x.startswith(cookie_name+"=")]
        require(len(matching)==1,"SECURE_COOKIE_MISSING")
        c=matching[0].lower()
        require("secure" in c and "httponly" in c and "path=/" in c
                and "samesite=lax" in c,"SECURE_COOKIE_ATTRIBUTES_CHANGED")
    print("DB_R31_8_SESSION_COOKIE_SECURE_FLAGS=PASS",flush=True)


def add_foreign_receipt():
    """Temporary synthetic receipt, never associated with bank records."""
    base=_store()
    rid=uuid.uuid4().hex
    uid="r31-8-foreign-"+secrets.token_hex(14)
    name="R31-8-foreign-"+secrets.token_hex(6)+".xlsx"
    with closing(_connection(base)) as conn,conn:
        conn.execute("""INSERT INTO receipts
            (id,owner_uid,filename,source_name,sha256,created_utc,
            source_rows,valid_rows,review_rows,credit_total,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (rid,uid,rid+".xlsx",name,secrets.token_hex(32),
             "2026-11-25T00:00:00+00:00",1,1,0,"118.00",
             "STAGED_FOR_REVIEW"))
    return rid,uid


def cleanup_foreign_receipt(rid,uid):
    with closing(_connection(_store())) as conn, conn:
        cur=conn.execute("DELETE FROM receipts WHERE id=? AND owner_uid=?",
                         (rid,uid))
        require(cur.rowcount==1,"FOREIGN_QA_RECEIPT_CLEANUP_INCOMPLETE")


def run_authenticated_negative_cases(client,csrf,user):
    """Signed app session is master user; foreign source owner is synthetic.

    This is an authenticated-vs-foreign-receipt test, NOT a second genuine
    Firebase-user session. A separate second-account E2E remains pending.
    """
    before_summary,before_details=report_snapshot(user)
    foreign_id=foreign_uid=None
    try:
        foreign_id,foreign_uid=add_foreign_receipt()
        base={"base_url":SITE_ORIGIN}
        headers={"Origin":SITE_ORIGIN,"X-DIL-CSRF":csrf}

        own_list=client.get("/api/payment-evidence/uploads",**base)
        http_status(own_list,200,"OWNER_RECEIPTS_LIST")
        require(all(e.get("receipt_id")!=foreign_id for e in
                    own_list.get_json().get("evidence",[])),
                "FOREIGN_RECEIPT_VISIBLE_IN_LIST")

        foreign_get=client.get("/api/payment-evidence/uploads/"+foreign_id,**base)
        http_status(foreign_get,404,"FOREIGN_RECEIPT_PRIVATE_GET")
        foreign_sync=client.post(
            "/api/r31-private-qa/receipts/"+foreign_id+"/sync",
            headers=headers,**base)
        http_status(foreign_sync,404,"FOREIGN_RECEIPT_QA_SYNC")
        print("DB_R31_8_AUTHENTICATED_FOREIGN_RECEIPT_GET_SYNC=DENIED",flush=True)

        summary=client.get("/api/r31-private-qa/sol-report",**base)
        http_status(summary,200,"OWNER_SOL_REPORT")
        forged=client.get(
            "/api/r31-private-qa/sol-report?owner_uid="+foreign_uid,
            headers={"X-Owner-Uid":foreign_uid},**base)
        http_status(forged,200,"FORGED_OWNER_HEADER_QUERY")
        require(summary.get_json()==forged.get_json(),
                "FORGED_OWNER_CHANGED_REPORT")
        print("DB_R31_8_FORGED_OWNER_HEADER_AND_QUERY_IGNORED=PASS",flush=True)

        after_summary,after_details=report_snapshot(user)
        require(after_summary==before_summary and after_details==before_details,
                "FOREIGN_RECEIPT_ALTERED_OWNER_POSTGRES_REPORT")
        require(all(d.get("source_receipt_id")!=foreign_id for d in after_details),
                "FOREIGN_RECEIPT_LEAKED_TO_OWNER")
        print("DB_R31_8_OWNER_FILTERED_PG_SOL_DETAILS_PARITY=PASS",flush=True)
    finally:
        if foreign_id is not None:
            cleanup_foreign_receipt(foreign_id,foreign_uid)
            print("DB_R31_8_SYNTHETIC_FOREIGN_RECEIPT_CLEANUP=PASS",flush=True)


def main():
    raw=sys.stdin.buffer.read(16000)
    require(0<len(raw)<=16000,"AUTH_INPUT_SIZE")
    try:
        doc=json.loads(raw)
    except (ValueError,UnicodeError):
        stop("AUTH_INPUT_BAD_JSON")
    token=doc.get("id_token") if type(doc) is dict else None
    require(type(token) is str and 200<=len(token)<=12000,"AUTH_TOKEN_NOT_PRESENT")
    print("=== DB-R31.8 PRIVATE COMBINED SECURITY QA ===",flush=True)
    with app.test_client() as anonymous:
        base={"base_url":SITE_ORIGIN}
        for path in (
            "/api/r31-private-qa/status",
            "/api/r31-private-qa/sol-report",
            "/api/r31-private-qa/payment-details",
            "/api/payment-evidence/uploads"
        ):
            res=anonymous.get(path,**base)
            http_status(res,401,"ANONYMOUS_DENIAL")
    print("DB_R31_8_ANONYMOUS_FINANCIAL_SOURCE_API_DENIED=PASS",flush=True)

    # A made-up cookie must not be trusted, even if presented under the
    # original __Host session-cookie name. Do not use a real user's cookie.
    # An unhandled exception in this specific test previously appeared only
    # as generic host-level RUNTIME_ERROR, hiding the failed security gate.
    print("DB_R31_8_CURRENT_CHECK=FORGED_FIREBASE_SESSION_COOKIE",flush=True)
    try:
        with app.test_client() as forged_client:
            domain="sbi-preview.13-232-241-221.sslip.io"
            forged_client.set_cookie(SESSION_COOKIE,"not-a-firebase-session-cookie",
                                     domain=domain,secure=True,httponly=True)
            denied=forged_client.get("/api/r31-private-qa/sol-report",
                                     base_url=SITE_ORIGIN)
            http_status(denied,401,"FORGED_SESSION_COOKIE_DENIAL")
    except Exception as exc:
        # Never include the exception message, stack or session-cookie data.
        # Precise safe error taxonomy is sufficient to differentiate a client
        # test-harness mismatch from a Firebase middleware/server failure.
        allowed={
            "TypeError","AttributeError","ValueError","KeyError",
            "RuntimeError","AssertionError","OSError","LookupError",
        }
        category=type(exc).__name__
        stop("FORGED_COOKIE_EXCEPTION_"+(
            category.upper() if category in allowed else "OTHER"
        ))
    print("DB_R31_8_FORGED_FIREBASE_COOKIE_DENIED=PASS",flush=True)

    with app.test_client() as client:
        base={"base_url":SITE_ORIGIN}
        csrf_r=client.get("/auth/csrf",**base)
        http_status(csrf_r,200,"CSRF_START")
        csrf=csrf_r.get_json().get("csrf_token")
        require(type(csrf) is str and len(csrf)==64,"CSRF_TOKEN_MISSING")
        headers={"Origin":SITE_ORIGIN,"X-DIL-CSRF":csrf}
        session=client.post("/auth/session",json={"idToken":token},
                            headers=headers,**base)
        http_status(session,200,"REAL_FIREBASE_SESSION")
        private_cookie_assertions(client,csrf_r,session)
        identity=client.get("/auth/me",**base)
        http_status(identity,200,"FIREBASE_ME")
        # Never log user email/UID, but verify that original Firebase middleware
        # created a live authorized identity, then trust that owner exclusively.
        print("DB_R31_8_REAL_FIREBASE_SESSION=PASS",flush=True)

        for path in ("/api/r31-private-qa/sol-report",
                     "/api/r31-private-qa/payment-details.csv"):
            res=client.get(path,**base)
            http_status(res,200,"OWNER_READ_API")
        # Signed-in user's request does not rely on any client-supplied owner.
        # Build trusted owner from Firebase SDK using exact existing session.
        from dashboard_sessions import firebase_app, SESSION_COOKIE
        from firebase_admin import auth
        cookie=client.get_cookie(SESSION_COOKIE,domain="sbi-preview.13-232-241-221.sslip.io")
        require(cookie is not None,"FIREBASE_SESSION_COOKIE_MISSING")
        identity_claims=auth.verify_session_cookie(cookie.value,check_revoked=True,app=firebase_app())
        user=auth.get_user(identity_claims["uid"],app=firebase_app())
        owner=authenticated_owner(user)
        require(owner==identity_claims["uid"],"TRUSTED_OWNER_MISMATCH")

        no_csrf=client.post(
            "/api/r31-private-qa/receipts/"+uuid.uuid4().hex+"/sync",
            headers={"Origin":SITE_ORIGIN},**base)
        http_status(no_csrf,403,"MISSING_CSRF_NEGATIVE")
        bad_origin=client.post(
            "/api/r31-private-qa/receipts/"+uuid.uuid4().hex+"/sync",
            headers={"Origin":"https://example.invalid","X-DIL-CSRF":csrf},**base)
        http_status(bad_origin,403,"CROSS_ORIGIN_NEGATIVE")
        print("DB_R31_8_SIGNED_SESSION_CSRF_NEGATIVE_CASES=PASS",flush=True)

        run_authenticated_negative_cases(client,csrf,user)

    rls,owner_count=private_db_role_snapshot()
    print("DB_R31_8_REPORT_DB_ROLE_LEAST_PRIVILEGE=PASS",flush=True)
    require(owner_count>=1,"QA_OWNER_SOURCE_DATA_ABSENT")
    print("DB_R31_8_OWNER_SCOPED_SOURCE_READS=PASS",flush=True)
    if rls==(False,False):
        print("DB_R31_8_PRODUCTION_RLS=NOT_ENABLED",flush=True)
    else:
        # Even when RLS is switched on, verification of effective user-
        # specific policy + invoker view is NOT implied by catalog bit flags.
        print("DB_R31_8_PRODUCTION_RLS=POLICY_EFFECT_NOT_VERIFIED",flush=True)
    print("DB_R31_8_SECOND_REAL_FIREBASE_OWNER=NOT_TESTED",flush=True)
    print("DB_R31_8_PRIVATE_HTTPS_EXTERNAL_E2E=NOT_TESTED_NO_PUBLIC_ROUTE",flush=True)
    print("DB_R31_8_MASTER_V251_FINANCIAL_ALLOCATION=NOT_CONNECTED",flush=True)
    print("DB_R31_8_PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST",flush=True)
    print("DB_R31_8_RELEASE_STATUS=PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED",flush=True)
    print("=== DB-R31.8 PRIVATE COMBINED QA COMPLETE ===",flush=True)


if __name__=="__main__":
    main()
