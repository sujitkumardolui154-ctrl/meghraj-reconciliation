#!/usr/bin/env python3
"""ONE AWS Phase 1 combined gate: build, verified data, isolated canary, public release review.

No production deployment, no financial writes, and no existing container mutation.
Use from a pinned GitHub commit on the authorized AWS Lightsail Ubuntu host.
Print status labels only; never output environment variables, credentials or report rows.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request

REPO = Path("/home/ubuntu/sbi-aws-app")
PRIVATE_ROOT = Path("/etc/sbi-phase1-reporting")
PRIVATE_ENV = PRIVATE_ROOT / "candidate.env"
PRIVATE_SNAPSHOT = PRIVATE_ROOT / "snapshot"
PUBLIC_PREVIEW = "https://sbi-preview.13-232-241-221.sslip.io/"
RUNNING = (
    "sbi-backend-readonly-ingress-stage",
    "sbi-backend-readonly-stage",
    "aws_lightsail-sbi-preview-1",
    "sbi-agent-stage",
    "sbi-dashboard-ui-stage",
    "aws_lightsail-caddy-1",
)

# Invoked inside a disconnected, sealed Docker container, without host data on stdout.
PROBE = r'''
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

def request(path, method="GET", authorized=False):
    h = {}
    if authorized:
        u = os.environ.get("SBI_AWS_REPORT_USERNAME", "")
        p = os.environ.get("SBI_AWS_REPORT_PASSWORD", "")
        h["Authorization"] = "Basic " + base64.b64encode((u + ":" + p).encode()).decode()
    req = urllib.request.Request("http://127.0.0.1:8080" + path, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read(50*1024*1024 + 1)
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096)

def check(condition, code):
    if not condition:
        print("CHECK_FAILED=" + code)
        raise SystemExit(2)

for _ in range(20):
    try:
        status, body = request("/healthz")
        if status == 200:
            break
    except Exception:
        time.sleep(.5)
else:
    print("CHECK_FAILED=CANARY_NOT_HEALTHY")
    raise SystemExit(2)

health = json.loads(body)
check(health.get("financial_data_connected") is False, "FINANCIAL_CONNECTED_UNEXPECTED")
check(health.get("financial_execution_enabled") is False, "FINANCIAL_WRITES_UNEXPECTED")
check(request("/reports", authorized=False)[0] == 401, "ANONYMOUS_REPORT_NOT_DENIED")
check(request("/reports", method="POST", authorized=True)[0] == 403,
      "WRITE_HTTP_METHOD_NOT_DENIED")
check(request("/api/upload", authorized=True)[0] == 403, "UPLOAD_NOT_DENIED")
check(request("/imports/preview", authorized=True)[0] == 403, "IMPORT_NOT_DENIED")

mode = os.environ.get("SBI_COMBINED_QA_MODE")
ready, _ = request("/readyz")
status, raw = request("/reports", authorized=True)
if mode == "FAIL_CLOSED":
    check(ready == 503, "UNCONFIGURED_READY_SHOULD_503")
    check(status == 503, "UNCONFIGURED_REPORTS_SHOULD_503")
    print("CANARY_AUTH_NEGATIVE=PASS")
    print("CANARY_UNCONFIGURED_FAIL_CLOSED=PASS")
elif mode == "PRIVATE_SNAPSHOT":
    check(ready == 200, "PRIVATE_SNAPSHOT_NOT_READY")
    check(status == 200, "PRIVATE_SNAPSHOT_REPORT_INDEX_NOT_200")
    catalog = json.loads(raw)
    check(catalog.get("reconciliation_executed") is False,
          "RECONCILIATION_EXE_UNEXPECTED")
    reports = catalog.get("reports", {})
    check({"unpaid", "ok", "balance-review"} <= reports.keys(),
          "CORE_REPORTS_MISSING")
    file_rows = 0
    for kind, entry in reports.items():
        status, data = request("/reports/" + kind + ".csv", authorized=True)
        check(status == 200, "PRIVATE_CSV_HTTP_FAILED_" + kind)
        check(len(data) <= 50*1024*1024, "PRIVATE_CSV_TOO_LARGE_" + kind)
        manifest = json.loads(open("/approved-snapshot/manifest.json", "rb").read())
        expected = manifest["reports"][kind]["sha256"]
        check(hashlib.sha256(data).hexdigest() == expected, "CSV_HASH_FAILED_" + kind)
        check(entry["rows"] == manifest["reports"][kind]["row_count"],
              "CSV_ROW_COUNT_FAILED_" + kind)
        file_rows += entry["rows"]
    print("CANARY_AUTH_NEGATIVE=PASS")
    print("PRIVATE_SNAPSHOT_HASHED_REPORTS=PASS")
    print("PRIVATE_SNAPSHOT_REPORT_KINDS=" + str(len(reports)))
    print("PRIVATE_SNAPSHOT_REPORTED_ROWS=" + str(file_rows))
else:
    print("CHECK_FAILED=UNKNOWN_MODE")
    raise SystemExit(2)
print("FINANCIAL_WRITES=NOT_PERFORMED")
'''.lstrip()


def announce(key, value):
    print("{}={}".format(key, value), flush=True)


def call(cmd, *, check=True, capture=False, quiet=False, input_text=None):
    kwargs = {"text": True, "check": check}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    elif quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if input_text is not None:
        kwargs["input"] = input_text
    return subprocess.run(cmd, **kwargs)


def git(*args, capture=True):
    return call(["git", "-C", str(REPO), *args], capture=capture).stdout.strip()


def choose_docker():
    if call(["docker", "info"], check=False, quiet=True).returncode == 0:
        return ["docker"]
    if shutil.which("sudo") and call(
        ["sudo", "-n", "docker", "info"], check=False, quiet=True
    ).returncode == 0:
        return ["sudo", "-n", "docker"]
    raise RuntimeError("DOCKER_ACCESS_NOT_AUTHORIZED")


def image_ref(docker, container):
    result = call(
        docker + ["container", "inspect", "--format", "{{.Id}}|{{.Image}}|{{.State.Running}}", container],
        check=False, capture=True,
    )
    if result.returncode:
        raise RuntimeError("EXPECTED_CONTAINER_MISSING_" + container)
    fields = result.stdout.strip().split("|")
    if len(fields) != 3 or fields[2] != "true":
        raise RuntimeError("EXPECTED_CONTAINER_NOT_RUNNING_" + container)
    return tuple(fields)


def baseline(docker):
    return {name: image_ref(docker, name) for name in RUNNING}


def private_configuration():
    # Separate root-controlled AWS secrets, not the pre-existing staging env file.
    # Fail closed; neither create nor print a credential or a finance file.
    if not PRIVATE_ENV.exists() and not PRIVATE_SNAPSHOT.exists():
        return False
    if not PRIVATE_ENV.is_file() or not PRIVATE_SNAPSHOT.is_dir():
        raise RuntimeError("PRIVATE_SNAPSHOT_PARTIAL_CONFIGURATION")
    env_info = PRIVATE_ENV.lstat()
    if (stat.S_ISLNK(env_info.st_mode) or env_info.st_uid != 0
            or (stat.S_IMODE(env_info.st_mode) & 0o077)):
        raise RuntimeError("PRIVATE_ENV_OWNER_OR_MODE_INVALID")
    if PRIVATE_SNAPSHOT.is_symlink() or PRIVATE_SNAPSHOT.joinpath("manifest.json").is_symlink():
        raise RuntimeError("PRIVATE_SNAPSHOT_SYMLINK_FORBIDDEN")
    # The Docker daemon reads env-file via its invoking client; root-only
    # env files may require the operator to run this script via an approved
    # privileged environment (not by bypassing the release guard).
    if not os.access(PRIVATE_ENV, os.R_OK):
        raise RuntimeError("PRIVATE_ENV_NOT_READABLE_USE_AUTHORIZED_OPERATOR")
    return True


def launch(docker, name, image, has_private):
    cmd = docker + [
        "run", "-d", "--rm",
        "--name", name,
        "--label", "sbi.phase1.combined_gate=isolated",
        "--network", "none", "--restart", "no",
        "--user", "10001:10001", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "256m",
        "-e", "SBI_COMBINED_QA_MODE=" + ("PRIVATE_SNAPSHOT" if has_private else "FAIL_CLOSED"),
    ]
    if has_private:
        cmd += [
            "--env-file", str(PRIVATE_ENV),
            "--mount", "type=bind,src={},dst=/approved-snapshot,readonly".format(PRIVATE_SNAPSHOT),
        ]
    else:
        # Synthetic credentials only, no data mount and no network access.
        cmd += [
            "-e", "SBI_AWS_REPORT_USERNAME=offline-synthetic",
            "-e", "SBI_AWS_REPORT_PASSWORD=not-a-real-password-for-isolated-qa-2026",
        ]
    cmd.append(image)
    result = call(cmd, capture=True)
    if len(result.stdout.strip()) != 64:
        raise RuntimeError("CANDIDATE_CONTAINER_ID_INVALID")


def host_public_preview():
    req = urllib.request.Request(PUBLIC_PREVIEW, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return "UNREACHABLE"


def main():
    announce("=== SBI AWS PHASE1 SINGLE COMBINED GATE ===", "START")
    required_sha = os.environ.get("SBI_COMBINED_SOURCE_SHA", "").strip()
    if len(required_sha) != 40 or any(c not in "0123456789abcdef" for c in required_sha):
        raise RuntimeError("PINNED_SOURCE_SHA_REQUIRED")
    if not REPO.joinpath(".git").exists() and not git("rev-parse", "--is-inside-work-tree") == "true":
        raise RuntimeError("AWS_SOURCE_CHECKOUT_MISSING")
    # The operator's fetch and commit verification happen before invoking
    # this runner. Insist the exact commit is already available locally.
    full_sha = git("rev-parse", required_sha + "^{commit}")
    if full_sha != required_sha:
        raise RuntimeError("PINNED_GIT_COMMIT_MISMATCH")
    docker = choose_docker()
    before = baseline(docker)
    announce("EXISTING_CONTAINERS_RUNNING", len(before))
    dest = REPO.parent / ("sbi-phase1-combined-" + required_sha[:12])
    if dest.exists():
        existing_sha = call(
            ["git", "-C", str(dest), "rev-parse", "HEAD"], check=False, capture=True
        )
        if existing_sha.returncode != 0 or existing_sha.stdout.strip() != required_sha:
            raise RuntimeError("COMBINED_WORKTREE_PATH_CONFLICT")
    else:
        call(["git", "-C", str(REPO), "worktree", "add", "--detach", str(dest), required_sha],
             quiet=True)
    image = "sbi-phase1-combined:{}".format(required_sha[:12])
    # Build a distinct tag, do not retag or restart the existing containers.
    announce("STAGE1_CANDIDATE_BUILD", "START")
    call(docker + [
        "build", "--build-arg", "SBI_SOURCE_SHA=" + required_sha,
        "-f", str(dest / "staging/aws_phase1_reporting/Dockerfile"),
        "-t", image, str(dest)
    ])
    metadata = call(docker + [
        "image", "inspect", image, "--format",
        "{{.Id}}|{{index .Config.Labels \"org.opencontainers.image.revision\"}}"
    ], capture=True).stdout.strip()
    if len(metadata.split("|")) != 2 or metadata.split("|")[1] != required_sha:
        raise RuntimeError("CANDIDATE_IMAGE_PROVENANCE_MISMATCH")
    announce("STAGE1_CANDIDATE_IMAGE", "PASS_SOURCE_SHA_PINNED")
    try:
        has_private = private_configuration()
    except RuntimeError as error:
        announce("STAGE2_PRIVATE_DATA", "BLOCKED_" + str(error))
        has_private = False
    if not has_private:
        announce("STAGE2_PRIVATE_DATA", "BLOCKED_NO_APPROVED_SNAPSHOT")
    else:
        announce("STAGE2_PRIVATE_DATA", "CONFIG_PRESENT_VALIDATE_IN_CANARY")
    name = "sbi-phase1-combined-{}-{}".format(required_sha[:8], os.getpid())
    safe_canary = False
    cleanup_pass = False
    existing_unchanged = False
    try:
        launch(docker, name, image, has_private)
        probe = call(
            docker + ["exec", "-i", name, "python", "-"],
            capture=True, check=False, input_text=PROBE
        )
        # The probe prints only status labels, never actual customer rows.
        if probe.stdout:
            print(probe.stdout.strip(), flush=True)
        safe_canary = probe.returncode == 0
        announce("STAGE3_ISOLATED_CANARY",
                 "PASS_READONLY_AUTH_CONTRACT" if safe_canary
                 else "FAIL_CLOSED_REVIEW_REQUIRED")
        if safe_canary and has_private:
            announce("STAGE2_SNAPSHOT_HASH_AND_STRUCTURE", "PASS")
    finally:
        # Only stop the ephemeral named container, never existing SBI services.
        call(docker + ["stop", "--time", "3", name], check=False, quiet=True)
        remainder = call(docker + ["container", "inspect", name], check=False, quiet=True)
        cleanup_pass = remainder.returncode != 0
        announce("ISOLATED_CANDIDATE_CLEANUP",
                 "PASS" if cleanup_pass else "REVIEW_REQUIRED")
        after = baseline(docker)
        existing_unchanged = after == before
        announce("EXISTING_CONTAINERS_UNCHANGED",
                 "PASS" if existing_unchanged else "FAIL_REVIEW_REQUIRED")
    code = host_public_preview()
    announce("EXISTING_PUBLIC_PREVIEW_HTTP", code)
    announce("PUBLIC_PREVIEW_ANONYMOUS_ACCESS",
             "PASS_DENIED_401" if code == 401 else "REVIEW_REQUIRED")
    announce("REAL_FIREBASE_LOGIN", "NOT_TESTED")
    announce("INDEPENDENT_SOURCE_VALUE_PARITY", "NOT_VERIFIED_BY_THIS_RUN")
    announce("CREDIT_NOTE_CONFLICT_RESOLUTION", "PENDING_SOURCE_REVIEW")
    announce("PRODUCTION_ROLLBACK", "NOT_EXERCISED")
    announce("STAGE4_PRODUCTION_RELEASE_GATE", "BLOCKED_PENDING_LIVE_AUTH_PARITY_AND_APPROVAL")
    announce("AWS_DEPLOYMENT", "NOT_PERFORMED")
    announce("FINANCIAL_WRITES", "NOT_PERFORMED")
    announce("PRODUCTION_CUTOVER", "BLOCKED")
    if not (safe_canary and cleanup_pass and existing_unchanged):
        announce("PHASE1_COMBINED_GATE", "REVIEW_REQUIRED_CANARY_OR_BASELINE_FAILED")
        raise RuntimeError("ISOLATION_SAFETY_GATE_FAILED")
    announce("PHASE1_COMBINED_GATE", "COMPLETE_WITH_EXTERNAL_GATES")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        # Never echo Docker stderr as it may contain private path values.
        announce("PHASE1_COMBINED_GATE", "REVIEW_REQUIRED_" + type(error).__name__)
        if isinstance(error, RuntimeError):
            announce("BLOCKER", str(error))
        announce("AWS_DEPLOYMENT", "NOT_PERFORMED")
        announce("FINANCIAL_WRITES", "NOT_PERFORMED_BY_TEST")
        announce("PRODUCTION_CUTOVER", "BLOCKED")
        sys.exit(2)
