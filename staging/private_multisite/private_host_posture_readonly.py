#!/usr/bin/env python3
"""Read-only PRIVATE-ACCESS host posture inventory; never grants release.

No raw Docker inspect, process args, hostnames, IP addresses, IAM identities,
tokens, credentials, or Caddy content printed. No network probes or mutations.
Results are candidates for independent review, not proof of public unreachability.
"""
import hashlib
import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path

CADDY="aws_lightsail-caddy-1"
QA_PG="sbi-r3114-private-postgres"
QA_NET="sbi-r3114-private-isolated"
EXPECTED_CADDY_SHA="61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b"

def run(args, timeout=15):
    try:
        p=subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                         check=False)
        return p.returncode,p.stdout
    except (OSError,subprocess.TimeoutExpired):
        return 127,""

def docker(*args):
    return run(["sudo","-n","docker",*args])

def inspect(kind,name):
    code,out=docker(kind,"inspect",name)
    if code:
        return None
    try:
        value=json.loads(out)
        return value[0] if isinstance(value,list) and len(value)==1 else None
    except (TypeError,ValueError):
        return None

def socket_summary():
    rc,out=run(["ss","-H","-ltn"])
    if rc:
        return "NOT_VERIFIED"
    # Local socket inspection cannot prove internet reachability or firewall rules.
    public_port=False
    loopback_port=False
    for line in out.splitlines():
        parts=line.split()
        if len(parts)<5:
            continue
        addr=parts[3]
        try:
            # IPv4 and IPv6 address:port, including [::]:443.
            host,port=addr.rsplit(":",1)
            if int(port) not in (80,443,8080,18181):
                continue
            host=host.strip("[]")
            if host in ("*","0.0.0.0","::"):
                public_port=True
            else:
                ip=ipaddress.ip_address(host.split("%")[0])
                if ip.is_loopback:
                    loopback_port=True
                else:
                    public_port=True
        except (ValueError,IndexError):
            return "REVIEW_REQUIRED"
    if public_port:
        return "NON_LOOPBACK_WEB_LISTENER_PRESENT"
    if loopback_port:
        return "LOOPBACK_WEB_LISTENER_ONLY"
    return "NO_TARGET_WEB_LISTENER_FOUND"

def main():
    print("=== R31 PRIVATE MULTISITE AWS READONLY POSTURE ===")
    c=inspect("container",CADDY)
    if c is None:
        print("SBI_PRIVATE_CADDY=NOT_VERIFIED")
    else:
        rc,raw=docker("exec",CADDY,"cat","/etc/caddy/Caddyfile")
        actual=hashlib.sha256(raw.encode("utf-8")).hexdigest() if not rc else None
        print("SBI_PRIVATE_CADDY_BASELINE="+
              ("PASS_UNCHANGED" if actual==EXPECTED_CADDY_SHA
               else "REVIEW_REQUIRED"))
    pg=inspect("container",QA_PG)
    net=inspect("network",QA_NET)
    if pg is None or net is None:
        print("SBI_PRIVATE_QA_POSTGRES=NOT_VERIFIED")
    else:
        host=pg.get("HostConfig") or {}
        networks=(pg.get("NetworkSettings") or {}).get("Networks") or {}
        ok=(pg.get("State",{}).get("Running") is True
            and host.get("Privileged") is False
            and host.get("PortBindings") in (None,{})
            and set(networks)=={QA_NET}
            and net.get("Internal") is True
            and net.get("Attachable") is False)
        print("SBI_PRIVATE_QA_POSTGRES="+
              ("PASS_PRIVATE_UNPUBLISHED" if ok else "REVIEW_REQUIRED"))
    print("SBI_PRIVATE_HOST_WEB_LISTENERS="+socket_summary())
    if not shutil.which("tailscale"):
        print("SBI_PRIVATE_TAILSCALE_CLI=NOT_INSTALLED")
    else:
        rc,out=run(["tailscale","status","--json"])
        if rc:
            print("SBI_PRIVATE_TAILSCALE=NOT_VERIFIED")
        else:
            try:
                info=json.loads(out)
                state=info.get("BackendState")
                print("SBI_PRIVATE_TAILSCALE_BACKEND="+
                      ("RUNNING" if state=="Running" else "NOT_RUNNING_OR_REVIEW"))
            except ValueError:
                print("SBI_PRIVATE_TAILSCALE=NOT_VERIFIED")
    print("SBI_PRIVATE_LIGHTSAIL_IPV4_IPV6_FIREWALL=NOT_VERIFIED_BY_HOST")
    print("SBI_PRIVATE_FIREBASE_TWO_REAL_EMPLOYEES=NOT_VERIFIED_BY_HOST")
    print("SBI_PRIVATE_TAILNET_GRANTS_DEVICE_MFA=NOT_VERIFIED_BY_HOST")
    print("SBI_PRIVATE_PUBLIC_INTERNET_DENIAL=NOT_VERIFIED_BY_HOST")
    print("SBI_PRIVATE_REPLACEMENT_GATES=7_PENDING")
    print("SBI_PREVIOUS_PUBLIC_EXTERNAL_MTLS=0_OF_22_NOT_WAIVED")
    print("SBI_FINANCIAL_APPLY=LOCKED")
    print("SBI_PRODUCTION_RELEASE=BLOCKED")

if __name__=="__main__":
    main()
