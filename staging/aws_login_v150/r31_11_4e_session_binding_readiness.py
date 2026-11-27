#!/usr/bin/env python3
"""R31.11.4E: NO-DEPLOY, NO-WRITE private Firebase-to-RLS acceptance gate.

Inspects the existing dedicated AWS PostgreSQL QA topology, *actual* two-user
Firebase Admin receipt, role catalog, and secret metadata. Does NOT issue a
Firebase session, connect as a tenant, mount credentials, enable runtime flags,
start containers, change cloud configuration, or authorize HTTPS/mTLS.
A PASS proves readiness to request separate approval for live session tests.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import r31_11_4a_isolated_postgres_provision as infra
import r31_11_4c_firebase_bound_login_roles as roles
import r31_11_4_private_runtime_readiness as readiness

SECRET_DIR = Path("/home/ubuntu/sbi-r3114c-app-secrets")
SOURCE_DIR = Path(__file__).resolve().parent
FILES = (
    "r3114-owner-a.env",
    "r3114-owner-b.env",
    "r3114-tenant-bindings.json",
)
APP_UID = 10001
APP_GID = 10001


class ReadinessBlocked(RuntimeError):
    """Only non-sensitive internal identifiers; never raw secrets/errors."""


def _secure_metadata():
    """Inspect UID-10001 private files via sudo stat; NEVER read file contents.

    Ubuntu cannot traverse mode-0700 directory owned by UID 10001.
    Calling Path.is_file()/stat() as Ubuntu is not evidence of bad permissions.
    GNU stat without -L reports symlinks as symlinks; refuse them.
    """
    paths = [SECRET_DIR] + [SECRET_DIR / name for name in FILES]
    try:
        inspected = subprocess.run(
            ["sudo", "-n", "stat", "-c", "%a %u %g %s %F",
             "--", *(str(p) for p in paths)],
            check=False, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ReadinessBlocked("QA_SECRET_METADATA_INSPECTION_UNAVAILABLE") from None
    if inspected.returncode != 0:
        raise ReadinessBlocked("QA_SECRET_METADATA_INSPECTION_UNAVAILABLE")
    rows = inspected.stdout.strip().splitlines()
    if len(rows) != len(paths):
        raise ReadinessBlocked("QA_SECRET_METADATA_UNEXPECTED")
    for position, line in enumerate(rows):
        parts = line.split(" ", 4)
        if len(parts) != 5:
            raise ReadinessBlocked("QA_SECRET_METADATA_UNEXPECTED")
        mode, uid, gid, size, kind = parts
        expected_mode = "700" if position == 0 else "600"
        expected_type = "directory" if position == 0 else "regular file"
        if (mode != expected_mode or uid != str(APP_UID)
                or gid != str(APP_GID) or kind != expected_type
                or not size.isdecimal()
                or (position != 0 and not 1 <= int(size) <= 8192)):
            raise ReadinessBlocked("QA_SECRET_METADATA_NOT_RESTRICTED")


def _candidate_source_guards():
    app = (SOURCE_DIR / "app.py").read_text("utf-8")
    docker = (SOURCE_DIR / "Dockerfile.r31_11_4_private_candidate").read_text("utf-8")
    adapter = (SOURCE_DIR / "r31_11_4_runtime_rls_adapter.py").read_text("utf-8")
    if (not all(x in app for x in (
            'SBI_R31_PRIVATE_STAGING_ENABLED',
            'SBI_R31_11_4_RUNTIME_ENABLED',
            'app.register_blueprint(runtime_r3114)'))
            or 'USER 10001:10001' not in docker
            or 'r31_11_4_runtime_rls_adapter.py /app/' not in docker
            or 'SBI_R31_11_4_RUNTIME_ENABLED' not in adapter
            or 'default_transaction_read_only=on' not in adapter
            or 'sbi_r31_11_4_auth_qa_20261126' not in adapter):
        raise ReadinessBlocked("QA_CANDIDATE_SOURCE_GUARD_FAILED")


def _no_private_qa_runtime_deployment():
    # Existing dedicated PostgreSQL is permitted; an R31.11.4 API is not.
    run = subprocess.run(
        ["sudo", "-n", "docker", "ps", "--format", "{{.Names}}"],
        check=False, capture_output=True, text=True, timeout=20,
    )
    if run.returncode:
        raise ReadinessBlocked("QA_DOCKER_INSPECT_UNAVAILABLE")
    forbidden = {"sbi-r3114-private-api", "sbi-r3114-auth-qa",
                 "sbi-r3114-runtime", "sbi-r3114e-private-api"}
    if forbidden.intersection(run.stdout.splitlines()):
        raise ReadinessBlocked("QA_RUNTIME_DEPLOYMENT_NOT_AUTHORIZED")


def _read_only_qa_catalog():
    if (readiness.NEW_PG != roles.PG
            or readiness.NEW_DB != roles.DB
            or readiness.NEW_NET != "sbi-r3114-private-isolated"):
        raise ReadinessBlocked("QA_TARGET_CHANGED")
    info = readiness._inspect(readiness.NEW_PG)
    networks = json.loads(readiness._docker(
        "network", "inspect", readiness.NEW_NET))
    if (type(networks) is not list or len(networks) != 1
            or not readiness._candidate_isolated(info, networks[0])):
        raise ReadinessBlocked("QA_TOPOLOGY_NOT_ISOLATED")
    readiness._public_route_absent()
    data = readiness._safe_catalog_state()
    if data != {"new_db": 1, "forbidden_dbs": 0}:
        raise ReadinessBlocked("QA_DATABASE_ISOLATION_CHANGED")
    if not readiness._rls_schema_present():
        raise ReadinessBlocked("QA_RLS_SCHEMA_MISSING")
    role_shape = readiness._restricted_role_state()
    if not readiness._restricted_roles_complete(role_shape):
        raise ReadinessBlocked("QA_ROLE_RESTRICTIONS_CHANGED")
    catalog = roles._catalog_counts()
    if (catalog["db"] != roles.DB or catalog["role_count"] != 2
            or catalog["group_count"] != 2 or catalog["maps"] != 2
            or catalog["data_rows"] != 0
            or catalog["policy_count"] != 4
            or catalog["forced_rls"] != 4):
        raise ReadinessBlocked("QA_ROLE_MAP_OR_DATA_CHANGED")


def run_checks():
    _candidate_source_guards()
    infra.preflight()
    _read_only_qa_catalog()
    print("DB_R31_11_4E_PRIVATE_PG16_RLS=PASS_READONLY", flush=True)
    # Firebase Admin SDK READ requests verify that both existing users are
    # enabled, verified, explicitly dashboard-authorized, and non-admin.
    approved = roles._approved_users()
    if len(approved) != 2 or approved[0]["uid"] == approved[1]["uid"]:
        raise ReadinessBlocked("QA_APPROVED_USERS_NOT_DISTINCT")
    print("DB_R31_11_4E_TWO_REAL_FIREBASE_USERS=PASS_ADMIN_READONLY", flush=True)
    _secure_metadata()
    print("DB_R31_11_4E_SECRET_METADATA=PASS_UID10001_MODE0600", flush=True)
    _no_private_qa_runtime_deployment()
    print("DB_R31_11_4E_RUNTIME=UNDEPLOYED_APPROVAL_REQUIRED", flush=True)
    print("DB_R31_11_4E_MODE=SOURCE_AND_QA_READINESS_ONLY", flush=True)


def main():
    print("=== DB-R31.11.4E FIREBASE-TO-POSTGRES SESSION READINESS ===",
          flush=True)
    try:
        run_checks()
        return 0
    except ReadinessBlocked as reason:
        # Exactly allowlisted static codes. No paths, Firebase UIDs, emails,
        # tokens, raw Google SDK, Docker, SQL or sudo errors can leak.
        allowed = {
            "QA_SECRET_METADATA_INSPECTION_UNAVAILABLE",
            "QA_SECRET_METADATA_UNEXPECTED",
            "QA_SECRET_METADATA_NOT_RESTRICTED",
            "QA_RUNTIME_DEPLOYMENT_NOT_AUTHORIZED",
            "QA_DOCKER_INSPECT_UNAVAILABLE",
            "QA_CANDIDATE_SOURCE_GUARD_FAILED",
            "QA_TARGET_CHANGED",
            "QA_TOPOLOGY_NOT_ISOLATED",
            "QA_DATABASE_ISOLATION_CHANGED",
            "QA_RLS_SCHEMA_MISSING",
            "QA_ROLE_RESTRICTIONS_CHANGED",
            "QA_ROLE_MAP_OR_DATA_CHANGED",
            "QA_APPROVED_USERS_NOT_DISTINCT",
        }
        code = str(reason)
        if code not in allowed:
            code = "UNCLASSIFIED_READINESS_FAILURE"
        print("DB_R31_11_4E_BLOCK_REASON=" + code, flush=True)
        print("STOP=DB_R31_11_4E_PRIVATE_ACCEPTANCE_REVIEW_REQUIRED",
              flush=True)
        return 2
    except Exception:
        # Unexpected errors also fail closed; never display raw exceptions.
        print("DB_R31_11_4E_BLOCK_REASON=UNCLASSIFIED_READINESS_FAILURE",
              flush=True)
        print("STOP=DB_R31_11_4E_PRIVATE_ACCEPTANCE_REVIEW_REQUIRED",
              flush=True)
        return 2
    finally:
        print("DB_R31_11_4E_REAL_SESSION_E2E=NOT_TESTED", flush=True)
        print("DB_R31_11_4E_EXTERNAL_MTLS_HTTPS=PENDING", flush=True)
        print("DB_R31_11_4E_FINANCIAL_APPLY=LOCKED", flush=True)
        print("DB_R31_11_4E_R3112=QUARANTINED", flush=True)
        print("DB_R31_11_4E_RELEASE=PRODUCTION_BLOCKED", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
