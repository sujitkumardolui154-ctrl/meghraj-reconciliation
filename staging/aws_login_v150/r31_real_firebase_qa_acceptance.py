#!/usr/bin/env python3
"""AWS host operator for DB-R31.7, with no passwords/tokens in chat/history.

Run on Lightsail terminal (TTY) after private DB-R31.6 stage PASS.
Authenticates an EXISTING dashboard-authorized Firebase *test account* using
Identity Toolkit HTTPS and streams only the short-lived ID token to a fresh
Python process INSIDE the existing private QA Docker container. No public
routing, credential files, Firebase user creation, engine apply or prod DB.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

STAGE = "sbi-r31-auth-private-qa"
PG = "sbi-synthetic-postgres-38-31"
QA_DB = "sbi_r31_owner_qa_20261125"
NETWORK = "sbi-synthetic-isolated-38-31"
STAGE_IMAGE = "sbi-r31-auth-qa:7a2298d93b6ace5977dc959acea3c7aa7c7ce4f0"
ROOT = Path(__file__).resolve().parent
IN_CONTAINER = ROOT / "r31_firebase_private_incontainer_smoke.py"


def blocked(code: str):
    print("STOP=DB_R31_" + code, flush=True)
    raise SystemExit(2)


def docker(*args: str, input_text=None, timeout=45):
    result = subprocess.run(
        ["sudo", "-n", "docker", *args], input=input_text,
        capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        # Suppress raw stdout/stderr: never accidentally disclose a token.
        blocked("PRIVATE_DOCKER_COMMAND_FAILED")
    return result.stdout.strip()


def preflight():
    if not IN_CONTAINER.is_file() or IN_CONTAINER.is_symlink():
        blocked("PINNED_AUTH_ACCEPTANCE_SOURCE_MISSING")
    stage = json.loads(docker("inspect", STAGE))[0]
    if (not stage.get("State", {}).get("Running")
        or stage.get("Config", {}).get("Image") != STAGE_IMAGE
        or stage.get("HostConfig", {}).get("PortBindings") not in (None, {})
        or NETWORK not in stage.get("NetworkSettings", {}).get("Networks", {})):
        blocked("PRIVATE_STAGE_IDENTITY_OR_NETWORK_CHANGED")
    psql_query = (
        "SELECT string_agg(datname,',' ORDER BY datname) "
        "FROM pg_database WHERE datname IN "
        "('sbi_reconciliation_main','" + QA_DB + "');"
    )
    dbs = docker("exec", PG, "psql", "-X", "-qAt",
                 "-U", "postgres", "-d", "postgres", "-c", psql_query)
    if dbs != QA_DB:
        blocked("ISOLATED_QA_DB_IDENTITY_NOT_CONFIRMED")
    flag = docker("exec", STAGE, "python3", "-c",
                  "import os;print(os.environ.get('SBI_R31_PRIVATE_STAGING_ENABLED',''))")
    if flag != "isolated-ownerqa-firebase-csrf-v1":
        blocked("PRIVATE_STAGING_FLAG_NOT_ENABLED")
    print("DB_R31_PRIVATE_ISOLATION_PREFLIGHT=PASS", flush=True)


def firebase_api_key():
    key = docker(
        "exec", STAGE, "python3", "-c",
        "import os;print(os.environ.get('FIREBASE_WEB_API_KEY',''))"
    )
    if not key or len(key) > 256:
        blocked("FIREBASE_WEB_API_KEY_NOT_READY")
    return key


# Firebase returns a generic HTTP 400 for multiple unrelated errors.
# Decode ONLY known, public error identifiers; never print response bodies,
# emails, passwords, API keys or any returned identity tokens.
SAFE_FIREBASE_SIGNIN_ERRORS = frozenset({
    "INVALID_LOGIN_CREDENTIALS",
    "EMAIL_NOT_FOUND",
    "INVALID_PASSWORD",
    "USER_DISABLED",
    "OPERATION_NOT_ALLOWED",
    "PASSWORD_LOGIN_DISABLED",
    "INVALID_API_KEY",
    "API_KEY_INVALID",
    "PROJECT_NOT_FOUND",
    "TOO_MANY_ATTEMPTS_TRY_LATER",
    "MISSING_PASSWORD",
    "MISSING_EMAIL",
})


def safe_firebase_signin_error(exc: urllib.error.HTTPError) -> str:
    """Return a short whitelisted error label without identity disclosure."""
    if exc.code != 400:
        return "REJECTED_HTTP_" + str(exc.code)
    try:
        raw = exc.read(4096)
        body = json.loads(raw)
        message = body.get("error", {}).get("message")
    except (ValueError, UnicodeError, AttributeError, TypeError, OSError):
        message = None
    if type(message) is str and message in SAFE_FIREBASE_SIGNIN_ERRORS:
        return message
    return "REJECTED_HTTP_400"


def obtain_firebase_test_id_token(key: str):
    if not sys.stdin.isatty():
        blocked("INTERACTIVE_TERMINAL_REQUIRED_FOR_PRIVATE_PASSWORD")
    print("Use an existing Firebase *test* user with the dil_dashboard claim.")
    print("Do NOT paste passwords or tokens into ChatGPT or GitHub.")
    email = input("Firebase test user email: ").strip()
    password = getpass.getpass("Firebase test user password (hidden): ")
    if not 3 <= len(email) <= 254 or not password:
        blocked("FIREBASE_TEST_IDENTITY_INPUT_INVALID")
    uri = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
        + urllib.parse.quote(key, safe="")
    )
    body = json.dumps({
        "email": email,
        "password": password,
        "returnSecureToken": True
    }).encode("utf-8")
    password = None
    request = urllib.request.Request(
        uri, data=body, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read(25000))
    except urllib.error.HTTPError as exc:
        blocked("FIREBASE_TEST_SIGNIN_" + safe_firebase_signin_error(exc))
    except (urllib.error.URLError, TimeoutError, ValueError):
        blocked("FIREBASE_TEST_SIGNIN_NETWORK_OR_RESPONSE_ERROR")
    token = payload.get("idToken") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not 200 <= len(token) <= 12000:
        blocked("FIREBASE_TEST_ID_TOKEN_MISSING")
    print("DB_R31_FIREBASE_TEST_PASSWORD_LOGIN=PASS", flush=True)
    return token


def main():
    preflight()
    key = firebase_api_key()
    token = obtain_firebase_test_id_token(key)
    # The Docker process command contains the trusted Python SOURCE only.
    # The ID token is passed through stdin, not command line, env, a file or
    # any user-visible stdout. It dies with the ephemeral process.
    source = IN_CONTAINER.read_text("utf-8")
    payload = json.dumps({"id_token": token})
    token = None
    result = subprocess.run(
        ["sudo", "-n", "docker", "exec", "-i", "-w", "/app",
         STAGE, "python3", "-c", source],
        input=payload, text=True, capture_output=True,
        timeout=120, check=False
    )
    # Print ONLY whitelisted QA receipts and static refusal codes.
    for line in result.stdout.splitlines():
        if (line.startswith("DB_R31_") or line.startswith("STOP=DB_R31_")):
            print(line, flush=True)
    if result.returncode:
        if not any(line.startswith("STOP=DB_R31_")
                   for line in result.stdout.splitlines()):
            print("STOP=DB_R31_PRIVATE_FIREBASE_QA_RUNTIME_FAILURE", flush=True)
        raise SystemExit(1)
    if "DB_R31_RELEASE_STATUS=PRIVATE_REAL_FIREBASE_QA_PASS_NOT_PUBLIC" \
       not in result.stdout:
        blocked("PRIVATE_QA_SUCCESS_RECEIPT_MISSING")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.TimeoutExpired):
        blocked("PRIVATE_ACCEPTANCE_RUNTIME_UNAVAILABLE")
