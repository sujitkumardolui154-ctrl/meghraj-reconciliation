#!/usr/bin/env python3
"""R31.11.4G: read-only AWS ingress/mTLS topology + cleanup preflight.

NO deployment, network create/connect, public Caddy change, certificate read,
account sign-in, financial query execution or data writes. It checks only
Caddy configuration identity, private PG16 isolation, R31.11.4F ephemeral
cleanup and empty dedicated QA tables, and outputs a planning gate. It cannot
prove actual end-to-end mTLS HTTPS, certificate trust or 4F real sessions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

CADDY="aws_lightsail-caddy-1"
POSTGRES="sbi-r3114-private-postgres"
QA_NETWORK="sbi-r3114-private-isolated"
QA_DB="sbi_r31_11_4_auth_qa_20261126"
EPHEMERAL_CONTAINER="sbi-r3114f-private-probe"
EPHEMERAL_NET="sbi-r3114f-firebase-egress"
EPHEMERAL_ADC="/home/ubuntu/sbi-r3114f-tmp-adc"
PROJECT_ROOT=Path(__file__).resolve().parents[2]
PLACEHOLDER=Path(__file__).resolve().with_name("Caddyfile.r31_11_review_only.template")


class ReadOnlyBlocked(RuntimeError):
    pass


def check(value,code):
    if not value:
        raise ReadOnlyBlocked(code)


def run(*command):
    try:
        r=subprocess.run(command,text=True,check=False,capture_output=True,
                         timeout=25)
    except (OSError,subprocess.TimeoutExpired):
        raise ReadOnlyBlocked("READONLY_COMMAND_UNAVAILABLE") from None
    return r.returncode,r.stdout


def docker(*args):
    code,stdout=run("sudo","-n","docker",*args)
    check(code==0,"DOCKER_READONLY_INSPECTION_FAILED")
    return stdout


def inspect_one(kind,name):
    raw=docker(kind,"inspect",name)
    try:
        obj=json.loads(raw)
    except (ValueError,TypeError):
        raise ReadOnlyBlocked("DOCKER_METADATA_INVALID") from None
    check(type(obj) is list and len(obj)==1 and type(obj[0]) is dict,
          "DOCKER_METADATA_INVALID")
    return obj[0]


def absent_docker(kind,name):
    code,_=run("sudo","-n","docker",kind,"inspect",name)
    check(code==1,"EPHEMERAL_RESOURCE_PRESENT_OR_INSPECTION_UNAVAILABLE")


def check_source(sha):
    check(re.fullmatch(r"[0-9a-f]{40}",sha) is not None,
          "SOURCE_SHA_INVALID")
    code,head=run("git","-C",str(PROJECT_ROOT),"rev-parse","HEAD")
    check(code==0 and head.strip()==sha,"SOURCE_COMMIT_CHANGED")
    # A Python script importing this module may generate .pyc files in a
    # pristine worktree *before* its first git status call. Validate tracked
    # changes strictly; permit only untracked, ordinary __pycache__/*.pyc
    # paths. No other unexpected file, staged diff or source modification
    # is acceptable. Do not delete files or rewrite gitignore.
    code,status=run("git","-C",str(PROJECT_ROOT),"status",
                    "--porcelain=v1","--untracked-files=all")
    check(code==0,"SOURCE_STATUS_UNAVAILABLE")
    for entry in status.splitlines():
        if not entry.startswith("?? "):
            raise ReadOnlyBlocked("SOURCE_DIRTY")
        path=entry[3:]
        if (not re.fullmatch(
                r"(?:[A-Za-z0-9_.-]+/)*__pycache__/[A-Za-z0-9_.-]+\\.pyc",
                path)
                or path.startswith("/")):
            raise ReadOnlyBlocked("SOURCE_UNEXPECTED_UNTRACKED_FILE")
    check(PLACEHOLDER.is_file() and not PLACEHOLDER.is_symlink(),
          "MTLS_REFERENCE_TEMPLATE_MISSING")
    src=PLACEHOLDER.read_text("utf-8")
    check("qa-r311.example.invalid" in src
          and "require_and_verify" in src and "trust_pool" in src
          and "DO NOT IMPORT OR DEPLOY AS-IS" in src,
          "UNAPPROVED_MTLS_TEMPLATE_CHANGED")
    return True


def check_database_isolation():
    pg=inspect_one("container",POSTGRES)
    net=inspect_one("network",QA_NETWORK)
    check(pg.get("State",{}).get("Running") is True,
          "QA_PG_NOT_RUNNING")
    host=pg.get("HostConfig") or {}
    networks=(pg.get("NetworkSettings") or {}).get("Networks") or {}
    check(host.get("Privileged") is False
          and host.get("PortBindings") in (None,{})
          and set(networks)=={QA_NETWORK}
          and net.get("Internal") is True
          and net.get("Attachable") is False,
          "QA_POSTGRES_NETWORK_CHANGED")
    sql="""BEGIN READ ONLY;
SELECT json_build_object(
  'database',current_database(),
  'owner_maps',(SELECT count(*) FROM r311_auth.role_owner_map),
  'data_rows',(SELECT count(*) FROM sbi.import_batches)+
              (SELECT count(*) FROM sbi.payment_source_rows)+
              (SELECT count(*) FROM sbi.payments)+
              (SELECT count(*) FROM sbi.payment_source_status_v1)
)::text;
COMMIT;"""
    raw=docker("exec",POSTGRES,"psql","-X","-qAt",
               "-v","ON_ERROR_STOP=1","-U","postgres","-d",QA_DB,
               "-c",sql).strip()
    try:
        data=json.loads(raw)
    except (TypeError,ValueError):
        raise ReadOnlyBlocked("QA_DATABASE_CATALOG_UNEXPECTED") from None
    check(data=={"database":QA_DB,"owner_maps":2,"data_rows":0},
          "QA_DATABASE_CATALOG_UNEXPECTED")
    return True


def caddy_preflight():
    info=inspect_one("container",CADDY)
    check(info.get("State",{}).get("Running") is True
          and info.get("HostConfig",{}).get("Privileged") is False,
          "CADDY_STATUS_UNEXPECTED")
    # Never display raw Caddy content: it could contain private hostnames.
    config=docker("exec",CADDY,"cat","/etc/caddy/Caddyfile")
    check(bool(config.strip()),"CADDY_CONFIG_EMPTY")
    forbidden=("sbi-r3114f","sbi-r3114-private-postgres",
               "sbi-r3114-private-api","r31-private-qa/tenant-rls-source-r3114",
               "qa-r311.example.invalid","sbi-r3114f-firebase-egress")
    check(not any(item in config for item in forbidden),
          "UNAPPROVED_PRIVATE_QA_CADDY_ROUTE_PRESENT")
    check("reverse_proxy" in config,"CADDY_CONFIG_UNEXPECTED")
    return hashlib.sha256(config.encode("utf-8")).hexdigest()


def ephemeral_cleanup():
    absent_docker("container",EPHEMERAL_CONTAINER)
    absent_docker("network",EPHEMERAL_NET)
    code,_=run("sudo","-n","test","-e",EPHEMERAL_ADC)
    check(code==1,"QA_EPHEMERAL_ADC_PRESENT_OR_INSPECTION_UNAVAILABLE")
    code,_=run("sudo","-n","test","-L",EPHEMERAL_ADC)
    check(code==1,"QA_EPHEMERAL_ADC_SYMLINK_OR_INSPECTION_UNAVAILABLE")
    return True


def main(argv=None):
    p=argparse.ArgumentParser(description="QA-only read-only HTTPS/mTLS planning audit")
    p.add_argument("--source-sha",required=True)
    args=p.parse_args(argv)
    print("=== DB-R31.11.4G EXTERNAL HTTPS/MTLS READONLY PREFLIGHT ===",
          flush=True)
    try:
        check_source(args.source_sha)
        check_database_isolation()
        print("DB_R31_11_4G_QA_POSTGRES_NETWORK=PASS_PRIVATE_UNPUBLISHED",flush=True)
        print("DB_R31_11_4G_QA_DB_ROWS=ZERO_OWNER_MAPS_TWO",flush=True)
        checksum=caddy_preflight()
        print("DB_R31_11_4G_CADDY_EXISTING_ROUTE=PASS_NO_PRIVATE_QA_ROUTE",flush=True)
        print("DB_R31_11_4G_CADDY_CONFIG_SHA256="+checksum,flush=True)
        ephemeral_cleanup()
        print("DB_R31_11_4G_4F_TEMP_RESOURCES=PASS_ABSENT",flush=True)
        print("DB_R31_11_4G_MTLS_REFERENCE=DESIGN_ONLY_INVALID_HOSTNAME",flush=True)
        print("DB_R31_11_4G_MODE=READONLY_PLANNING_NO_AWS_CHANGES",flush=True)
        return 0
    except Exception:
        # Suppress all raw cloud / Docker / Caddy / SQL exception details.
        print("STOP=DB_R31_11_4G_PREFLIGHT_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4G_4F_REAL_SESSION_RECEIPTS=NOT_VERIFIED_BY_THIS_AUDIT",flush=True)
        print("DB_R31_11_4G_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4G_R3112_QA_DESIGN=ACTIVE_RELEASE_GATED",flush=True)
        print("DB_R31_11_4G_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4G_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
