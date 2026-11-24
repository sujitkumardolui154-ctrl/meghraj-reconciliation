#!/usr/bin/env python3
"""R31.7 dedicated, disposable AWS QA launcher.

Leaves existing dual-network private-auth stage, live Caddy, finance engine,
and the shared FT-04 QA PostgreSQL container/network UNTOUCHED. Instead, it
creates a new one-member internal Docker network with an empty PostgreSQL 16
container, seeds ONLY the synthetic FT-04 source schema, and uses the same
approved owner-source/report QA runner with its explicit dedicated profile.

The database, anonymous PG volume and role secrets created here are deleted
ONLY after verifying their exact unique Docker IDs. No production databases,
network attachments or financial tables are mutated. Never run as a daemon.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import stat
import subprocess
import sys
import time

import db_r31_owner_qa_combined as qa

REPO=Path(__file__).resolve().parents[2]
NETWORK=qa.DEDICATED_NETWORK
PG=qa.DEDICATED_PG
SOURCE=qa.SOURCE
PRIVATE=qa.DEDICATED_PRIVATE
CI_IMAGE="postgres:16-alpine"
TEST_PASSWORD="R31_DISPOSABLE_SYNTHETIC_ONLY_20261125"
LABEL="org.sbi.r31.purpose"
LABEL_VALUE="r31-7-disposable-isolation"
SHA=re.compile(r"[a-f0-9]{40}\Z")


class DedicatedQASafetyStop(RuntimeError):
    pass


def require(ok,code):
    if not ok:
        raise DedicatedQASafetyStop(code)


def docker(*args,check=True,timeout=45):
    cmd=["sudo","-n","docker",*args]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:
        # No Docker CLI stdout/stderr is printed: it might contain secrets.
        raise DedicatedQASafetyStop("DEDICATED_DOCKER_COMMAND_FAILED")
    return p


def json_inspect(kind,name):
    result=docker(kind,"inspect",name)
    try:
        return json.loads(result.stdout)[0]
    except (ValueError,IndexError,TypeError):
        raise DedicatedQASafetyStop("DEDICATED_INSPECT_UNEXPECTED") from None


def source_preflight():
    require(os.geteuid()!=0,"RUN_AS_NONROOT_UBUNTU")
    require(REPO.is_dir() and not REPO.is_symlink(),
            "DEDICATED_SOURCE_DIRECTORY_UNSAFE")
    p=subprocess.run(["git","-C",str(REPO),"rev-parse","HEAD"],
                     capture_output=True,text=True)
    require(p.returncode==0 and SHA.fullmatch(p.stdout.strip()),
            "DEDICATED_PINNED_SOURCE_COMMIT_REQUIRED")
    p=subprocess.run(["git","-C",str(REPO),"status","--porcelain",
                      "--untracked-files=all"],capture_output=True,text=True)
    require(p.returncode==0 and not p.stdout.strip(),
            "DEDICATED_SOURCE_WORKTREE_NOT_CLEAN")
    for name in ("db_r31_ft04_qa_seed.sql",
                 "db_r31_additive_qa_up.sql",
                 "db_r31_owner_qa_combined.py",
                 "db_r31_owner_qa_runtime.py",
                 "db_r31_owner_persistent_qa.sql"):
        require((qa.ROOT/name).is_file(),"DEDICATED_QA_SOURCE_MISSING")
    # Do not change/remove an existing QA app or PG. This script is only for
    # a *new* disposable name. A stopped leftover is a REVIEW, not a cleanup.
    require(docker("network","inspect",NETWORK,check=False).returncode!=0,
            "DEDICATED_NETWORK_ALREADY_EXISTS_REVIEW")
    require(docker("container","inspect",PG,check=False).returncode!=0,
            "DEDICATED_PG_ALREADY_EXISTS_REVIEW")
    require(docker("image","inspect",CI_IMAGE,check=False).returncode==0,
            "LOCAL_DISPOSABLE_POSTGRES_IMAGE_REQUIRED")
    require(not PRIVATE.exists() and not PRIVATE.is_symlink(),
            "DEDICATED_PRIVATE_QA_DIRECTORY_EXISTS_REVIEW")
    app=qa.inspect(qa.APP)
    require(app["State"]["Status"]=="running" and
            isinstance(app.get("Image"),str) and
            app["Image"].startswith("sha256:"),
            "REVIEWED_APP_IMAGE_UNAVAILABLE")
    return p.stdout.strip()


def create_network():
    docker("network","create","--internal",
           "--label",f"{LABEL}={LABEL_VALUE}",NETWORK)
    inspected=json_inspect("network",NETWORK)
    require(inspected.get("Internal") is True and
            inspected.get("Labels",{}).get(LABEL)==LABEL_VALUE and
            not (inspected.get("Containers") or {}),
            "DEDICATED_INTERNAL_NETWORK_CREATION_UNSAFE")
    return inspected["Id"]


def create_pg():
    docker("run","--detach","--pull=never",
           "--name",PG,
           "--network",NETWORK,
           "--label",f"{LABEL}={LABEL_VALUE}",
           "--restart","no",
           "--security-opt","no-new-privileges",
           "--pids-limit","256","--memory","512m",
           "-e",f"POSTGRES_DB={SOURCE}",
           "-e",f"POSTGRES_PASSWORD={TEST_PASSWORD}",
           CI_IMAGE,timeout=60)
    inspected=qa.inspect(PG)
    require(inspected.get("Config",{}).get("Labels",{}).get(LABEL)==LABEL_VALUE and
            inspected.get("HostConfig",{}).get("PortBindings") in (None,{}) and
            set(inspected.get("NetworkSettings",{}).get("Networks",{}))=={NETWORK},
            "DEDICATED_PG_CONTAINER_IDENTITY_UNSAFE")
    return inspected["Id"]


def wait_pg():
    ready=False
    for _ in range(60):
        p=docker("exec",PG,"pg_isready","-h","127.0.0.1",
                 "-p","5432","-U","postgres","-d",SOURCE,check=False)
        if p.returncode==0:
            ready=True
            break
        time.sleep(1)
    require(ready,"DEDICATED_POSTGRES_NOT_READY")


def seed_source():
    qa.use_dedicated_isolated_profile()
    require(not qa.db_exists("sbi_reconciliation_main"),
            "DEDICATED_PRODUCTION_DB_UNEXPECTEDLY_PRESENT")
    require(qa.db_exists(SOURCE),"DEDICATED_SOURCE_DB_MISSING")
    for name in ("db_r31_ft04_qa_seed.sql","db_r31_additive_qa_up.sql"):
        sql=(qa.ROOT/name).read_text(encoding="utf-8")
        result=qa.psql(SOURCE,sql)
    require(qa.psql(SOURCE,
        "SELECT to_regclass('sbi.payment_received_source_v1') IS NOT NULL;")=="t",
        "DEDICATED_SOURCE_VIEW_MISSING")
    print("DB_R31_7_SEPARATE_SYNTHETIC_FT04_SCHEMA=PASS",flush=True)


def safe_cleanup(container_id,network_id):
    notes=[]
    if container_id:
        current=qa.inspect(PG)
        require(current.get("Id")==container_id and
                current.get("Config",{}).get("Labels",{}).get(LABEL)==LABEL_VALUE,
                "DEDICATED_CONTAINER_CHANGED_REFUSE_CLEANUP")
        docker("rm","-f","-v",PG,timeout=35)
        notes.append("PG")
    if network_id:
        current=json_inspect("network",NETWORK)
        require(current.get("Id")==network_id and
                current.get("Labels",{}).get(LABEL)==LABEL_VALUE and
                not (current.get("Containers") or {}),
                "DEDICATED_NETWORK_CHANGED_REFUSE_CLEANUP")
        docker("network","rm",NETWORK)
        notes.append("NETWORK")
    if PRIVATE.exists():
        require(PRIVATE.is_dir() and not PRIVATE.is_symlink()
                and PRIVATE.resolve()==Path(
                    "/home/ubuntu/sbi-db-management/db-r31-7-dedicated"),
                "DEDICATED_CREDENTIAL_DIRECTORY_UNSAFE")
        allowed={"ingest.env","report.env"}
        files=list(PRIVATE.iterdir())
        require(all(x.is_file() and not x.is_symlink()
                    and x.name in allowed and
                    stat.S_IMODE(x.stat().st_mode)==0o600 for x in files),
                "DEDICATED_UNKNOWN_PRIVATE_CREDENTIAL_REFUSE_CLEANUP")
        for f in files:
            f.unlink()
        PRIVATE.rmdir()
        notes.append("CREDS")
    print("DB_R31_7_DEDICATED_TEST_ASSETS_REMOVED=" + (
        "YES" if network_id and container_id and
                 {"PG","NETWORK"}.issubset(notes) else
        "NO_ASSETS_OR_PARTIAL"),flush=True)


def main():
    print("=== R31.7 DEDICATED ISOLATED AWS QA ===",flush=True)
    source_preflight()
    network_id=None
    container_id=None
    failure=None
    try:
        network_id=create_network()
        container_id=create_pg()
        wait_pg()
        seed_source()
        # Runner refuses any extra or multi-homed member; the dual-homed
        # R31 Firebase-auth service remains on its original network.
        qa.validate_safety()
        print("DB_R31_7_DEDICATED_NETWORK_ONLY_QA_PG=PASS",flush=True)
        qa.main()
        print("DB_R31_7_AWS_DEDICATED_SOURCE_AND_REPORT_QA=PASS",flush=True)
    except Exception as exc:
        failure=exc
    finally:
        try:
            safe_cleanup(container_id,network_id)
        except Exception as cleanup_exc:
            print("STOP=DEDICATED_CLEANUP_REVIEW_REQUIRED",flush=True)
            if failure is None:
                failure=cleanup_exc
    if failure is not None:
        raise DedicatedQASafetyStop(
            "DEDICATED_R31_7_QA_FAILED_REVIEW_REQUIRED") from failure
    print("DB_R31_7_PRODUCTION_DATABASE_WRITES=NONE",flush=True)
    print("DB_R31_7_FIREBASE_REAL_OWNER_AUTH=NOT_TESTED",flush=True)
    print("DB_R31_7_RELEASE_STATUS=DEDICATED_ISOLATED_AWS_QA_PASS_ONLY",
          flush=True)


if __name__=="__main__":
    try:
        if sys.argv[1:]:
            raise DedicatedQASafetyStop("DEDICATED_QA_NO_ARGUMENTS_ALLOWED")
        main()
    except Exception as err:
        print("DB_R31_7_DEDICATED_QA=REVIEW_REQUIRED",flush=True)
        print("STOP="+str(err)[:110],flush=True)
        raise SystemExit(1)
