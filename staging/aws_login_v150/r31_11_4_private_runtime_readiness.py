#!/usr/bin/env python3
"""DB-R31.11.4: read-only private runtime provisioning readiness audit.

NEVER creates databases, roles, users, passwords, routes or containers. The
original R31.11 clone has passed its synthetic QA and MUST NOT be repurposed
for real Firebase UID/LOGIN role provisioning.

No real two-user Firebase or external mTLS acceptance is claimed.
R31.12 financial integration remains quarantined.
"""
from __future__ import annotations

import json
import subprocess

from r31_real_firebase_qa_acceptance import preflight, PG, QA_DB, STAGE
from r31_11_3_runtime_rls_adapter import QA_DB as PREVIOUS_DB, QA_HOST as PREVIOUS_HOST

NEW_PG = "sbi-r3114-private-postgres"
NEW_DB = "sbi_r31_11_4_auth_qa_20261126"
NEW_NET = "sbi-r3114-private-isolated"
CADDY = "aws_lightsail-caddy-1"
BLOCKED_DB_NAMES = frozenset((
    "sbi_reconciliation_main", "sbi_reconciliation_staging",
    "sbi_r31_owner_qa_20261125", "sbi_r31_11_tenant_clone_20261125",
))

class AuditBlocked(RuntimeError):
    """Safe refusal; no raw Docker, DB or private errors surfaced."""


def _docker(*args, allow_absent=False):
    result = subprocess.run(
        ["sudo", "-n", "docker", *args],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode:
        if allow_absent and result.returncode == 1:
            return None
        raise AuditBlocked("DOCKER_READONLY_CHECK_FAILED")
    return result.stdout.strip()


def _inspect(name, *, allow_absent=False):
    raw = _docker("inspect", name, allow_absent=allow_absent)
    if raw is None:
        return None
    obj = json.loads(raw)
    if type(obj) is not list or len(obj) != 1:
        raise AuditBlocked("DOCKER_INSPECT_INVALID")
    return obj[0]


def _candidate_isolated(info, network):
    """Review metadata only: no role changes, API routing, or DB access."""
    if type(info) is not dict or type(network) is not dict:
        return False
    cfg = info.get("Config") or {}
    host = info.get("HostConfig") or {}
    state = info.get("State") or {}
    networks = (info.get("NetworkSettings") or {}).get("Networks") or {}
    mount_destinations = [mount.get("Destination", "") for mount
                          in info.get("Mounts", []) if isinstance(mount, dict)]
    return (
        state.get("Running") is True
        and cfg.get("Image") not in (None, "")
        and host.get("Privileged") is False
        and host.get("PortBindings") in (None, {})
        and set(networks) == {NEW_NET}
        and network.get("Internal") is True
        and network.get("Attachable") is False
        and not any(
            dest.startswith(("/var/run/docker.sock", "/run/docker.sock",
                             "/var/run/postgresql", "/run/postgresql",
                             "/run/secrets/r31-"))
            for dest in mount_destinations
        )
    )


def _public_route_absent():
    config = _docker("exec", CADDY, "cat", "/etc/caddy/Caddyfile")
    if any(value in config for value in (
        NEW_PG, "sbi-r3114-private-api", "sbi-r31-auth-private-qa",
        "sbi-r31-auth-qa"
    )):
        raise AuditBlocked("UNAPPROVED_PUBLIC_QA_ROUTING")
    return True


def _safe_catalog_state():
    """Only names/counts, never actual account or payment rows."""
    query = """
    SELECT json_build_object(
        'new_db',COUNT(*) FILTER (WHERE datname='sbi_r31_11_4_auth_qa_20261126'),
        'forbidden_dbs',COUNT(*) FILTER (
          WHERE datname IN (
            'sbi_reconciliation_main','sbi_reconciliation_staging',
            'sbi_r31_owner_qa_20261125',
            'sbi_r31_11_tenant_clone_20261125')
        )
    )::text FROM pg_database;
    """
    raw = _docker("exec", NEW_PG, "psql", "-X", "-qAt",
                  "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                  "-d", "postgres", "-c", query)
    obj = json.loads(raw)
    if (type(obj) is not dict
            or type(obj.get("new_db")) is not int
            or type(obj.get("forbidden_dbs")) is not int):
        raise AuditBlocked("DB_CATALOG_INVALID")
    return obj


def audit():
    print("=== DB-R31.11.4 PRIVATE RUNTIME PROVISIONING READINESS ===",flush=True)
    # R31.7 pins the original private Docker image and network and verifies
    # production main DB is absent from that isolated Postgres container.
    preflight()
    if (PG != "sbi-synthetic-postgres-38-31"
            or QA_DB != "sbi_r31_owner_qa_20261125"
            or STAGE != "sbi-r31-auth-private-qa"):
        raise AuditBlocked("EXISTING_QA_IDENTITY_CHANGED")
    if (PREVIOUS_HOST != PG
            or PREVIOUS_DB != "sbi_r31_11_tenant_clone_20261125"):
        raise AuditBlocked("R3113_ADAPTER_TARGET_UNEXPECTED")
    print("DB_R31_11_4_R3113_TARGET=EXISTING_SYNTHETIC_CLONE_NOT_APPROVED_FOR_REAL_USERS",
          flush=True)
    _public_route_absent()
    print("DB_R31_11_4_CADDY_PRIVATE_QA_REFERENCE=ABSENT",flush=True)
    info = _inspect(NEW_PG, allow_absent=True)
    if info is None:
        print("DB_R31_11_4_SEPARATE_AUTH_POSTGRES=NOT_PROVISIONED",flush=True)
        return False
    net_raw = _docker("network", "inspect", NEW_NET)
    networks = json.loads(net_raw)
    if type(networks) is not list or len(networks) != 1:
        raise AuditBlocked("CANDIDATE_NETWORK_INVALID")
    if not _candidate_isolated(info,networks[0]):
        raise AuditBlocked("CANDIDATE_NETWORK_OR_HOST_NOT_ISOLATED")
    print("DB_R31_11_4_SEPARATE_AUTH_POSTGRES=PRIVATE_ISOLATION_PASS",
          flush=True)
    state = _safe_catalog_state()
    if state["forbidden_dbs"] != 0:
        raise AuditBlocked("CANDIDATE_HAS_FORBIDDEN_DATABASE")
    if state["new_db"] != 1:
        print("DB_R31_11_4_SEPARATE_AUTH_DATABASE=NOT_PROVISIONED",flush=True)
        return False
    print("DB_R31_11_4_SEPARATE_AUTH_DATABASE=FOUND_READONLY",flush=True)
    # The existence of a DB does NOT prove role/password/owner binding QA.
    # That verification requires two approved real Firebase users and an
    # independently reviewed provisioning script. Do not guess them.
    return False


def main():
    try:
        infra_ready = audit()
    except (AuditBlocked, ValueError, KeyError, TypeError,
            OSError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_11_4_READONLY_PROVISIONING_PREFLIGHT_BLOCKED",
              flush=True)
        infra_ready = False
    print("DB_R31_11_4_LOGIN_ROLE_PROVISIONING=NOT_AUTHORIZED_BY_THIS_AUDIT",
          flush=True)
    print("DB_R31_11_4_FIREBASE_TWO_USERS=PENDING_SECOND_APPROVED_ACCOUNT",
          flush=True)
    print("DB_R31_11_4_FIREBASE_TO_DB_ACCEPTANCE=NOT_EXECUTED",flush=True)
    print("DB_R31_11_4_EXTERNAL_MTLS_HTTPS=NOT_APPROVED",flush=True)
    print("DB_R31_11_4_R3112_FINANCIAL_INTEGRATION=QUARANTINED",flush=True)
    print("DB_R31_11_4_FINANCIAL_APPLY=LOCKED",flush=True)
    print("DB_R31_11_4_PRODUCTION_WRITES=NONE_BY_AUDIT",flush=True)
    print("DB_R31_11_4_RELEASE=PRODUCTION_BLOCKED_PRIVATE_ACCEPTANCE_PENDING",
          flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
