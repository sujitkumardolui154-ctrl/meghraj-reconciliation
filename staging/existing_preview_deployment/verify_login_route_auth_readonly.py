#!/usr/bin/env python3
"""Read-only existing login routing and auth endpoints preflight.

No credentials, cookies, POST, response bodies, service changes or financial writes.
This does NOT prove that a real Firebase session succeeds or that production is private.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ORIGIN="https://sbi-preview.13-232-241-221.sslip.io"
CADDY="aws_lightsail-caddy-1"
SERVICE_TOKEN="sbi-login-workspace"

def run(*cmd):
    try:
        p=subprocess.run(cmd, capture_output=True, text=True, timeout=20,check=False)
        return p.returncode,p.stdout
    except (OSError,subprocess.TimeoutExpired):
        return 127,""

def container(name):
    rc,out=run("sudo","-n","docker","inspect",name)
    if rc: return None
    try:
        result=json.loads(out)
        return result[0] if type(result) is list and len(result)==1 else None
    except (ValueError,TypeError): return None

def https(path):
    rc,out=run("curl","--silent","--show-error","--proto","=https",
               "--max-time","12","--connect-timeout","5",
               "--output","/dev/null","--write-out","%{http_code} %{ssl_verify_result}",
               ORIGIN+path)
    m=re.fullmatch(r"(\d{3}) (\d+)",out.strip())
    if rc or not m or int(m.group(2))!=0: return "NOT_VERIFIED"
    return "HTTP_"+m.group(1)

def main(sha):
    print("=== SBI R31 EXISTING LOGIN ROUTE AND AUTH PREFLIGHT ===")
    rc,actual=run("git","-C",str(ROOT),"rev-parse","HEAD")
    rc2,dirty=run("git","-C",str(ROOT),"status","--porcelain")
    if (not re.fullmatch(r"[0-9a-f]{40}",sha) or rc or rc2
        or actual.strip()!=sha or dirty.strip()):
        print("STOP=R31_LOGIN_SOURCE_NOT_PINNED")
        return 2
    policy=json.loads((ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json").read_text("utf-8"))
    if (policy.get("user_required_url")!=ORIGIN+"/login"
        or policy.get("financial_apply")!="LOCKED"
        or policy.get("production_release")!="BLOCKED"):
        print("STOP=R31_LOGIN_TARGET_OR_LOCK_CHANGED")
        return 2
    print("R31_LOGIN_SOURCE_AND_TARGET=PASS_PINNED")
    rc,config=run("sudo","-n","docker","exec",CADDY,"cat","/etc/caddy/Caddyfile")
    # Do not print raw Caddy config; it can use env-expanded imports or named routes.
    if rc:
        print("R31_LOGIN_CADDY_ROUTE=NOT_VERIFIED")
    elif "/login" in config and SERVICE_TOKEN in config:
        print("R31_LOGIN_CADDY_ROUTE=CANDIDATE_LITERAL_ROUTE")
    elif "reverse_proxy" in config:
        print("R31_LOGIN_CADDY_ROUTE=PROXY_PRESENT_ROUTE_NEEDS_REVIEW")
    else:
        print("R31_LOGIN_CADDY_ROUTE=NOT_VERIFIED")
    rc,names=run("sudo","-n","docker","ps","--format","{{.Names}}")
    matches=[x for x in names.splitlines() if SERVICE_TOKEN in x] if rc==0 else []
    if len(matches)!=1:
        print("R31_LOGIN_SERVICE=NOT_VERIFIED")
    else:
        srv=container(matches[0])
        proxy=container(CADDY)
        if not srv or not proxy:
            print("R31_LOGIN_SERVICE=NOT_VERIFIED")
        else:
            running=srv.get("State",{}).get("Running") is True
            sn=set((srv.get("NetworkSettings") or {}).get("Networks") or {})
            pn=set((proxy.get("NetworkSettings") or {}).get("Networks") or {})
            print("R31_LOGIN_SERVICE="+("RUNNING" if running else "NOT_RUNNING"))
            print("R31_LOGIN_PROXY_NETWORK="+
                  ("SHARED_DOCKER_NETWORK" if sn & pn else "NO_SHARED_NETWORK_OR_REVIEW"))
    for key,path in (("PAGE","/login"),("AUTH_CONFIG","/auth/config"),
                     ("AUTH_CSRF","/auth/csrf"),("AUTH_ME_ANONYMOUS","/auth/me"),
                     ("LOGIN_SCRIPT","/login.js")):
        # Read only status; no response bodies, cookies, headers or key values.
        print("R31_LOGIN_"+key+"="+https(path))
    print("R31_LOGIN_FIREBASE_SESSION=NOT_TESTED_NO_CREDENTIALS_USED")
    print("R31_LOGIN_TWO_OWNER_HTTPS_RLS=NOT_TESTED")
    print("R31_LOGIN_EXTERNAL_SECURITY_ACCEPTANCE=NOT_APPROVED")
    print("R31_LOGIN_FINANCIAL_APPLY=LOCKED")
    print("R31_LOGIN_PRODUCTION_RELEASE=BLOCKED")
    print("R31_LOGIN_PREFLIGHT=COMPLETE_READONLY_OBSERVATIONS")
    return 0

if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--source-sha",required=True)
    args=arg.parse_args()
    try:
        status=main(args.source_sha)
    except (OSError,ValueError,TypeError,UnicodeError):
        print("STOP=R31_LOGIN_RUNTIME_REVIEW_REQUIRED")
        print("R31_LOGIN_FINANCIAL_APPLY=LOCKED")
        print("R31_LOGIN_PRODUCTION_RELEASE=BLOCKED")
        status=2
    raise SystemExit(status)
