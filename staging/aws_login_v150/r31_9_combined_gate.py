#!/usr/bin/env python3
"""R31.9 fail-closed combined security gate (no deployment).

1) QA PostgreSQL RLS read-only catalog and privilege audit.
2) Two genuine distinct Firebase TEST sessions, if accounts exist.
3) External HTTPS E2E readiness: blocked without approved QA route.
No migrations, Caddy edits, account creation or production financial writes.
"""
from __future__ import annotations

import getpass
import json
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import os

from r31_real_firebase_qa_acceptance import (
    STAGE, preflight, docker, firebase_api_key, safe_firebase_signin_error
)

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "r31_9_combined_incontainer.py"
ALLOWED = frozenset({
    "DB_R31_9_RLS_AUDIT",
    "DB_R31_9_RLS_CATALOG",
    "DB_R31_9_RLS_EFFECTIVE_TENANT_GUARD",
    "DB_R31_9_REPORT_PRIVILEGES",
    "DB_R31_9_TWO_REAL_FIREBASE_USERS",
    "DB_R31_9_REAL_CROSS_ACCOUNT_RECEIPTS",
    "DB_R31_9_SYNTHETIC_RECEIPT_CLEANUP",
    "DB_R31_9_CROSS_ACCOUNT",
    "DB_R31_9_PG_FINANCIAL_WRITES",
    "DB_R31_9_AUTH_PAYLOAD",
})


def safe_line(line):
    if len(line) > 180 or any(ord(ch) < 32 for ch in line):
        return False
    if line == "=== DB-R31.9 ISOLATED COMBINED SECURITY GATE ===":
        return True
    if "=" not in line:
        return False
    key, value = line.split("=", 1)
    return key in ALLOWED and re.fullmatch(r"[A-Z0-9_]{1,100}", value) is not None


def signin(api_key):
    # Hide email as well as password; never print or pass in shell/env.
    email = getpass.getpass("Existing Firebase TEST user email (hidden): ").strip()
    password = getpass.getpass("Existing Firebase TEST user password (hidden): ")
    if not (3 <= len(email) <= 254 and 1 <= len(password) <= 1024):
        print("STOP=DB_R31_9_INVALID_TEST_CREDENTIAL_INPUT", flush=True)
        raise SystemExit(2)
    uri = ("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
           + urllib.parse.quote(api_key, safe=""))
    req = urllib.request.Request(
        uri,
        data=json.dumps({"email": email, "password": password,
                         "returnSecureToken": True}).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"}
    )
    email = password = None
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            doc = json.loads(res.read(25000))
    except urllib.error.HTTPError as exc:
        print("STOP=DB_R31_9_FIREBASE_" + safe_firebase_signin_error(exc),
              flush=True)
        raise SystemExit(2)
    except (OSError, ValueError, TimeoutError):
        print("STOP=DB_R31_9_FIREBASE_LOGIN_NETWORK_ERROR", flush=True)
        raise SystemExit(2)
    token = doc.get("idToken") if isinstance(doc, dict) else None
    if not isinstance(token, str) or not (200 <= len(token) <= 12000):
        print("STOP=DB_R31_9_FIREBASE_TEST_TOKEN_UNAVAILABLE", flush=True)
        raise SystemExit(2)
    return token


def run_inner(tokens):
    # Both tokens pass only through Docker process stdin. Raw process
    # stdout/stderr, credentials and tracebacks never reach the terminal.
    proc = subprocess.Popen(
        ["sudo", "-n", "docker", "exec", "-i", "-w", "/app", STAGE,
         "python3", "-u", "-c", SOURCE.read_text(encoding="utf-8")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, bufsize=0
    )
    lines = []
    partial = b""
    try:
        proc.stdin.write(json.dumps({"id_tokens": tokens}).encode("utf-8"))
        proc.stdin.close()
        deadline = time.monotonic() + 150
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print("STOP=DB_R31_9_CONTAINER_TIMEOUT", flush=True)
                    return 1, lines
                events = sel.select(min(remaining, 10))
                if not events:
                    print("DB_R31_9_RUNNING=WAITING_FOR_PRIVATE_CHECK", flush=True)
                    continue
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                partial += chunk
                if len(partial) > 65536:
                    print("STOP=DB_R31_9_OUTPUT_TOO_LONG", flush=True)
                    return 1, lines
                while b"\n" in partial:
                    raw, partial = partial.split(b"\n", 1)
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                    if safe_line(line):
                        print(line, flush=True)
                        lines.append(line)
        if partial:
            line = partial.decode("utf-8", errors="replace").rstrip("\r")
            if safe_line(line):
                print(line, flush=True)
                lines.append(line)
        try:
            return proc.wait(timeout=5), lines
        except subprocess.TimeoutExpired:
            return 1, lines
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if proc.stdout:
            proc.stdout.close()
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()


def main():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        print("STOP=DB_R31_9_SOURCE_NOT_VERIFIED", flush=True)
        return 2
    print("=== DB-R31.9 COMBINED 1-3 PRIVATE SECURITY QA ===", flush=True)
    preflight()
    caddy = docker("exec", "aws_lightsail-caddy-1", "cat", "/etc/caddy/Caddyfile")
    qa_routed = any(
        name in caddy for name in ("sbi-r31-auth-private-qa", "sbi-r31-auth-qa")
    )
    if qa_routed:
        print("DB_R31_9_EXTERNAL_ROUTE_GUARD=UNEXPECTED_QA_ROUTE_DETECTED",
              flush=True)
        print("DB_R31_9_HTTPS_E2E=BLOCKED_UNAPPROVED_ROUTE", flush=True)
    else:
        print("DB_R31_9_EXTERNAL_ROUTE_GUARD=PASS_NO_PUBLIC_QA_ROUTE",
              flush=True)
        print("DB_R31_9_HTTPS_E2E=NOT_TESTED_NO_APPROVED_ROUTE", flush=True)
    print("DB_R31_9_RLS_AND_TWO_OWNER_TEST=START", flush=True)
    tokens = []
    try:
        response = (
            input("Two distinct existing Firebase TEST users available? [y/N]: ")
            .strip().lower() if sys.stdin.isatty() else "n"
        )
        if response == "y":
            key = firebase_api_key()
            print("Account 1: authorized existing test user", flush=True)
            tokens.append(signin(key))
            print("Account 2: different authorized existing test user", flush=True)
            tokens.append(signin(key))
        status, lines = run_inner(tokens)
    finally:
        tokens.clear()
    if status != 0:
        print("STOP=DB_R31_9_COMBINED_CONTAINER_CHECK_FAILED", flush=True)
        return 2
    # Catalog flag alone is not a database-enforced tenant security proof.
    # An approved TLS route is also required, so this audit cannot be promoted.
    needed = (
        "DB_R31_9_REPORT_PRIVILEGES=PASS_READONLY_ROLE",
        "DB_R31_9_RLS_CATALOG=ENABLED_CATALOG_ONLY",
        "DB_R31_9_RLS_EFFECTIVE_TENANT_GUARD=PASS",
        "DB_R31_9_TWO_REAL_FIREBASE_USERS=PASS_DISTINCT_AUTHENTICATED_UIDS",
        "DB_R31_9_REAL_CROSS_ACCOUNT_RECEIPTS=PASS_BIDIRECTIONAL_404_AND_FILTERING",
        "DB_R31_9_SYNTHETIC_RECEIPT_CLEANUP=PASS",
    )
    if qa_routed or any(item not in lines for item in needed):
        print("DB_R31_9_RELEASE_STATUS=COMBINED_QA_INCOMPLETE_PRODUCTION_BLOCKED",
              flush=True)
        return 2
    print("DB_R31_9_RELEASE_STATUS=COMBINED_QA_INCOMPLETE_HTTPS_NOT_TESTED",
          flush=True)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        print("STOP=DB_R31_9_HOST_OR_DOCKER_UNAVAILABLE", flush=True)
        raise SystemExit(2)
