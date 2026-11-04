#!/usr/bin/env python3
"""SBI Stage 5E: non-destructive Docker hardening preflight.

Never starts/stops/updates existing named services, publishes ports, binds
host paths, mounts the Docker socket, or accesses finance credentials.
Optional smoke creates only network-disabled --rm test containers.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

CONTAINERS = ("sbi-agent-stage", "sbi-dashboard-ui-stage")
EXPECTED = {
    "sbi-agent-stage": "sbi-stage-candidate:11c3166728a8",
    "sbi-dashboard-ui-stage": "caddy:2",
}
CHECKS = (
    ("sbi-agent-stage", "python3", ["-c", "import os;print('UID=%s GID=%s'%(os.getuid(),os.getgid()))"]),
    ("sbi-dashboard-ui-stage", "/usr/bin/caddy", ["version"]),
)
RUNTIME_FLAGS = [
    "--rm", "--pull=never", "--network=none", "--read-only",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,uid=65534,gid=65534,mode=0700",
    "--tmpfs", "/data:rw,noexec,nosuid,size=16m,uid=65534,gid=65534,mode=0700",
    "--tmpfs", "/config:rw,noexec,nosuid,size=16m,uid=65534,gid=65534,mode=0700",
    "--user", "65534:65534", "--cap-drop=ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "64", "--memory", "128m", "--cpus", "0.5",
]
# Above is an intentionally conservative, isolated candidate, not the final
# configuration: Caddy may need different UID, /data and /config persistence,
# port binding and filesystem ownership when an actual deployment is designed.


def docker_json(kind: str, name: str) -> dict:
    cp = subprocess.run(
        ["docker", kind, "inspect", name],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if cp.returncode:
        raise RuntimeError(f"{kind} inspect failed for {name}")
    payload = json.loads(cp.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError(f"unexpected inspect shape for {name}")
    return payload[0]


def inventory() -> list[dict]:
    result = []
    for container in CONTAINERS:
        doc = docker_json("container", container)
        host = doc.get("HostConfig") or {}
        cfg = doc.get("Config") or {}
        image = cfg.get("Image") or ""
        if image != EXPECTED[container]:
            raise RuntimeError(
                f"{container}: unexpected image; expected {EXPECTED[container]}, "
                "do not test a different release without review"
            )
        if not doc.get("State", {}).get("Running", False):
            raise RuntimeError(f"{container}: not running; no candidate inference")
        result.append({
            "container": container,
            "image": image,
            "running": True,
            "configured_user": cfg.get("User") or "(image default)",
            "privileged": bool(host.get("Privileged")),
            "read_only_root": bool(host.get("ReadonlyRootfs")),
            "cap_add": host.get("CapAdd"),
            "cap_drop": host.get("CapDrop"),
            "security_opt": host.get("SecurityOpt"),
            "network_mode": host.get("NetworkMode"),
            "mount_destinations": [m.get("Destination", "") for m in doc.get("Mounts", [])],
        })
    return result


def smoke() -> list[dict]:
    result = []
    for container, entrypoint, args in CHECKS:
        # Caddy's /usr/bin/caddy has cap_net_bind_service=ep. With all
        # capabilities dropped, exec fails EPERM under no-new-privileges.
        # Allow only NET_BIND_SERVICE for the Caddy image (owner-tested).
        extra = ["--cap-add", "NET_BIND_SERVICE"] if container == "sbi-dashboard-ui-stage" else []
        command = (["docker", "run", *RUNTIME_FLAGS, *extra, "--entrypoint",
                    entrypoint, EXPECTED[container], *args])
        cp = subprocess.run(
            command, capture_output=True, text=True, timeout=35, check=False
        )
        result.append({
            "container": container,
            "result": "PASS" if cp.returncode == 0 else "FAIL",
            "exit_code": cp.returncode,
            "output_tail": (cp.stdout + cp.stderr)[-600:],
            "network_disabled": True,
            "temporary_container_only": True,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke", action="store_true",
        help="explicitly run disposable, network-disabled non-root tests",
    )
    args = parser.parse_args()
    try:
        summary = {"phase": "STAGE5E", "mode": "SMOKE" if args.smoke else "INVENTORY",
                   "production_changed": False, "finance_writes": 0,
                   "inventory": inventory()}
        if args.smoke:
            summary["smoke"] = smoke()
            summary["result"] = ("PASS_SYNTHETIC_ONLY" if all(
                x["result"] == "PASS" for x in summary["smoke"]
            ) else "REVIEW_REQUIRED")
        else:
            summary["result"] = "INVENTORY_ONLY"
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["result"] != "REVIEW_REQUIRED" else 2
    except (RuntimeError, ValueError, json.JSONDecodeError, OSError,
            subprocess.TimeoutExpired) as exc:
        print(f"STAGE5E_BLOCKED={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
