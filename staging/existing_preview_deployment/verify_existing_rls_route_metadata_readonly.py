#!/usr/bin/env python3
"""Only inspect existing Lightsail login container + anonymous QA HTTP route.

No user sessions, Firebase sign-ins, token use, Caddy/Docker writes, database
connection, route registration or finance writes. Prints no env values.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
URL="https://sbi-preview.13-232-241-221.sslip.io"
CONTAINER_TOKEN="sbi-login-workspace"
ROUTE="/api/r31-private-qa/tenant-rls-source-r3114"
FLAGS={
    "SBI_R31_PRIVATE_STAGING_ENABLED":"isolated-ownerqa-firebase-csrf-v1",
    "SBI_R31_11_4_RUNTIME_ENABLED":"private-firebase-rls-auth-acceptance-v1",
}
class Review(Exception): pass

def process(args,timeout=20):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Review("COMMAND_UNAVAILABLE") from None
    return p.returncode,p.stdout

def pinned(sha):
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise Review("SOURCE_SHA_INVALID")
    rc,head=process(["git","-C",str(ROOT),"rev-parse","HEAD"])
    rd,dirty=process(["git","-C",str(ROOT),"status","--porcelain"])
    if rc or rd or head.strip()!=sha or dirty.strip():
        raise Review("SOURCE_NOT_PINNED_OR_DIRTY")
    try:
        policy=json.loads((ROOT/"staging/existing_preview_deployment/existing_preview_target_policy.json").read_text("utf-8"))
    except (OSError,ValueError):
        raise Review("POLICY_NOT_AVAILABLE") from None
    if (policy.get("user_required_url")!=URL+"/login" or
        policy.get("financial_apply")!="LOCKED" or
        policy.get("production_release")!="BLOCKED"):
        raise Review("TARGET_OR_RELEASE_LOCK_CHANGED")

def inspect_login():
    rc,out=process(["sudo","-n","docker","ps","--format","{{.Names}}"])
    if rc:
        raise Review("DOCKER_CONTAINER_LIST_NOT_AVAILABLE")
    names=[n for n in out.splitlines() if CONTAINER_TOKEN in n]
    if len(names)!=1:
        raise Review("LOGIN_CONTAINER_NAME_AMBIGUOUS")
    name=names[0]
    rc,out=process(["sudo","-n","docker","inspect",name])
    if rc: raise Review("LOGIN_CONTAINER_METADATA_NOT_AVAILABLE")
    try:
        data=json.loads(out)
    except ValueError:
        raise Review("LOGIN_CONTAINER_METADATA_INVALID") from None
    if type(data) is not list or len(data)!=1 or type(data[0]) is not dict:
        raise Review("LOGIN_CONTAINER_METADATA_INVALID")
    cfg=data[0]
    if cfg.get("State",{}).get("Running") is not True:
        raise Review("LOGIN_CONTAINER_NOT_RUNNING")
    env=(cfg.get("Config") or {}).get("Env") or []
    if type(env) is not list:
        raise Review("LOGIN_CONTAINER_ENV_SHAPE_INVALID")
    statuses={}
    for key,expected in FLAGS.items():
        matches=[v.split("=",1)[1] for v in env if isinstance(v,str) and v.startswith(key+"=")]
        statuses[key]="ENABLED_EXACT" if matches==[expected] else "NOT_ENABLED_OR_REVIEW"
    # Existence status is not proof the Flask blueprint is registered.
    rc,_=process(["sudo","-n","docker","exec",name,
                  "test","-f","/app/r31_11_4_runtime_rls_blueprint.py"])
    files="CANDIDATE_MODULE_PRESENT" if rc==0 else "NOT_VERIFIED_IN_RUNNING_IMAGE"
    return statuses,files

def anonymous_probe():
    # Request only HTTP status, never response body, cookies or headers.
    rc,out=process(["curl","--silent","--show-error","--max-time","12",
                    "--connect-timeout","6","--proto","=https",
                    "--output","/dev/null",
                    "--write-out","%{http_code} %{ssl_verify_result}",
                    URL+ROUTE],timeout=17)
    if rc:
        return "NOT_VERIFIED"
    m=re.fullmatch(r"(\d{3}) (\d+)",out.strip())
    if not m or int(m.group(2))!=0:
        return "NOT_VERIFIED"
    return "HTTP_"+m.group(1)

def main(sha):
    print("=== R31 EXISTING HTTPS RLS ROUTE METADATA PREFLIGHT ===")
    pinned(sha)
    print("R31_ROUTE_EXACT_EXISTING_URL=PASS_PINNED")
    states,module=inspect_login()
    print("R31_ROUTE_LOGIN_CONTAINER=RUNNING")
    print("R31_ROUTE_PRIVATE_STAGING_FLAG="+states["SBI_R31_PRIVATE_STAGING_ENABLED"])
    print("R31_ROUTE_R3114_FLAG="+states["SBI_R31_11_4_RUNTIME_ENABLED"])
    print("R31_ROUTE_CANDIDATE_MODULE="+module)
    print("R31_ROUTE_ANONYMOUS_HTTPS_STATUS="+anonymous_probe())
    print("R31_ROUTE_ANONYMOUS_STATUS_PROVES_REGISTRATION=NO")
    print("R31_ROUTE_REAL_TWO_OWNER_RLS_HTTPS=NOT_TESTED")
    print("R31_ROUTE_NEXT_CHANGE=SEPARATE_AUTHORIZED_REVIEW_REQUIRED")
    return 0

if __name__=="__main__":
    args=argparse.ArgumentParser()
    args.add_argument("--source-sha",required=True)
    opt=args.parse_args()
    try:
        code=main(opt.source_sha)
    except Review as ex:
        code=2
        why=str(ex) if re.fullmatch(r"[A-Z0-9_]{3,90}",str(ex)) else "REVIEW_REQUIRED"
        print("STOP=R31_ROUTE_"+why)
    except (ValueError,TypeError,UnicodeError,OSError):
        code=2
        print("STOP=R31_ROUTE_UNEXPECTED_READONLY_AUDIT_ERROR")
    finally:
        print("R31_ROUTE_FINANCIAL_APPLY=LOCKED")
        print("R31_ROUTE_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(code)
