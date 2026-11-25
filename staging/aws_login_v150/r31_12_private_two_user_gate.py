#!/usr/bin/env python3
"""R31.12 host-only identity gate. No secrets in shell history or logs.

Requires two existing approved Firebase test users. Reuses R31.7 pinned private
isolation and R31.11 second-account lookup; no Firebase, Caddy or financial writes.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from r31_real_firebase_qa_acceptance import preflight, docker, firebase_api_key, STAGE
from r31_11_second_firebase_preflight import check_second_firebase
from r31_9_combined_gate import signin

ROOT = Path(__file__).resolve().parent
INNER = ROOT / "r31_12_private_two_user_incontainer.py"
REQUIRED = frozenset({
    "DB_R31_12_VERIFIED_TOKENS=PASS_DISTINCT_MASTER_AND_SECOND",
    "DB_R31_12_PRIVATE_APP_SESSIONS=PASS_BOTH_INDEPENDENT",
    "DB_R31_12_FINANCIAL_WRITES=NONE_BY_TEST",
})
ALLOWED = re.compile(r"^DB_R31_12_[A-Z0-9_]{1,60}=[A-Z0-9_]{1,100}$")


def run_inner(tokens: list[str]) -> bool:
    if not INNER.is_file() or INNER.is_symlink():
        print("STOP=DB_R31_12_VERIFIED_SOURCE_MISSING", flush=True)
        return False
    payload = json.dumps({"id_tokens": tokens})
    result = subprocess.run(
        ["sudo", "-n", "docker", "exec", "-i", "-w", "/app", STAGE,
         "python3", "-u", "-c", INNER.read_text("utf-8")],
        input=payload, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=150, check=False
    )
    payload = None
    lines = [
        line for line in result.stdout.splitlines()
        if len(line) <= 180 and ALLOWED.fullmatch(line)
    ]
    for line in lines:
        print(line, flush=True)
    if result.returncode != 0 or not REQUIRED.issubset(set(lines)):
        print("STOP=DB_R31_12_PRIVATE_IDENTITY_GATE_INCOMPLETE", flush=True)
        return False
    return True


def main() -> int:
    print("=== DB-R31.12 PRIVATE TWO-USER FIREBASE QA ===", flush=True)
    if not sys.stdin.isatty():
        print("STOP=DB_R31_12_INTERACTIVE_TERMINAL_REQUIRED", flush=True)
        return 2
    if not INNER.is_file() or INNER.is_symlink():
        print("STOP=DB_R31_12_VERIFIED_SOURCE_MISSING", flush=True)
        return 2
    preflight()
    caddy = docker("exec", "aws_lightsail-caddy-1",
                   "cat", "/etc/caddy/Caddyfile")
    if any(name in caddy for name in
           ("sbi-r31-auth-private-qa", "sbi-r31-auth-qa")):
        print("STOP=DB_R31_12_UNAPPROVED_PUBLIC_QA_ROUTE", flush=True)
        return 2
    print("DB_R31_12_PRIVATE_QA_ROUTE=NOT_PUBLIC", flush=True)
    if not check_second_firebase():
        print("DB_R31_12_SECOND_ACCOUNT=BLOCKED_NOT_DISTINCT_AND_APPROVED",
              flush=True)
        print("DB_R31_12_RELEASE_STATUS=PRODUCTION_BLOCKED", flush=True)
        return 2
    print("DB_R31_12_SECOND_ACCOUNT=PASS_READONLY_ADMIN_PREFLIGHT", flush=True)
    tokens = []
    try:
        key = firebase_api_key()
        print("Enter approved MASTER Firebase test account credentials privately.",
              flush=True)
        try:
            tokens.append(signin(key))
        except SystemExit:
            print("STOP=DB_R31_12_MASTER_LOGIN_FAILED", flush=True)
            return 2
        print("Enter distinct SECOND approved Firebase test account credentials privately.",
              flush=True)
        try:
            tokens.append(signin(key))
        except SystemExit:
            print("STOP=DB_R31_12_SECOND_LOGIN_FAILED", flush=True)
            return 2
        success = run_inner(tokens)
    finally:
        tokens.clear()
    print("DB_R31_12_IDENTITY_QA=" +
          ("PASS_DISTINCT_PRIVATE_SESSIONS" if success else "BLOCKED_RUNTIME"),
          flush=True)
    print("DB_R31_12_RELEASE_STATUS=IDENTITY_QA_ONLY_PRODUCTION_BLOCKED", flush=True)
    return 2  # Deliberately never approves production.


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        print("STOP=DB_R31_12_PRIVATE_RUNTIME_UNAVAILABLE", flush=True)
        raise SystemExit(2)
