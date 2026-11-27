#!/usr/bin/env python3
"""R31.11.4F isolated one-shot REAL Firebase-to-private-PG QA.

No HTTP listener, public routing, invoice/GST/engine invocation, DB writes,
Firebase user mutation, token persistence, or production database connection.
Actual Firebase Auth SDK checks and two actual PostgreSQL restricted-login
read-only queries occur through real Flask install_sessions() + private route.
Run ONLY inside the pinned UID10001 isolated candidate image, with approved
QA secrets mounted read-only and the exact dedicated QA network.

Status output is a fixed allowlist; never print raw auth, database errors, UIDs,
emails, credentials, cookies or token details. This is Flask in-process QA
and DOES NOT satisfy external HTTPS/mTLS or session revocation E2E.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from flask import Flask

import dashboard_sessions as sessions
from firebase_admin import auth
from r31_11_4_runtime_rls_blueprint import runtime_tenant_rls

DB = "sbi_r31_11_4_auth_qa_20261126"
QA_FLAG = "private-firebase-rls-auth-acceptance-v1"
STAGING_FLAG = "isolated-ownerqa-firebase-csrf-v1"
BASE = "https://localhost"
PATH = "/api/r31-private-qa/tenant-rls-source-r3114"
MAPPING = Path("/run/secrets/r3114-tenant-bindings.json")


class TestBlocked(RuntimeError):
    pass


def require(check, reason):
    if not check:
        raise TestBlocked(reason)


def real_binding():
    # File is protected UID10001 mode-0600; no identifiers are printed.
    # The existing adapter also independently revalidates the same binding.
    import r31_11_4_runtime_rls_adapter as adapter
    raw = adapter._secure_file(MAPPING,8192)
    data = json.loads(raw)
    require(data.get("version") == 1 and data.get("database") == DB
            and type(data.get("bindings")) is list
            and len(data["bindings"]) == 2,
            "QA_BINDINGS_INVALID")
    mapping = {row["pg_login_role"]:row["firebase_uid"]
               for row in data["bindings"]}
    require(set(mapping) == {"r3113_login_a","r3113_login_b"}
            and len(set(mapping.values())) == 2,
            "QA_BINDINGS_NOT_DISTINCT")
    return mapping


def check_environment():
    require(os.getuid()==10001 and os.getgid()==10001,"QA_RUNTIME_UID_CHANGED")
    require(os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED")==STAGING_FLAG
            and os.environ.get("SBI_R31_11_4_RUNTIME_ENABLED")==QA_FLAG,
            "QA_RUNTIME_FLAGS_NOT_APPROVED")
    require(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            == "/run/firebase/adc.json","QA_FIREBASE_AUTH_CONFIG_MISSING")
    require(Path("/run/firebase/adc.json").is_file(),
            "QA_FIREBASE_AUTH_CONFIG_MISSING")
    require(sessions.PROJECT == "meghraj-reconciliation",
            "QA_FIREBASE_PROJECT_CHANGED")


def parse_tokens():
    raw = sys.stdin.buffer.read(25001)
    require(0<len(raw)<=25000,"QA_ID_TOKEN_STREAM_INVALID")
    try:
        obj=json.loads(raw)
    except (TypeError,ValueError,UnicodeError):
        raise TestBlocked("QA_ID_TOKEN_STREAM_INVALID") from None
    require(type(obj) is dict and set(obj)=={"tokens"}
            and type(obj["tokens"]) is list
            and len(obj["tokens"]) == 2,"QA_ID_TOKEN_STREAM_INVALID")
    tokens=obj["tokens"]
    require(all(type(token) is str and 200 <= len(token) <= 12000
                for token in tokens) and tokens[0] != tokens[1],
            "QA_ID_TOKENS_NOT_DISTINCT")
    return tokens


def verify_real_users(tokens,mapping):
    app=sessions.firebase_app()
    require(app.project_id==sessions.PROJECT,"QA_FIREBASE_PROJECT_CHANGED")
    expected=[mapping["r3113_login_a"],mapping["r3113_login_b"]]
    for token,uid in zip(tokens,expected):
        verified=auth.verify_id_token(token,check_revoked=True,app=app)
        require(verified.get("uid")==uid,"QA_ID_TOKEN_OWNER_MISMATCH")
        user=auth.get_user(uid,app=app)
        claims=user.custom_claims or {}
        require(not user.disabled and user.email_verified
                and claims.get("dil_dashboard") is True
                and claims.get("dil_admin") is not True
                and uid != sessions.MASTER_UID,
                "QA_FIREBASE_OWNER_NOT_APPROVED")


def minimal_private_app():
    app=Flask("r3114f_private_probe")
    sessions.ORIGINS.add(BASE)  # Only this in-process, ephemeral Flask app.
    sessions.install_sessions(app)
    app.register_blueprint(runtime_tenant_rls)
    app.testing=True
    return app


def assert_response(response,status,code):
    require(response.status_code==status,code)


def run_owner(app,token,other_uid,role):
    with app.test_client() as client:
        base={"base_url":BASE}
        csrf_response=client.get("/auth/csrf",**base)
        assert_response(csrf_response,200,"QA_CSRF_SESSION_START_FAILED")
        csrf=(csrf_response.get_json() or {}).get("csrf_token")
        require(type(csrf) is str and len(csrf)==64,"QA_CSRF_TOKEN_INVALID")
        headers={"Origin":BASE,"X-DIL-CSRF":csrf}
        login=client.post("/auth/session",json={"idToken":token},
                          headers=headers,**base)
        assert_response(login,200,"QA_REAL_FIREBASE_SESSION_CREATE_FAILED")
        require((login.get_json() or {}).get("administrator") is False,
                "QA_TEST_OWNER_ADMIN_UNEXPECTED")
        identity=client.get("/auth/me",**base)
        assert_response(identity,200,"QA_REAL_FIREBASE_SESSION_VERIFY_FAILED")
        require((identity.get_json() or {}).get("administrator") is False,
                "QA_TEST_OWNER_ADMIN_UNEXPECTED")

        # Deliberate owner and DB-role forgeries. Real session UID must win;
        # adapter asserts actual PostgreSQL session_user and RLS owner UID.
        source=client.get(
            PATH+"?limit=2&owner_uid="+other_uid+"&pg_role=r3113_login_b",
            headers={"X-Owner-Uid":other_uid,
                     "X-Pg-Role":"r3113_login_b" if role=="a"
                                  else "r3113_login_a"},**base)
        assert_response(source,200,"QA_REAL_SESSION_TO_DB_BINDING_FAILED")
        data=source.get_json() or {}
        require(data.get("report")=="R31_11_4_DB_ENFORCED_TENANT_SOURCE_ONLY"
                and data.get("rows")==[]
                and data.get("reconciliation_status")=="NOT_CALCULATED"
                and data.get("invoice_generation_enabled") is False
                and data.get("gst_generation_enabled") is False
                and data.get("financial_execution_enabled") is False
                and data.get("production_financial_writes") is False,
                "QA_READONLY_FINANCIAL_RESPONSE_CHANGED")
        # This is not a production DB or a financial endpoint; the route
        # allows GET only and cannot perform INSERT/UPDATE/DELETE.
        put=client.put(PATH,headers={"Origin":BASE},**base)
        assert_response(put,405,"QA_RESTRICTED_ROUTE_ACCEPTED_WRITE")
        bad_origin=client.post(PATH,headers={"Origin":"https://invalid.example"},
                               **base)
        assert_response(bad_origin,403,"QA_CROSS_ORIGIN_WRITE_NOT_DENIED")
    return True


def check_anonymous_invalid(app):
    with app.test_client() as anonymous:
        r=anonymous.get(PATH,base_url=BASE)
        assert_response(r,401,"QA_ANONYMOUS_NOT_DENIED")
        anonymous.set_cookie(sessions.SESSION_COOKIE,"synthetic-invalid-cookie",
                             secure=True)
        r=anonymous.get(PATH,base_url=BASE)
        assert_response(r,401,"QA_INVALID_COOKIE_NOT_DENIED")


def main():
    print("=== DB-R31.11.4F REAL FIREBASE PRIVATE IN-PROCESS QA ===",flush=True)
    try:
        check_environment()
        mapping=real_binding()
        tokens=parse_tokens()
        verify_real_users(tokens,mapping)
        print("DB_R31_11_4F_REAL_FIREBASE_TWO_TOKEN_IDENTITIES=PASS_VERIFIED",flush=True)
        app=minimal_private_app()
        check_anonymous_invalid(app)
        print("DB_R31_11_4F_ANONYMOUS_AND_INVALID_COOKIE=DENIED_PASS",flush=True)
        run_owner(app,tokens[0],mapping["r3113_login_b"],"a")
        print("DB_R31_11_4F_TENANT_A_FIREBASE_SESSION_TO_PG=PASS_READONLY",flush=True)
        run_owner(app,tokens[1],mapping["r3113_login_a"],"b")
        print("DB_R31_11_4F_TENANT_B_FIREBASE_SESSION_TO_PG=PASS_READONLY",flush=True)
        print("DB_R31_11_4F_FORGED_UID_AND_PG_ROLE=IGNORED_PASS",flush=True)
        print("DB_R31_11_4F_FINANCIAL_WRITE_ENDPOINT=DENIED_PASS",flush=True)
        print("DB_R31_11_4F_RUNTIME_MODE=ONE_SHOT_FLASK_IN_PROCESS_NO_HTTP_LISTENER",flush=True)
        return 0
    except Exception:
        print("STOP=DB_R31_11_4F_PRIVATE_AUTH_ACCEPTANCE_FAILED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4F_REAL_REVOKED_OR_EXPIRED_SESSION=NOT_TESTED",flush=True)
        print("DB_R31_11_4F_EXTERNAL_MTLS_HTTPS=PENDING",flush=True)
        print("DB_R31_11_4F_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4F_R3112=QUARANTINED",flush=True)
        print("DB_R31_11_4F_RELEASE=PRODUCTION_BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
