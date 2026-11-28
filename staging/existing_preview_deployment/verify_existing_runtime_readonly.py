#!/usr/bin/env python3
"""SBI R31 exact-existing-preview runtime verification. NO mutations.

Only tests the owner-authorized HTTPS login URL (unauthenticated GET), reads
local Docker inspection and in-memory Caddy config; prints fixed safe statuses.
Does not print actual Caddy, certificate, Docker env, authentication data, IPs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HOST="sbi-preview.13-232-241-221.sslip.io"
LOGIN_URL="https://"+HOST+"/login"
CADDY="aws_lightsail-caddy-1"
LOGIN_SERVICE="sbi-login-workspace"
PG="sbi-r3114-private-postgres"
NET="sbi-r3114-private-isolated"
BASELINE_SHA="61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b"
ROOT=Path(__file__).resolve().parents[2]

def command(args, timeout=20):
    try:
        p=subprocess.run(args,text=True,capture_output=True,check=False,timeout=timeout)
        return p.returncode,p.stdout
    except (OSError,subprocess.TimeoutExpired):
        return 127,""

def docker(*args):
    return command(["sudo","-n","docker",*args])

def inspection(kind,name):
    code,out=docker(kind,"inspect",name)
    if code!=0:
        return None
    try:
        values=json.loads(out)
        return values[0] if type(values) is list and len(values)==1 and type(values[0]) is dict else None
    except (ValueError,TypeError):
        return None

def source(sha):
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        return False
    c,head=command(["git","-C",str(ROOT),"rev-parse","HEAD"])
    d,dirty=command(["git","-C",str(ROOT),"status","--porcelain"])
    return c==0 and d==0 and head.strip()==sha and not dirty.strip()

def https_probe():
    # No auth cookies, no follow-redirect, no TLS bypass, no response body.
    rc,out=command([
        "curl","--silent","--show-error","--max-time","15",
        "--connect-timeout","7","--proto","=https",
        "--output","/dev/null",
        "--write-out","%{http_code} %{ssl_verify_result}",
        LOGIN_URL
    ],timeout=19)
    match=re.fullmatch(r"(\d{3}) (\d+)",out.strip())
    if rc!=0 or not match:
        return "NOT_VERIFIED", "NOT_VERIFIED"
    status,verify=map(int,match.groups())
    tls="PASS_TRUSTED" if verify==0 else "REVIEW_REQUIRED"
    # A 3xx response still establishes an authenticated/public route, not full login functionality.
    page="RESPONDED_HTTP_"+str(status) if 100<=status<=599 else "NOT_VERIFIED"
    return tls,page

def audit(sha):
    print("=== R31 EXISTING SSLIP APPLICATION READONLY VERIFICATION ===")
    if not source(sha):
        print("STOP=DB_R31_EXISTING_SOURCE_UNPINNED_OR_DIRTY")
        return 2
    print("DB_R31_EXISTING_SOURCE=PASS_PINNED")
    policy=json.loads((ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json").read_text("utf-8"))
    if (policy.get("user_required_url")!=LOGIN_URL or
        policy.get("financial_apply")!="LOCKED" or
        policy.get("production_release")!="BLOCKED" or
        policy.get("actual_deployment_performed") is not False):
        print("STOP=DB_R31_EXISTING_POLICY_CHANGED")
        return 2
    print("DB_R31_EXISTING_TARGET=PASS_EXACT_SSLIP_LOGIN")
    tls,http=https_probe()
    print("DB_R31_EXISTING_PUBLIC_HTTPS_TLS="+tls)
    print("DB_R31_EXISTING_LOGIN_HTTP="+http)
    c=inspection("container",CADDY)
    rc,config=docker("exec",CADDY,"cat","/etc/caddy/Caddyfile")
    if c is None or rc!=0:
        print("DB_R31_EXISTING_CADDY=NOT_VERIFIED")
    else:
        ok=c.get("State",{}).get("Running") is True
        digest=hashlib.sha256(config.encode("utf-8")).hexdigest()
        print("DB_R31_EXISTING_CADDY_BASELINE="+
              ("PASS_UNCHANGED" if ok and digest==BASELINE_SHA else "REVIEW_REQUIRED"))
        # Read-only route evidence is qualitative; no private config revealed.
        print("DB_R31_EXISTING_LOGIN_ROUTE="+
              ("CANDIDATE_PRESENT" if "/login" in config and LOGIN_SERVICE in config
               else "NOT_VERIFIED"))
    rc,names=docker("ps","--format","{{.Names}}")
    if rc!=0:
        print("DB_R31_EXISTING_LOGIN_CONTAINER=NOT_VERIFIED")
    else:
        found=[x for x in names.splitlines() if LOGIN_SERVICE in x]
        print("DB_R31_EXISTING_LOGIN_CONTAINER="+
              ("RUNNING_CANDIDATE" if len(found)==1 else "REVIEW_REQUIRED"))
    pg=inspection("container",PG)
    net=inspection("network",NET)
    if pg is None or net is None:
        state="NOT_VERIFIED"
    else:
        host=pg.get("HostConfig") or {}
        networks=(pg.get("NetworkSettings") or {}).get("Networks") or {}
        ok=(pg.get("State",{}).get("Running") is True
            and host.get("Privileged") is False
            and host.get("PortBindings") in (None,{})
            and set(networks)=={NET} and net.get("Internal") is True
            and net.get("Attachable") is False)
        state="PASS_QA_PRIVATE_UNPUBLISHED" if ok else "REVIEW_REQUIRED"
    print("DB_R31_EXISTING_QA_POSTGRES="+state)
    print("DB_R31_EXISTING_FIREBASE_REAL_LOGIN=NOT_TESTED")
    print("DB_R31_EXISTING_TWO_USER_RLS_OVER_HTTPS=NOT_TESTED")
    print("DB_R31_EXISTING_PUBLIC_IPV4_IPV6_EXPOSURE=NOT_VERIFIED_BY_LOCAL_AUDIT")
    print("DB_R31_EXISTING_ACTUAL_DEPLOYMENT=NOT_PERFORMED")
    print("DB_R31_EXISTING_FINANCIAL_APPLY=LOCKED")
    print("DB_R31_EXISTING_PRODUCTION_RELEASE=BLOCKED")
    print("DB_R31_EXISTING_AUDIT=COMPLETE_REVIEW_OBSERVATIONS")
    return 0

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-sha",required=True)
    args=parser.parse_args()
    try:
        exit_code=audit(args.source_sha)
    except (OSError,ValueError,TypeError,UnicodeError):
        print("STOP=DB_R31_EXISTING_APPLICATION_AUDIT_REVIEW_REQUIRED")
        print("DB_R31_EXISTING_FINANCIAL_APPLY=LOCKED")
        print("DB_R31_EXISTING_PRODUCTION_RELEASE=BLOCKED")
        exit_code=2
    raise SystemExit(exit_code)
