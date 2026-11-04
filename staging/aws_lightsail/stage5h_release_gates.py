#!/usr/bin/env python3
"""Stage 5H consolidated non-destructive TLS, auth boundary, and feature-gap audit.

Makes only unauthenticated GETs to known public URLs or local loopback.
Reads container and volume metadata, never certificate content or credentials.
Does not prove certificate persistence after restart or authenticated parity.
"""
from __future__ import annotations
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

AWS_URL = "https://sbi-preview.13-232-241-221.sslip.io"
CLOUD_RUN_URL = "https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app"
CADDY = "aws_lightsail-caddy-1"
SAFE_PATHS = ("/", "/healthz", "/api/pipeline/status", "/api/upload")

def docker_inspect():
    result = subprocess.run(["docker","container","inspect",CADDY],
                            capture_output=True,text=True,timeout=12,check=False)
    if result.returncode:
        raise RuntimeError("Cannot inspect Caddy metadata")
    payload = json.loads(result.stdout)
    if len(payload) != 1:
        raise RuntimeError("Unexpected Caddy inspect response")
    return payload[0]

def check_url(url):
    request = urllib.request.Request(url, method="GET",
                headers={"User-Agent":"SBI-Stage5H-readonly/1"})
    try:
        with urllib.request.urlopen(request,timeout=8,context=ssl.create_default_context()) as r:
            return {"http": r.status, "tls_verified": url.startswith("https://")}
    except urllib.error.HTTPError as exc:
        # TLS was negotiated and verified before HTTP response.
        return {"http": exc.code, "tls_verified": url.startswith("https://")}
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
        # Avoid printing remote response or secrets; error class only.
        return {"http": "CONNECTION_OR_TLS_FAILURE",
                "tls_verified": False, "failure_type": type(exc).__name__}

def main():
    result={"stage":"5H","mode":"READ_ONLY_FINAL_GATES",
            "production_changed":False,"financial_writes":0}
    try:
        d=docker_inspect()
        mounts={m.get("Destination"):m for m in d.get("Mounts",[])
                if m.get("Type")=="volume"}
        result["storage"]={}
        for name in ("/data","/config"):
            m=mounts.get(name)
            result["storage"][name]={"volume_present":bool(m),
                    "read_write":bool(m and m.get("RW")),
                    "volume_name": m.get("Name") if m else None}
        result["storage"]["restart_survival"]="NOT_TESTED"
        result["storage"]["certificate_contents"]="NOT_ACCESSED"
        result["storage"]["nonroot_volume_ownership"]="NOT_TESTED"
        result["public_https"]=check_url(AWS_URL+"/")
        result["public_https"]["url"]=AWS_URL
        result["unauthenticated_aws_routes"]={
            path:check_url(AWS_URL+path)["http"] for path in SAFE_PATHS}
        result["cloud_run_reference"]={
            "url":CLOUD_RUN_URL,
            "unauthenticated_root":check_url(CLOUD_RUN_URL+"/")["http"],
            "feature_inventory":"NOT_AVAILABLE_FROM_UNAUTHENTICATED_GET",
            "feature_parity":"NOT_VERIFIED"}
        http=result["public_https"]["http"]
        checks={
          "caddy_storage_volumes_present":all(
            result["storage"][x]["volume_present"] and result["storage"][x]["read_write"]
            for x in ("/data","/config")),
          "aws_tls_chain_verified":result["public_https"]["tls_verified"],
          "unauthenticated_aws_not_exposing_finance":result["unauthenticated_aws_routes"]["/api/upload"] in (401,403,404,405,503),
          "aws_root_protected":http in (401,403),
        }
        result["checks"]=checks
        result["remaining_gates"]=[
          "isolated_certificate_persistence_restore_test",
          "authenticated_aws_functional_e2e",
          "cloud_run_login_v150_route_and_feature_parity",
          "actual_live_rollback_not_tested",
        ]
        result["release_decision"]="REVIEW_REQUIRED"
        result["audit_result"]="PASS_READ_ONLY_REVIEW_PENDING" if all(checks.values()) else "BLOCKED_REVIEW_REQUIRED"
        print(json.dumps(result,indent=2,sort_keys=True))
        return 0 if all(checks.values()) else 2
    except (RuntimeError,OSError,ValueError,json.JSONDecodeError,subprocess.TimeoutExpired) as exc:
        print("STAGE5H_BLOCKED="+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
