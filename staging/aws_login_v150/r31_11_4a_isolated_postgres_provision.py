#!/usr/bin/env python3
"""R31.11.4A: guarded NEW PRIVATE PostgreSQL 16 provisioning on AWS operator host.

Default is READ-ONLY plan. --apply requires exact, deliberate QA-only approval.
Creates ONLY a new internal Docker network, new named volume, new local password
file, and a new isolated PostgreSQL 16 container/database. Does NOT touch the
existing R31.11 owner QA, synthetic clone, Caddy, Firebase or financial engine.

Never use on a second machine or after a partial attempt without an independent
review. No auto cleanup, overwrite, rerun, role grants or production writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time

from r31_real_firebase_qa_acceptance import (
    PG as EXISTING_PG, QA_DB as EXISTING_QA, STAGE, preflight,
)

NAME = "sbi-r3114-private-postgres"
NETWORK = "sbi-r3114-private-isolated"
VOLUME = "sbi-r3114-authdata-20261126"
DATABASE = "sbi_r31_11_4_auth_qa_20261126"
PROBE_DB = "sbi_r3114_restore_probe_20261126"
SECRET_DIR = Path("/home/ubuntu/sbi-r3114a-private")
PASSWORD_PATH = SECRET_DIR / "postgres-init-password"
SECRET_MOUNT = "/run/secrets/r3114-postgres-init-password"
CADDY = "aws_lightsail-caddy-1"
EXPECTED_ORIGINAL = (
    "sbi-synthetic-postgres-38-31",
    "sbi_r31_owner_qa_20261125",
    "sbi-r31-auth-private-qa",
)
APPROVE = "R3114A_PRIVATE_QA_ONLY"
EXPECTED_IMAGE_MAJOR = 16
LABEL = "com.meghraj.r3114a.isolated_only"
BASE_ALLOWED = frozenset(("postgres", "template0", "template1", DATABASE))


class ProvisionBlocked(RuntimeError):
    """Public safe status only; never print raw secret or Docker output."""


def docker(*args, payload=None, timeout=35):
    result = subprocess.run(
        ["sudo", "-n", "docker", *args],
        input=payload,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise ProvisionBlocked("DOCKER_OPERATION_REFUSED")
    return result.stdout.decode("utf-8", errors="strict").strip()


def docker_blob(*args, payload=None, timeout=35):
    result = subprocess.run(
        ["sudo", "-n", "docker", *args],
        input=payload,
        capture_output=True, timeout=timeout, check=False,
    )
    if result.returncode:
        raise ProvisionBlocked("DOCKER_BACKUP_OR_RESTORE_FAILED")
    return result.stdout


def safe_json(raw):
    result = json.loads(raw)
    if type(result) is not list or len(result) != 1:
        raise ProvisionBlocked("DOCKER_INSPECTION_INVALID")
    return result[0]


def caddy_fingerprint():
    config = docker("exec", CADDY, "cat", "/etc/caddy/Caddyfile")
    if any(name in config for name in (
        NAME, NETWORK, "sbi-r3114-private-api", "sbi-r31-auth-private-qa",
        "sbi-r31-auth-qa"
    )):
        raise ProvisionBlocked("UNAPPROVED_QA_CADDY_ROUTE")
    return hashlib.sha256(config.encode()).hexdigest()


def _existing_resource_names():
    checks = (
        ("container", ("ps", "-a", "--filter", f"name=^/{NAME}$",
                       "--format", "{{.Names}}"), NAME),
        ("network", ("network", "ls", "--filter", f"name=^{NETWORK}$",
                     "--format", "{{.Name}}"), NETWORK),
        ("volume", ("volume", "ls", "--filter", f"name=^{VOLUME}$",
                    "--format", "{{.Name}}"), VOLUME),
    )
    result = {}
    for kind, args, exact in checks:
        names = docker(*args).splitlines()
        if any(n.strip() not in ("", exact) for n in names):
            raise ProvisionBlocked("DOCKER_RESOURCE_LIST_AMBIGUOUS")
        result[kind] = any(n.strip() == exact for n in names)
    result["secret"] = PASSWORD_PATH.exists() or PASSWORD_PATH.is_symlink()
    result["secret_dir"] = SECRET_DIR.exists() or SECRET_DIR.is_symlink()
    return result


def inspect_original_image():
    if (EXISTING_PG, EXISTING_QA, STAGE) != EXPECTED_ORIGINAL:
        raise ProvisionBlocked("ORIGINAL_QA_IDENTITY_CHANGED")
    info = safe_json(docker("inspect", EXISTING_PG))
    if (info.get("State", {}).get("Running") is not True
            or info.get("HostConfig", {}).get("PortBindings") not in (None, {})
            or "sbi-synthetic-isolated-38-31" not in
               (info.get("NetworkSettings", {}).get("Networks") or {})):
        raise ProvisionBlocked("ORIGINAL_QA_CONTAINER_CHANGED")
    entrypoint = (info.get("Config") or {}).get("Entrypoint")
    if entrypoint not in (["docker-entrypoint.sh"],
                          ["/usr/local/bin/docker-entrypoint.sh"]):
        raise ProvisionBlocked("SOURCE_POSTGRES_ENTRYPOINT_NOT_VERIFIED")
    image_id = info.get("Image")
    if (type(image_id) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}",image_id) is None):
        raise ProvisionBlocked("SOURCE_IMAGE_NOT_PINNED")
    version = docker("exec", EXISTING_PG, "postgres", "-V")
    if not re.match(r"^postgres \(PostgreSQL\) 16(?:\.|\s|$)", version):
        raise ProvisionBlocked("SOURCE_IMAGE_NOT_POSTGRES16")
    return image_id


def review_plan():
    # Must pass original private isolation before even planning new resources.
    preflight()
    image_id = inspect_original_image()
    caddy_hash = caddy_fingerprint()
    existing = _existing_resource_names()
    if any(existing.values()):
        raise ProvisionBlocked("NAME_OR_SECRET_ALREADY_EXISTS_REVIEW_REQUIRED")
    print("DB_R31_11_4A_ORIGINAL_PRIVATE_ISOLATION=PASS",flush=True)
    print("DB_R31_11_4A_LOCAL_POSTGRES16_IMAGE=PINNED_FROM_EXISTING_QA",
          flush=True)
    print("DB_R31_11_4A_RESOURCE_NAMES=ALL_UNUSED",flush=True)
    print("DB_R31_11_4A_CADDY_EXPOSURE=NO_NEW_ROUTE",flush=True)
    return image_id, caddy_hash


def _new_secret():
    # Create only a fresh folder and a fresh mode-0600 password file.
    # A partial provisioning run must never silently reuse any of these.
    if SECRET_DIR.is_symlink() or SECRET_DIR.exists():
        raise ProvisionBlocked("QA_SECRET_DIRECTORY_ALREADY_EXISTS")
    SECRET_DIR.mkdir(mode=0o700)
    os.chmod(SECRET_DIR, 0o700)
    path_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        path_flags |= os.O_NOFOLLOW
    fd = os.open(PASSWORD_PATH, path_flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        # Do not log, put on CLI, GitHub or Docker environment.
        password = secrets.token_urlsafe(48).encode("ascii") + b"\n"
        with os.fdopen(fd, "wb") as output:
            output.write(password)
            output.flush()
            os.fsync(output.fileno())
    finally:
        # fd is closed by fdopen after success; on pre-fdopen error close it.
        try:
            os.close(fd)
        except OSError:
            pass
    state = PASSWORD_PATH.stat()
    if (stat.S_IMODE(state.st_mode) != 0o600
            or state.st_uid != os.geteuid()
            or PASSWORD_PATH.is_symlink()):
        raise ProvisionBlocked("QA_SECRET_PERMISSIONS_INVALID")


def _run_args(image_id):
    # Strictly no -p/--publish, privileged, Docker socket or production mount.
    return (
        "run", "-d",
        "--name", NAME,
        "--pull", "never",
        "--network", NETWORK,
        "--network-alias", NAME,
        "--restart", "no",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--cap-add", "CHOWN",
        "--cap-add", "FOWNER",
        "--cap-add", "SETUID",
        "--cap-add", "SETGID",
        "--cap-add", "DAC_OVERRIDE",
        "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
        "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,size=16m",
        "--pids-limit", "160",
        "--memory", "768m",
        "--cpus", "1",
        "--label", f"{LABEL}=true",
        "--mount", f"type=volume,source={VOLUME},target=/var/lib/postgresql/data",
        "--mount", (
            f"type=bind,source={PASSWORD_PATH},"
            f"target={SECRET_MOUNT},readonly"
        ),
        "--env", f"POSTGRES_DB={DATABASE}",
        "--env", "POSTGRES_USER=postgres",
        "--env", f"POSTGRES_PASSWORD_FILE={SECRET_MOUNT}",
        "--env", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
        image_id,
    )


def _exact_topology(image_id):
    info = safe_json(docker("inspect", NAME))
    net = safe_json(docker("network", "inspect", NETWORK))
    host = info.get("HostConfig", {})
    cfg = info.get("Config", {})
    networks = (info.get("NetworkSettings") or {}).get("Networks") or {}
    mounts = info.get("Mounts", [])
    named_volume = [
        m for m in mounts if m.get("Type") == "volume"
        and m.get("Name") == VOLUME
        and m.get("Destination") == "/var/lib/postgresql/data"
    ]
    password_mount = [
        m for m in mounts if m.get("Type") == "bind"
        and m.get("Source") == str(PASSWORD_PATH)
        and m.get("Destination") == SECRET_MOUNT
        and m.get("RW") is False
    ]
    return (
        info.get("State", {}).get("Running") is True
        and info.get("Image") == image_id
        and cfg.get("Labels", {}).get(LABEL) == "true"
        and host.get("Privileged") is False
        and host.get("PortBindings") in (None, {})
        and host.get("ReadonlyRootfs") is True
        and any(str(v).startswith("no-new-privileges")
                for v in (host.get("SecurityOpt") or []))
        and set(networks) == {NETWORK}
        and net.get("Internal") is True
        and net.get("Attachable") is False
        and len(named_volume) == 1
        and len(password_mount) == 1
        and len(mounts) == 2
    )


def _ready():
    for attempt in range(30):
        result = subprocess.run(
            ["sudo","-n","docker","exec",NAME,
             "pg_isready","-U","postgres","-d",DATABASE],
            capture_output=True, timeout=10, check=False,
        )
        if result.returncode == 0:
            return True
        time.sleep(1)
    return False


def _catalog():
    result = docker("exec", NAME, "psql", "-X", "-qAt",
                    "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                    "-d", "postgres", "-c",
                    "SELECT datname FROM pg_database ORDER BY datname")
    names = set(result.splitlines())
    if (names != BASE_ALLOWED or len(result.splitlines()) != len(names)):
        raise ProvisionBlocked("NEW_QA_DATABASE_SET_UNEXPECTED")
    user_objects = docker(
        "exec", NAME, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", DATABASE, "-c",
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON "
        "n.oid=c.relnamespace WHERE "
        "n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%' "
        "AND c.relkind IN ('r','p','m','v')"
    )
    if user_objects != "0":
        raise ProvisionBlocked("NEW_QA_DATABASE_NOT_EMPTY")
    version = docker("exec", NAME, "postgres", "-V")
    if not re.match(r"^postgres \(PostgreSQL\) 16(?:\.|\s|$)",version):
        raise ProvisionBlocked("NEW_QA_POSTGRES_VERSION_WRONG")
    print("DB_R31_11_4A_NEW_DATABASE=EXACT_EMPTY_IDENTITY_PASS",flush=True)


def _empty_schema_restore_drill():
    # Verify a BASELINE schema-only dump can be restored into a separate
    # disposable database IN THIS NEW isolated container only. This is not
    # evidence of application-data backup or production disaster recovery.
    data = docker_blob("exec", NAME, "pg_dump",
                       "-U", "postgres", "-d", DATABASE,
                       "--schema-only", "--format=custom", timeout=35)
    if not data or len(data) > 4_000_000:
        raise ProvisionBlocked("BASELINE_BACKUP_INVALID")
    # The main database is never restored/overwritten.
    docker("exec", NAME, "createdb", "-U", "postgres", PROBE_DB)
    docker_blob("exec", "-i", NAME, "pg_restore",
                "-U", "postgres", "-d", PROBE_DB,
                "--no-owner", "--no-privileges", payload=data, timeout=60)
    probe_check = docker(
        "exec", NAME, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", PROBE_DB, "-c",
        "SELECT current_database()"
    )
    if probe_check != PROBE_DB:
        raise ProvisionBlocked("BASELINE_RESTORE_IDENTITY_FAILED")
    # Exact-name and no user-data guard before dropping disposable probe.
    objects = docker("exec", NAME, "psql", "-X", "-qAt",
                     "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                     "-d", PROBE_DB, "-c",
                     "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                     "ON n.oid=c.relnamespace WHERE "
                     "n.nspname NOT IN ('pg_catalog','information_schema') "
                     "AND n.nspname NOT LIKE 'pg_toast%' "
                     "AND c.relkind IN ('r','p','m','v')")
    if objects != "0":
        raise ProvisionBlocked("DISPOSABLE_RESTORE_HAS_UNEXPECTED_OBJECTS")
    docker("exec", NAME, "dropdb", "-U", "postgres", PROBE_DB)
    print("DB_R31_11_4A_EMPTY_BASELINE_RESTORE=PASS_DISPOSABLE_PROBE_ONLY",
          flush=True)


def apply(image_id, original_caddy_hash):
    # Plans first; never skip the guarded identical-name preflight.
    _new_secret()
    print("DB_R31_11_4A_PASSWORD_FILE=CREATED_PRIVATE_NOT_PRINTED",flush=True)
    docker("network", "create", "--driver", "bridge",
           "--internal", "--label", f"{LABEL}=true", NETWORK)
    print("DB_R31_11_4A_NETWORK=CREATED_INTERNAL_ONLY",flush=True)
    docker("volume", "create", "--label", f"{LABEL}=true", VOLUME)
    print("DB_R31_11_4A_VOLUME=CREATED_NEW_DEDICATED",flush=True)
    docker(*_run_args(image_id), timeout=45)
    print("DB_R31_11_4A_POSTGRES_CONTAINER=CREATED_FROM_PINNED_IMAGE",
          flush=True)
    if not _ready():
        raise ProvisionBlocked("NEW_PRIVATE_POSTGRES_NOT_READY")
    if not _exact_topology(image_id):
        raise ProvisionBlocked("NEW_PRIVATE_POSTGRES_TOPOLOGY_UNSAFE")
    print("DB_R31_11_4A_NETWORK_AND_FILESYSTEM=PASS_NO_PUBLIC_PORTS",
          flush=True)
    _catalog()
    _empty_schema_restore_drill()
    _catalog()  # Prove restore-probe database was removed.
    if caddy_fingerprint() != original_caddy_hash:
        raise ProvisionBlocked("CADDY_CONFIG_CHANGED_DURING_PROVISIONING")
    # Original source-only QA still safe and unchanged.
    preflight()
    print("DB_R31_11_4A_ORIGINAL_QA=UNCHANGED_AS_PREFLIGHTED",flush=True)
    print("DB_R31_11_4A_CADDY=UNCHANGED_NO_PUBLIC_QA_ROUTE",flush=True)
    print("DB_R31_11_4A_QA_INFRASTRUCTURE=PASS_PROVISIONED_ISOLATED",flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true",
                        help="Create NEW isolated QA resources; default is plan only")
    parser.add_argument("--approve",default="",
                        help="Required literal R3114A_PRIVATE_QA_ONLY for --apply")
    args = parser.parse_args(argv)
    try:
        image_id, fingerprint = review_plan()
        if not args.apply:
            print("DB_R31_11_4A_MODE=READONLY_PLAN_ONLY_NO_CHANGES",flush=True)
            return 0
        if args.approve != APPROVE:
            raise ProvisionBlocked("EXPLICIT_PRIVATE_QA_APPROVAL_REQUIRED")
        print("DB_R31_11_4A_MODE=AUTHORIZED_ISOLATED_CREATION",flush=True)
        apply(image_id,fingerprint)
        return 0
    except (ProvisionBlocked, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired):
        print("STOP=DB_R31_11_4A_GUARDED_PROVISIONING_REVIEW_REQUIRED",
              flush=True)
        return 2
    finally:
        print("DB_R31_11_4A_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4A_PRODUCTION_FINANCIAL_WRITES=NONE_BY_SCRIPT",
              flush=True)
        print("DB_R31_11_4A_REAL_FIREBASE_USERS=NOT_TOUCHED",flush=True)
        print("DB_R31_11_4A_R3112_FINANCIAL_INTEGRATION=QUARANTINED",
              flush=True)
        print("DB_R31_11_4A_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING",
              flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
