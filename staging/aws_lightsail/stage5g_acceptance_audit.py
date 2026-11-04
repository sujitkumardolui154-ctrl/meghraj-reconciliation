#!/usr/bin/env python3
"""Stage 5G: combined real-service acceptance inventory (non-destructive).

No secrets, no financial API writes, no docker run/exec, no mounts or service restart.
Local loopback HTTP GET only to explicitly approved routes. Actual persistent
recovery, HTTPS trust, privileged session auth, and Cloud Run parity remain gated.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

CADDY = "aws_lightsail-caddy-1"
AGENT = "sbi-agent-stage"
UI = "sbi-dashboard-ui-stage"
PREVIEW = "aws_lightsail-sbi-preview-1"
NAMES = (CADDY, AGENT, UI, PREVIEW)

def container(name):
    p = subprocess.run(["docker", "container", "inspect", name],
                       capture_output=True, text=True, timeout=12)
    if p.returncode:
        raise RuntimeError("Docker inspection failed: " + name)
    data = json.loads(p.stdout)
    if len(data) != 1:
        raise RuntimeError("Unexpected Docker response: " + name)
    return data[0]

def http_code(port, path):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method="GET", headers={"User-Agent": "SBI-5G-read-only-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return "CONNECTION_FAILED"

def main():
    evidence = {"stage": "5G", "mode": "READ_ONLY_ACCEPTANCE",
                "production_changed": False, "financial_writes": 0}
    try:
        docs = {n: container(n) for n in NAMES}
        evidence["containers"] = {}
        for name, d in docs.items():
            evidence["containers"][name] = {
                "running": bool(d.get("State", {}).get("Running")),
                "image_id": d.get("Image"),
                "mounts": [
                    {"destination": m.get("Destination"),
                     "type": m.get("Type"), "rw": m.get("RW"),
                     "named_volume": m.get("Name") if m.get("Type") == "volume" else None}
                    for m in d.get("Mounts", [])],
            }
        mounts = evidence["containers"][CADDY]["mounts"]
        volumes = {m["destination"]: m for m in mounts if m["type"] == "volume"}
        evidence["persistent_storage"] = {
            d: "NAMED_VOLUME_MOUNT_PRESENT" if d in volumes and volumes[d]["rw"]
            else "MISSING_OR_READONLY" for d in ("/data", "/config")}
        evidence["http"] = {
            "ui_root_18081": http_code(18081, "/"),
            "agent_root_18082": http_code(18082, "/"),
            "agent_health_18082": http_code(18082, "/healthz"),
            "agent_upload_unauth_18082": http_code(18082, "/api/upload"),
            "agent_imports_unauth_18082": http_code(18082, "/api/imports"),
        }
        checks = {
            "all_four_containers_running": all(v["running"] for v in evidence["containers"].values()),
            "ui_root_200": evidence["http"]["ui_root_18081"] == 200,
            "agent_login_401": evidence["http"]["agent_root_18082"] == 401,
            "agent_health_200": evidence["http"]["agent_health_18082"] == 200,
            "protected_upload_not_open": evidence["http"]["agent_upload_unauth_18082"] in (401, 403, 404, 405, 503),
            "protected_imports_not_open": evidence["http"]["agent_imports_unauth_18082"] in (401, 403, 404, 405, 503),
            "caddy_named_volumes": all(x == "NAMED_VOLUME_MOUNT_PRESENT" for x in evidence["persistent_storage"].values()),
        }
        evidence["checks"] = checks
        evidence["gates_not_exercised"] = [
            "actual_caddy_certificates_survive_restart",
            "nonroot_persistent_volume_recovery",
            "real_authenticated_session_access",
            "public_HTTPS_certificate_validation",
            "full_cloud_run_login_v150_feature_parity",
            "live_rollback",
        ]
        evidence["result"] = "INVENTORY_PASS_RELEASE_RESTRICTED" if all(checks.values()) else "REVIEW_REQUIRED"
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if all(checks.values()) else 2
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as ex:
        print("STAGE5G_BLOCKED=" + type(ex).__name__ + ": " + str(ex), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
