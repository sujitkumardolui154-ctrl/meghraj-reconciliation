#!/usr/bin/env python3
"""Existing SBI sslip.io HTTPS Firebase acceptance, pinned-source and fail-closed.

Default: safe unauthenticated origin/CSRF diagnostic only (no account sign-in).
--real-users: operator-confirmed TWO distinct existing authorized non-admin QA
users, secrets via interactive TTY only. Auth data stays in process RAM; no files.
Does not call finance APIs, write Postgres, or approve release.
"""
from __future__ import annotations
import argparse
import getpass
import http.cookiejar
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ORIGIN="https://sbi-preview.13-232-241-221.sslip.io"
AUTH="https://identitytoolkit.googleapis.com"
SESSION_COOKIE="__Host-dil_session"
CSRF_COOKIE="__Host-dil_csrf"

class Blocked(Exception): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None

def client():
    jar=http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPCookieProcessor(jar)),jar

def fetch(opener,url,body=None,headers=None):
    if not (url.startswith(ORIGIN+"/") or url.startswith(AUTH+"/")):
        raise Blocked("UNEXPECTED_NETWORK_TARGET")
    data=None if body is None else json.dumps(body).encode("utf-8")
    req=urllib.request.Request(url,data=data,
        headers={"Accept":"application/json",
                 **({"Content-Type":"application/json"} if data is not None else {}),
                 **(headers or {})},
        method="POST" if body is not None else "GET")
    try:
        with opener.open(req, timeout=20) as response:
            status=response.status
            raw=response.read(32769)
    except urllib.error.HTTPError as exc:
        status=exc.code
        raw=b"" # HTTP error response bodies are deliberately never read or printed
    except (urllib.error.URLError,TimeoutError,OSError):
        raise Blocked("HTTPS_NETWORK_OR_TLS_ERROR") from None
    if len(raw)>32768:
        raise Blocked("RESPONSE_OVERSIZE")
    return status,raw

def json_obj(raw):
    try:
        obj=json.loads(raw)
        if type(obj) is not dict: raise ValueError()
        return obj
    except (ValueError,UnicodeError):
        raise Blocked("RESPONSE_NOT_EXPECTED_JSON") from None

def has_secure_host_cookie(jar,name):
    found=[c for c in jar if c.name==name]
    if len(found)!=1: return False
    c=found[0]
    rest={str(k).lower():str(v).lower() for k,v in c._rest.items()}
    return (c.secure and c.path=="/" and not c.domain_specified
            and "httponly" in rest and rest.get("samesite")=="lax")

def pinned_source(sha):
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise Blocked("UNPINNED_COMMIT")
    try:
        a=subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],
                capture_output=True,text=True,timeout=8,check=False)
        b=subprocess.run(["git","-C",str(ROOT),"status","--porcelain"],
                capture_output=True,text=True,timeout=8,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Blocked("SOURCE_UNAVAILABLE") from None
    if a.returncode or b.returncode or a.stdout.strip()!=sha or b.stdout.strip():
        raise Blocked("UNPINNED_OR_DIRTY_SOURCE")
    try:
        p=json.loads((ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json").read_text("utf-8"))
    except (OSError,ValueError):
        raise Blocked("TARGET_POLICY_UNAVAILABLE") from None
    if (p.get("user_required_url")!=ORIGIN+"/login"
            or p.get("financial_apply")!="LOCKED"
            or p.get("production_release")!="BLOCKED"
            or p.get("actual_deployment_performed") is not False):
        raise Blocked("TARGET_OR_RELEASE_LOCK_CHANGED")

def csrf_start(opener,jar):
    status,raw=fetch(opener,ORIGIN+"/auth/csrf")
    if status!=200: raise Blocked("CSRF_ENDPOINT_HTTP_"+str(status))
    token=json_obj(raw).get("csrf_token")
    if (type(token) is not str or not re.fullmatch(r"[0-9a-f]{64}",token)
        or not has_secure_host_cookie(jar,CSRF_COOKIE)):
        raise Blocked("CSRF_JSON_OR_COOKIE_INVALID")
    return token

def csrf_origin_check():
    opener,jar=client()
    csrf=csrf_start(opener,jar)
    valid={"Origin":ORIGIN,"X-DIL-CSRF":csrf}
    # Existing auth route must accept exact Origin+cookie/header BEFORE
    # rejecting an empty ID token. This never signs in a user.
    valid_status,_=fetch(opener,ORIGIN+"/auth/session",
                         body={"idToken":""},headers=valid)
    print("R31_FIREBASE_EXACT_ORIGIN_EMPTY_TOKEN_HTTP="+str(valid_status))
    if valid_status==403:
        raise Blocked("EXISTING_SSLIP_ORIGIN_REJECTED_OR_CSRF_MISMATCH")
    if valid_status!=400:
        raise Blocked("SESSION_INVALID_TOKEN_CONTRACT_UNEXPECTED")
    bad_status,_=fetch(opener,ORIGIN+"/auth/session",
          body={"idToken":""},
          headers={"Origin":"https://unapproved.invalid","X-DIL-CSRF":csrf})
    print("R31_FIREBASE_WRONG_ORIGIN_HTTP="+str(bad_status))
    if bad_status!=403:
        raise Blocked("WRONG_ORIGIN_NOT_DENIED")
    blank_status,_=fetch(opener,ORIGIN+"/auth/session",
          body={"idToken":""}, headers={"X-DIL-CSRF":csrf})
    print("R31_FIREBASE_MISSING_ORIGIN_HTTP="+str(blank_status))
    if blank_status!=403:
        raise Blocked("MISSING_ORIGIN_NOT_DENIED")
    print("R31_FIREBASE_HTTPS_ORIGIN_CSRF=PASS_ANONYMOUS_NEGATIVES")
    return True

def firebase_key():
    opener,_=client()
    status,raw=fetch(opener,ORIGIN+"/auth/config")
    if status!=200: raise Blocked("FIREBASE_CONFIG_HTTP_"+str(status))
    key=json_obj(raw).get("apiKey")
    if type(key) is not str or not 10<=len(key)<=256 or not re.fullmatch(r"[A-Za-z0-9_-]+",key):
        raise Blocked("FIREBASE_CONFIG_KEY_INVALID")
    return key # public web key, never logged

def confirm_operator():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise Blocked("REAL_QA_INTERACTIVE_TERMINAL_REQUIRED")
    print("Two distinct approved, non-admin Firebase TEST employees are required.")
    print("Do NOT use the real master account. Never paste credentials/tokens in chat.")
    phrase=input("Type APPROVED_TWO_TEST_USERS to authorize real QA login: ").strip()
    if phrase!="APPROVED_TWO_TEST_USERS":
        raise Blocked("REAL_USER_QA_NOT_AUTHORIZED")

def test_one(account,key):
    opener,jar=client()
    email=input("QA employee "+str(account)+" email (local only): ").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email) or len(email)>254:
        raise Blocked("INVALID_TEST_EMAIL")
    password=getpass.getpass("QA employee "+str(account)+" password (hidden): ")
    if not password: raise Blocked("EMPTY_TEST_PASSWORD")
    csrf=csrf_start(opener,jar)
    url=AUTH+"/v1/accounts:signInWithPassword?key="+urllib.parse.quote(key,safe="")
    try:
        status,raw=fetch(opener,url,{"email":email,"password":password,"returnSecureToken":True})
    finally:
        password=None
    if status!=200: raise Blocked("FIREBASE_SIGNIN_HTTP_"+str(status))
    result=json_obj(raw)
    token=result.get("idToken")
    uid=result.get("localId")
    if (type(token) is not str or not 200<=len(token)<=12000
            or type(uid) is not str or not uid
            or result.get("email","").casefold()!=email.casefold()):
        raise Blocked("FIREBASE_IDENTITY_RESPONSE_INVALID")
    print("R31_FIREBASE_USER_"+str(account)+"_PASSWORD_SIGNIN=PASS")
    try:
        status,raw=fetch(opener,ORIGIN+"/auth/session",
            {"idToken":token},
            {"Origin":ORIGIN,"X-DIL-CSRF":csrf})
    finally:
        token=None
    if status!=200 or json_obj(raw).get("ok") is not True:
        raise Blocked("DASHBOARD_SESSION_HTTP_"+str(status))
    if not has_secure_host_cookie(jar,SESSION_COOKIE):
        raise Blocked("SESSION_COOKIE_SECURITY_ATTRIBUTES_MISSING")
    status,raw=fetch(opener,ORIGIN+"/auth/me")
    if status!=200: raise Blocked("AUTH_ME_HTTP_"+str(status))
    identity=json_obj(raw)
    if (identity.get("email","").casefold()!=email.casefold()
            or identity.get("administrator") is not False):
        raise Blocked("NONADMIN_SESSION_IDENTITY_MISMATCH")
    print("R31_FIREBASE_USER_"+str(account)+"_HTTPS_SESSION=PASS")
    print("R31_FIREBASE_USER_"+str(account)+"_SECURE_SESSION_COOKIE=PASS")
    # Session cookies are RAM-only and discarded. DO NOT call /auth/logout:
    # its implementation revokes refresh tokens and could affect a real user.
    return uid,email.casefold()

def main(sha,real_users):
    print("=== R31 EXISTING SSLIP REAL FIREBASE HTTPS ACCEPTANCE ===")
    pinned_source(sha)
    print("R31_FIREBASE_SOURCE_AND_EXISTING_URL=PASS_PINNED")
    csrf_origin_check()
    if real_users:
        confirm_operator()
        key=firebase_key()
        a=test_one(1,key)
        b=test_one(2,key)
        if a[0]==b[0] or a[1]==b[1]:
            raise Blocked("TWO_DISTINCT_FIREBASE_IDENTITIES_NOT_CONFIRMED")
        print("R31_FIREBASE_TWO_DISTINCT_NONADMIN_USERS=PASS_REAL_HTTPS_AUTH")
    else:
        print("R31_FIREBASE_TWO_DISTINCT_NONADMIN_USERS=NOT_TESTED_DEFAULT_PREFLIGHT")
    print("R31_FIREBASE_CROSS_TENANT_POSTGRES_RLS=NOT_TESTED")
    print("R31_FIREBASE_EXPIRED_REVOKED_LIVE_SESSIONS=NOT_TESTED")
    print("R31_FIREBASE_NETWORK_PRIVATE_ACCESS=NOT_VERIFIED")
    print("R31_FIREBASE_PRODUCTION_AUTHORIZATION=NOT_GRANTED")
    print("R31_FIREBASE_HTTPS_ACCEPTANCE=TARGETED_CHECKS_COMPLETE_NOT_RELEASE")
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-sha",required=True)
    p.add_argument("--real-users",action="store_true",
                   help="Optional explicit local interactive two-user HTTPS acceptance")
    args=p.parse_args()
    try:
        code=main(args.source_sha,args.real_users)
    except (Blocked,ValueError,TypeError,UnicodeError) as err:
        label=str(err) if isinstance(err,Blocked) else "UNEXPECTED_DATA_OR_RUNTIME"
        label=re.sub(r"[^A-Z0-9_]+","_",label)[:90]
        print("STOP=R31_FIREBASE_"+label)
        code=2
    finally:
        print("R31_FIREBASE_FINANCIAL_APPLY=LOCKED")
        print("R31_FIREBASE_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(code)
