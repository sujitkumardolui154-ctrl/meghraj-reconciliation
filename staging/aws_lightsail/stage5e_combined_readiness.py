#!/usr/bin/env python3
"""Stage 5E combined non-mutating rollout-readiness audit, no secrets.

Checks running image/rollback identity, Caddy asset mount metadata, intended
storage destinations and application route gap. No Docker run/start/stop,
network calls, financial database, or cloud credentials.
"""
from __future__ import annotations

import json
import subprocess
import sys

NAMES = (
    "aws_lightsail-sbi-preview-1",
    "sbi-agent-stage",
    "sbi-dashboard-ui-stage",
    "aws_lightsail-caddy-1",
)
EXPECTED_LOCAL = {
    "sbi-agent-stage": "sbi-stage-candidate:11c3166728a8",
    "sbi-dashboard-ui-stage": "caddy:2",
}

def inspect(name):
    p = subprocess.run(["docker", "container", "inspect", name],
                       check=False, capture_output=True, text=True, timeout=15)
    if p.returncode:
        raise RuntimeError("container inspection failed: " + name)
    docs = json.loads(p.stdout)
    if not isinstance(docs, list) or len(docs) != 1:
        raise RuntimeError("unexpected inspection response: " + name)
    return docs[0]

def image_exists(identifier):
    p = subprocess.run(["docker", "image", "inspect", identifier, "--format", "{{.Id}}"],
                       check=False, capture_output=True, text=True, timeout=15)
    return p.returncode == 0 and p.stdout.strip() == identifier

def summarize(doc, name):
    host = doc.get("HostConfig") or {}
    cfg = doc.get("Config") or {}
    state = doc.get("State") or {}
    image = doc.get("Image") or ""
    mounts = [{
        "destination": x.get("Destination"),
        "type": x.get("Type"),
        "read_only": not bool(x.get("RW", False)),
        # Host mount Source intentionally suppressed to avoid leaking paths.
    } for x in doc.get("Mounts", [])]
    networks = sorted((doc.get("NetworkSettings") or {}).get("Networks", {}).keys())
    ports = {}
    for target, bindings in (host.get("PortBindings") or {}).items():
        ports[target] = sorted(
            ({"host_ip": x.get("HostIp"), "host_port": x.get("HostPort")}
             for x in (bindings or [])),
            key=lambda x: (str(x["host_ip"]), str(x["host_port"]))
        )
    return {
        "name": name, "running": bool(state.get("Running")),
        "image_tag": cfg.get("Image"), "immutable_image_id": image,
        "rollback_image_present": image_exists(image) if image else False,
        "networks": networks, "ports": ports,
        "mounts": mounts, "read_only_root": bool(host.get("ReadonlyRootfs")),
        "privileged": bool(host.get("Privileged")),
        "security_opt": host.get("SecurityOpt"), "cap_drop": host.get("CapDrop"),
        "cap_add": host.get("CapAdd")
    }

def evaluate(records):
    by = {r["name"]: r for r in records}
    deviations = []
    for name, image in EXPECTED_LOCAL.items():
        r = by[name]
        if not r["running"] or r["image_tag"] != image:
            deviations.append(name + ": running/image drift")
    for name in NAMES:
        if not by[name]["rollback_image_present"]:
            deviations.append(name + ": immutable rollback image missing locally")
    if not any(x["destination"] == "/srv" for x in by["sbi-dashboard-ui-stage"]["mounts"]):
        deviations.append("dashboard /srv content mount missing")
    # This is an inventory, not a pass for tenant/role/session/auth parity.
    return {
        "stage": "5E", "kind": "READ_ONLY_DEPLOYMENT_GAP_INVENTORY",
        "results": records, "deviations": deviations,
        "security_candidate": "SYNTHETIC_ONLY",
        "persistent_caddy_storage": "UNVERIFIED",
        "actual_dashboard_routes": "UNVERIFIED",
        "cloud_run_login_v150_parity": "UNVERIFIED",
        "authenticated_e2e": "UNVERIFIED",
        "rollback_execution": "NOT_PERFORMED",
        "current_deployment_changed": False,
        "financial_write_performed": False,
        "next_gate": "PRIVATE_AUTHENTICATED_STAGE_TEST_AND_PERSISTENCE_REVIEW",
        "status": "REVIEW_REQUIRED" if deviations else "INVENTORY_PASS_RELEASE_NOT_APPROVED",
    }

def main():
    try:
        report = evaluate([summarize(inspect(n), n) for n in NAMES])
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if report["deviations"] else 0
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print("STAGE5E_AUDIT_BLOCKED=" + type(e).__name__ + ": " + str(e), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
