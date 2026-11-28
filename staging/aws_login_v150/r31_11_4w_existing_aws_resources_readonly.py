#!/usr/bin/env python3
"""R31.11.4W: read-only AWS host inventory of reusable security infrastructure.
No container creation, DNS change, credential access, certificate reading,
configuration mutation, financial queries, or live external acceptance.
Only prints fixed status codes and Caddy configuration digest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CADDY="aws_lightsail-caddy-1"
PG="sbi-r3114-private-postgres"
NET="sbi-r3114-private-isolated"
CADDY_BASELINE="61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b"

def command(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=25,check=False)
    if result.returncode!=0:
        raise RuntimeError("READONLY_COMMAND_FAILED")
    return result.stdout

def docker(*args):
    return command("sudo","-n","docker",*args)

def inspect(kind,name):
    data=json.loads(docker(kind,"inspect",name))
    if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):
        raise RuntimeError("DOCKER_METADATA_INVALID")
    return data[0]

def source(expected):
    if not re.fullmatch(r"[0-9a-f]{40}",expected):
        raise RuntimeError("INVALID_SHA")
    if command("git","-C",str(ROOT),"rev-parse","HEAD").strip()!=expected:
        raise RuntimeError("SOURCE_SHA_CHANGED")
    if command("git","-C",str(ROOT),"status","--porcelain").strip():
        raise RuntimeError("SOURCE_DIRTY")

def run(expected):
    source(expected)
    print("DB_R31_11_4W_SOURCE=PASS_PINNED")
    c=inspect("container",CADDY)
    if c.get("State",{}).get("Running") is not True:
        raise RuntimeError("CADDY_NOT_RUNNING")
    contents=docker("exec",CADDY,"cat","/etc/caddy/Caddyfile")
    digest=hashlib.sha256(contents.encode("utf-8")).hexdigest()
    if digest!=CADDY_BASELINE:
        raise RuntimeError("PUBLIC_CADDY_BASELINE_DRIFT")
    print("DB_R31_11_4W_EXISTING_CADDY=PASS_BASELINE_UNCHANGED")
    p=inspect("container",PG)
    n=inspect("network",NET)
    hosts=p.get("HostConfig") or {}
    networks=(p.get("NetworkSettings") or {}).get("Networks") or {}
    if not (p.get("State",{}).get("Running") is True
            and hosts.get("Privileged") is False
            and hosts.get("PortBindings") in (None,{})
            and set(networks)=={NET}
            and n.get("Internal") is True
            and n.get("Attachable") is False):
        raise RuntimeError("PRIVATE_QA_PG_NETWORK_DRIFT")
    print("DB_R31_11_4W_PRIVATE_QA_POSTGRES=PASS_EXISTING_UNPUBLISHED")
    # These are reusable host controls, NOT proof of external DNS, TLS or owner approval.
    r=json.loads((HERE/"r31_11_4r_deployment_gate.json").read_text(encoding="utf-8"))
    s=json.loads((HERE/"r31_11_4s_external_acceptance_matrix.json").read_text(encoding="utf-8"))
    if (r.get("deployment_authorization")!="NOT_GRANTED" or
        r.get("approved_qa_fqdn")!="PENDING" or
        s.get("authorization")!="NOT_GRANTED" or
        s.get("external_https_endpoint")!="NOT_DEPLOYED" or
        len(s.get("external_cases",[]))!=22 or
        any(x.get("status")!="NOT_TESTED_EXTERNAL" for x in s["external_cases"])):
        raise RuntimeError("APPROVAL_EVIDENCE_CHANGED")
    print("DB_R31_11_4W_EXISTING_HOST_CONTROLS=REUSE_CANDIDATE_NOT_EXTERNAL_APPROVAL")
    print("DB_R31_11_4W_APPROVED_QA_FQDN=NOT_VERIFIED")
    print("DB_R31_11_4W_EXTERNAL_INGRESS=NOT_APPROVED")
    print("DB_R31_11_4W_SERVER_CERT_AND_CLIENT_CA=NOT_VERIFIED")
    print("DB_R31_11_4W_REVOCATION_AND_ROLLBACK=NOT_VERIFIED")
    print("DB_R31_11_4W_EXTERNAL_TESTS=0_OF_22_EXECUTED")
    print("DB_R31_11_4W_AWS_INVENTORY=PASS_READONLY_SCOPE")
    return 0

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-sha",required=True)
    args=parser.parse_args()
    try:
        result=run(args.source_sha)
    except Exception:
        print("STOP=DB_R31_11_4W_HOST_OR_EVIDENCE_REVIEW_REQUIRED")
        result=2
    finally:
        print("DB_R31_11_4W_FINANCIAL_APPLY=LOCKED")
        print("DB_R31_11_4W_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(result)
