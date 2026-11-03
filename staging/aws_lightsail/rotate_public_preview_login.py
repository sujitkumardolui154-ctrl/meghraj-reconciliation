#!/usr/bin/env python3
"""Safely rotate legacy AWS public-preview Basic Auth without printing credentials.

The old preview may have credentials outside the current password policy. This operator-only
migration requires a new 10-15-character password and preserves a root-only local
backup of the original .env (not encrypted).
It changes only the existing sbi-preview service and never the financial stack.
"""
from __future__ import annotations

import base64
import datetime
import fcntl
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time

BRANCH = "aws/lightsail-preview-20261102"
ORIGIN = "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git"
ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = ROOT / "staging" / "aws_lightsail"
ENV_PATH = COMPOSE_DIR / ".env"
BACKUPS = Path("/root/sbi-public-login-backups")
AUDIT_DIR = Path("/var/log/sbi-public-dashboard")
PASSWORD_PATTERN = re.compile(r"[A-Za-z0-9._~-]{10,15}\Z")
SERVICE = "sbi-preview"
VERIFY_CODE = """
import base64, os, urllib.request, urllib.error
pair=(os.environ["PREVIEW_USERNAME"]+":"+os.environ["PREVIEW_PASSWORD"]).encode()
authorization="Basic "+base64.b64encode(pair).decode("ascii")
def code(path, login=False):
    headers={"Authorization":authorization} if login else {}
    req=urllib.request.Request("http://127.0.0.1:8080"+path,headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response: return response.status
    except urllib.error.HTTPError as error:
        return error.code
assert code("/healthz")==200
assert code("/")==401
assert code("/", True)==200
assert code("/api/upload", True) in (403,404)  # Legacy preview may not define this route; never allow 2xx.
"""


def command(*args: str) -> str:
    result = subprocess.run(args, cwd=COMPOSE_DIR, capture_output=True, text=True,
                            check=False, timeout=40)
    if result.returncode:
        # Do not surface potentially sensitive Docker Compose output.
        raise RuntimeError("required git/docker command failed")
    return result.stdout.strip()


def replace_password(text: str, password: str) -> str:
    if not PASSWORD_PATTERN.fullmatch(password):
        raise ValueError("new password must have 10-15 approved characters")
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith("PREVIEW_PASSWORD=")]
    if len(matches) != 1:
        raise ValueError("expected exactly one PREVIEW_PASSWORD assignment in .env")
    idx = matches[0]
    ending = "\r\n" if lines[idx].endswith("\r\n") else "\n"
    lines[idx] = "PREVIEW_PASSWORD=" + password + ending
    return "".join(lines)


def atomic_env(content: str, old_stat: os.stat_result) -> None:
    fd, name = tempfile.mkstemp(prefix=".env.rotate.", dir=COMPOSE_DIR)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, old_stat.st_uid, old_stat.st_gid)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, ENV_PATH)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def compose_login() -> dict[str, str]:
    doc = json.loads(command("docker", "compose", "config", "--format", "json"))
    service = doc.get("services", {}).get(SERVICE)
    if not isinstance(service, dict):
        raise RuntimeError("preview Compose service not found")
    env = service.get("environment")
    if not isinstance(env, dict):
        raise RuntimeError("preview Compose credentials unavailable")
    result = {key: env.get(key) for key in ("PREVIEW_USERNAME", "PREVIEW_PASSWORD")}
    if not all(isinstance(v, str) and v for v in result.values()):
        raise RuntimeError("preview Compose login variables unavailable")
    return result


def container_login(container: str) -> dict[str, str]:
    data = json.loads(command("docker", "inspect", container, "--format",
                              "{{json .Config.Env}}"))
    keys = {}
    for item in data:
        key, _, value = item.partition("=")
        if key in ("PREVIEW_USERNAME", "PREVIEW_PASSWORD"):
            if key in keys:
                raise RuntimeError("duplicate active preview credentials")
            keys[key] = value
    if len(keys) != 2:
        raise RuntimeError("active preview credentials missing")
    return keys


def verify(container: str) -> bool:
    result = subprocess.run(["docker", "exec", container, "python", "-c", VERIFY_CODE],
                            cwd=COMPOSE_DIR, capture_output=True, text=True,
                            check=False, timeout=20)
    return result.returncode == 0


def record_event(sha: str, image: str, backup: Path) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(AUDIT_DIR, 0o700)
    when = datetime.datetime.now(datetime.timezone.utc)
    filename = "auth-rotation-" + when.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(5) + ".json"
    destination = AUDIT_DIR / filename
    event = {
        "event": "public_preview_auth_rotation",
        "timestamp_utc": when.isoformat(),
        "source_sha": sha,
        "image_preserved": image,
        "preview_login_authenticated": True,
        "financial_writes": False,
        "backup_path": str(backup),
    }
    payload = json.dumps(event, sort_keys=True, indent=2) + "\n"
    with destination.open("x", encoding="utf-8") as output:
        os.chmod(destination, 0o600)
        output.write(payload)
    checksum = destination.with_suffix(".json.sha256")
    with checksum.open("x", encoding="utf-8") as output:
        os.chmod(checksum, 0o600)
        output.write(hashlib.sha256(payload.encode("utf-8")).hexdigest() + "  " + filename + "\n")
    print("AUTH_ROTATION_AUDIT=" + str(destination))


def main() -> int:
    if os.geteuid() != 0 or not sys.stdin.isatty():
        print("BLOCKED: run as root from an interactive AWS terminal")
        return 2
    with open("/run/lock/sbi-public-pipeline.lock", "a", encoding="ascii") as lock:
        failure_stage = "PREFLIGHT"
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("BLOCKED: another public-preview release is running")
            return 2
        try:
            sha = command("git", "-C", str(ROOT), "rev-parse", "HEAD")
            active_branch = command("git", "-C", str(ROOT), "branch", "--show-current")
            remote = command("git", "-C", str(ROOT), "remote", "get-url", "origin")
            head = command("git", "-C", str(ROOT), "ls-remote", "origin", "refs/heads/" + BRANCH).split()[0]
            if active_branch != BRANCH or remote != ORIGIN or sha != head:
                raise RuntimeError("source is not the approved AWS public-preview branch")
            if not ENV_PATH.exists() or ENV_PATH.is_symlink():
                raise RuntimeError("public .env must be a regular, non-symlink file")
            info = ENV_PATH.stat()
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError("public .env is not a regular file")
            original = ENV_PATH.read_text(encoding="utf-8")
            failure_stage = "ENV_ASSIGNMENT_FORMAT"
            if sum(line.startswith("PREVIEW_PASSWORD=") for line in original.splitlines()) != 1:
                raise ValueError("expected exactly one password entry")
            failure_stage = "COMPOSE_AND_CONTAINER_CHECK"
            current = compose_login()
            cid = command("docker", "compose", "ps", "-q", SERVICE)
            if not cid:
                raise RuntimeError("existing public service was not found")
            running = command("docker", "inspect", cid, "--format", "{{.State.Running}}")
            label = command("docker", "inspect", cid, "--format",
                            '{{index .Config.Labels "com.docker.compose.service"}}')
            if running != "true" or label != SERVICE:
                raise RuntimeError("existing public service is not healthy/identified")
            old_env = container_login(cid)
            if not all(hmac.compare_digest(current[key], old_env[key]) for key in current):
                raise RuntimeError("current container and Compose login differ; no rotation attempted")
            image_id = command("docker", "inspect", cid, "--format", "{{.Image}}")
            image_tag = command("docker", "inspect", cid, "--format", "{{.Config.Image}}")
            if not image_tag or image_tag.startswith("sha256:"):
                raise RuntimeError("Compose service image tag cannot be safely reused")
            if command("docker", "image", "inspect", image_tag, "--format", "{{.Id}}") != image_id:
                raise RuntimeError("Compose image tag differs from active image; no rotation attempted")
            failure_stage = "PASSWORD_CONFIRMATION"
            new_password = getpass.getpass("New public preview password (10-15 approved characters): ")
            repeat = getpass.getpass("Confirm new preview password: ")
            if not hmac.compare_digest(new_password, repeat):
                raise ValueError("password confirmation mismatch")
            failure_stage = "PASSWORD_REUSE"
            if new_password == current["PREVIEW_PASSWORD"]:
                raise ValueError("new password must be different")
            failure_stage = "PASSWORD_POLICY"
            updated = replace_password(original, new_password)
            del new_password, repeat
            failure_stage = "BACKUP_PREPARATION"
            BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(BACKUPS, 0o700)
            backup = BACKUPS / ("preview-env-" + datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(5))
            with backup.open("xb") as f:
                os.chmod(backup, 0o600)
                f.write(original.encode("utf-8"))
            changed = False
            update_stage = "WRITE_PREVIEW_ENV"
            try:
                changed = True
                atomic_env(updated, info)
                # Validate the actual Compose interpretation before altering the container.
                update_stage = "VALIDATE_UPDATED_ENV"
                replacement = compose_login()
                if replacement["PREVIEW_USERNAME"] != current["PREVIEW_USERNAME"] or not PASSWORD_PATTERN.fullmatch(replacement["PREVIEW_PASSWORD"]):
                    raise RuntimeError("updated Compose login validation failed")
                update_stage = "RECREATE_PUBLIC_PREVIEW"
                command("docker", "compose", "up", "-d", "--no-deps", "--no-build",
                        "--force-recreate", SERVICE)
                cid_new = command("docker", "compose", "ps", "-q", SERVICE)
                if not cid_new:
                    raise RuntimeError("new public preview container not found")
                update_stage = "VERIFY_SAME_IMAGE_AND_LOGIN"
                new_image = command("docker", "inspect", cid_new, "--format", "{{.Image}}")
                if new_image != image_id:
                    raise RuntimeError("public preview image changed unexpectedly")
                # The legacy app can take several seconds to become available.
                for attempt in range(20):
                    if verify(cid_new):
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("new login/health/financial-denial probe failed")
                print("PUBLIC_LOGIN_ROTATION=PASS")
                print("PUBLIC_IMAGE_UNCHANGED=PASS")
                print("FINANCIAL_WRITES=DISABLED")
                try:
                    record_event(sha, image_id, backup)
                except (OSError, ValueError):
                    print("AUDIT_RECEIPT=WRITE_FAILED")
                return 0
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                print("ROTATION_BLOCK_STAGE=" + update_stage)
                if changed:
                    print("AUTH_ROTATION_ROLLBACK=ATTEMPTED")
                    try:
                        atomic_env(original, info)
                        command("docker", "compose", "up", "-d", "--no-deps", "--no-build",
                                "--force-recreate", SERVICE)
                        restored = command("docker", "compose", "ps", "-q", SERVICE)
                        restored_image = command("docker", "inspect", restored, "--format", "{{.Image}}")
                        print("AUTH_ROTATION_ROLLBACK=" + (
                            "PREVIOUS_IMAGE_RESTORED" if restored_image == image_id
                            else "MANUAL_REVIEW_REQUIRED"))
                    except (OSError, RuntimeError, subprocess.TimeoutExpired):
                        print("AUTH_ROTATION_ROLLBACK=MANUAL_REVIEW_REQUIRED")
                return 2
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
                json.JSONDecodeError):
            # Only hard-coded stage labels; never echo exception details or secrets.
            print("ROTATION_BLOCK_STAGE=" + failure_stage)
            print("BLOCKED: safe public-preview credential migration prerequisites failed")
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
