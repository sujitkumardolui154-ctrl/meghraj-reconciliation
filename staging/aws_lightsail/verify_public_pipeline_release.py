#!/usr/bin/env python3
"""Read-only AWS public-preview attestation, without exposing login credentials.

Run on the Lightsail host with:
    sudo python3 staging/aws_lightsail/verify_public_pipeline_release.py

Does not build, restart, publish or mutate any service or financial database.
Host-local Docker credential variables are never printed or saved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "staging" / "aws_lightsail"
AUDITS = Path("/var/log/sbi-public-dashboard")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
CHECK = r"""
import base64
import json
import os
import urllib.error
import urllib.request

user = os.environ.get("PREVIEW_USERNAME", "")
secret = os.environ.get("PREVIEW_PASSWORD", "")
token = "Basic " + base64.b64encode((user + ":" + secret).encode()).decode()

def request(path, auth=False):
    headers = {"Authorization": token} if auth else {}
    r = urllib.request.Request("http://127.0.0.1:8080" + path, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=6) as response:
            return response.status, response.read(450000)
    except urllib.error.HTTPError as error:
        return error.code, b""

statuses = {}
statuses["health"], health = request("/healthz")
statuses["anonymous"], _ = request("/")
statuses["authenticated"], home = request("/", True)
statuses["financial_denied"], _ = request("/api/upload", True)
statuses["version"], payload = request("/api/pipeline/version", True)
statuses["status"], data = request("/api/pipeline/status", True)
version = json.loads(payload) if statuses["version"] == 200 else {}
status = json.loads(data) if statuses["status"] == 200 else {}
health_data = json.loads(health) if statuses["health"] == 200 else {}
safe = {
    "http": statuses,
    "new_html": b"All stages. One control center." in home,
    "source_sha": version.get("source_sha"),
    "version": version.get("version"),
    "channel": version.get("channel"),
    "reported_financial_api_connected": status.get("financial_api_connected"),
    "reported_health_financial_connected": health_data.get("financial_data_connected"),
}
print(json.dumps(safe, sort_keys=True))
"""


class ReleaseReviewRequired(Exception):
    """Public host attestation cannot be fully certified."""


def cmd(*arguments: str) -> str:
    result = subprocess.run(arguments, cwd=COMPOSE, text=True,
                            capture_output=True, timeout=25, check=False)
    if result.returncode:
        raise ReleaseReviewRequired("DOCKER_READ_FAILED")
    return result.stdout.strip()


def verify_receipt(folder: Path, source_sha: str, running_image: str,
                   image_lookup) -> dict[str, str]:
    """Validate a successful local receipt, SHA256 and rollback tag, without writing."""
    if not folder.is_dir() or folder.is_symlink():
        raise ReleaseReviewRequired("RELEASE_AUDIT_DIRECTORY_MISSING")
    for file in sorted(folder.glob("*.json"), reverse=True):
        if file.is_symlink() or not file.is_file():
            continue
        try:
            raw = file.read_bytes()
            record = json.loads(raw)
        except (OSError, ValueError, TypeError):
            continue
        if (not isinstance(record, dict) or record.get("status") != "success"
                or record.get("target") != "aws-public-preview"
                or record.get("source_sha") != source_sha):
            continue
        checksum_path = Path(str(file) + ".sha256")
        if not checksum_path.is_file() or checksum_path.is_symlink():
            raise ReleaseReviewRequired("RELEASE_CHECKSUM_MISSING")
        try:
            line = checksum_path.read_text(encoding="ascii").strip().splitlines()
        except (UnicodeError, OSError):
            raise ReleaseReviewRequired("RELEASE_CHECKSUM_UNREADABLE")
        if len(line) != 1 or len(line[0].split()) < 2:
            raise ReleaseReviewRequired("RELEASE_CHECKSUM_INVALID")
        digest, name = line[0].split(maxsplit=1)
        if name.lstrip("*") not in (str(file), file.name):
            raise ReleaseReviewRequired("RELEASE_CHECKSUM_FILE_MISMATCH")
        if digest != hashlib.sha256(raw).hexdigest():
            raise ReleaseReviewRequired("RELEASE_CHECKSUM_MISMATCH")
        if record.get("new_image") != running_image:
            raise ReleaseReviewRequired("RELEASE_IMAGE_DIGEST_MISMATCH")
        old = record.get("previous_image")
        backup = record.get("backup_tag")
        if not isinstance(old, str) or not old.startswith("sha256:"):
            raise ReleaseReviewRequired("PREVIOUS_IMAGE_MISSING")
        if not isinstance(backup, str) or not re.fullmatch(r"sbi-public-pipeline-backup:[0-9a-f]{12}", backup):
            raise ReleaseReviewRequired("ROLLBACK_TAG_INVALID")
        if image_lookup(backup) != old:
            raise ReleaseReviewRequired("ROLLBACK_IMAGE_NOT_AVAILABLE")
        return {"receipt_file": file.name, "receipt_sha256": digest, "backup_tag": backup}
    raise ReleaseReviewRequired("MATCHING_SUCCESS_RECEIPT_NOT_FOUND")


def verify_live() -> dict[str, str]:
    cid = cmd("docker", "compose", "ps", "-q", "sbi-preview")
    if not cid:
        raise ReleaseReviewRequired("PUBLIC_CONTAINER_MISSING")
    image = cmd("docker", "inspect", cid, "--format", "{{.Image}}")
    if not image.startswith("sha256:"):
        raise ReleaseReviewRequired("RUNNING_IMAGE_DIGEST_INVALID")
    if cmd("docker", "inspect", cid, "--format", "{{.State.Running}}") != "true":
        raise ReleaseReviewRequired("PUBLIC_CONTAINER_NOT_RUNNING")
    if cmd("docker", "inspect", cid, "--format",
           '{{index .Config.Labels "com.docker.compose.service"}}') != "sbi-preview":
        raise ReleaseReviewRequired("COMPOSE_SERVICE_UNEXPECTED")
    if cmd("docker", "inspect", cid, "--format", "{{len .Mounts}}") != "0":
        raise ReleaseReviewRequired("PUBLIC_CONTAINER_MOUNT_DETECTED")
    data = cmd("docker", "exec", cid, "python", "-c", CHECK)
    try:
        probe = json.loads(data)
    except (ValueError, TypeError):
        raise ReleaseReviewRequired("APP_PROBE_INVALID")
    expected_http = {
        "health": 200,
        "anonymous": 401,
        "authenticated": 200,
        "financial_denied": 403,
        "version": 200,
        "status": 200,
    }
    if probe.get("http") != expected_http or probe.get("new_html") is not True:
        raise ReleaseReviewRequired("APP_AUTH_OR_FINANCIAL_GATE_FAILED")
    sha = probe.get("source_sha")
    if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
        raise ReleaseReviewRequired("DEPLOYED_SOURCE_SHA_INVALID")
    if probe.get("version") != "git-" + sha[:12] or probe.get("channel") != "aws-public-preview":
        raise ReleaseReviewRequired("DEPLOYED_VERSION_CHANNEL_MISMATCH")
    if (probe.get("reported_financial_api_connected") is not False
            or probe.get("reported_health_financial_connected") is not False):
        raise ReleaseReviewRequired("FINANCIAL_API_CONNECTION_REPORTED")
    receipt = verify_receipt(AUDITS, sha, image, lambda tag: cmd(
        "docker", "image", "inspect", tag, "--format", "{{.Id}}"))
    return {
        "release_version": "git-" + sha[:12],
        "source_sha": sha,
        "running_image": image,
        "receipt_file": receipt["receipt_file"],
        "authentication": "PASS",
        "financial_api_denial": "PASS",
        "receipt_hash": "PASS",
        "rollback_image": "PASS",
    }


def main() -> int:
    if os.geteuid() != 0:
        print("BLOCKED: root-only Docker and local audit inspection required")
        return 2
    try:
        attested = verify_live()
    except (ReleaseReviewRequired, OSError, subprocess.TimeoutExpired,
            PermissionError) as error:
        code = str(error) if isinstance(error, ReleaseReviewRequired) else "LOCAL_INSPECTION_FAILED"
        print("PUBLIC_RELEASE_ATTESTATION=REVIEW_REQUIRED")
        print("ATTESTATION_BLOCKER=" + code)
        print("HOST_MUTATIONS=0")
        return 2
    print("PUBLIC_RELEASE_ATTESTATION=PASS")
    for key, value in attested.items():
        print(key.upper() + "=" + value)
    print("HOST_MUTATIONS=0")
    print("FINANCIAL_PRODUCTION=RESTRICTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
