#!/usr/bin/env python3
"""DB-R31.8 ONE-COMMAND COMBINED private security QA on existing AWS stage.

Strictly uses the already deployed R31.6 private image and isolated DB.
No Docker build, Caddy editing, public port, Firebase account changes,
production DB, financial allocation or unapproved user data uploads.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from r31_real_firebase_qa_acceptance import (
    STAGE, docker, preflight, firebase_api_key,
    obtain_firebase_test_id_token, blocked,
)

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/"r31_8_combined_security_incontainer.py"


def main():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        blocked("8_SECURITY_HARNESS_NOT_VERIFIED")
    # The already passed DB-R31.7 private stage/image/PG identity guard.
    preflight()
    # Read existing Caddy configuration, never edit it or publish the stage.
    caddy=docker("exec","aws_lightsail-caddy-1","cat","/etc/caddy/Caddyfile")
    if "sbi-r31-auth-private-qa" in caddy or "sbi-r31-auth-qa" in caddy:
        blocked("8_CADDY_PRIVATE_QA_ROUTE_DETECTED")
    print("DB_R31_8_PUBLIC_CADDY_QA_ROUTE=ABSENT",flush=True)
    token=obtain_firebase_test_id_token(firebase_api_key())
    if not token:
        blocked("8_FIREBASE_ID_TOKEN_NOT_AVAILABLE")
    body=json.dumps({"id_token":token})
    token=None
    result=subprocess.run(
        ["sudo","-n","docker","exec","-i","-w","/app",
         STAGE,"python3","-c",SOURCE.read_text(encoding="utf-8")],
        input=body,capture_output=True,text=True,
        check=False,timeout=120
    )
    # Audit stdout is whitelisted so a traceback cannot leak an identity,
    # token or details of the synthetic private evidence.
    for line in result.stdout.splitlines():
        if (line.startswith("DB_R31_8_")
            or line.startswith("STOP=DB_R31_8_")
            or line.startswith("=== DB-R31.8")):
            print(line,flush=True)
    if result.returncode!=0:
        if not any(s.startswith("STOP=DB_R31_8_")
                   for s in result.stdout.splitlines()):
            print("STOP=DB_R31_8_PRIVATE_COMBINED_RUNTIME_ERROR",flush=True)
        raise SystemExit(1)
    if ("DB_R31_8_RELEASE_STATUS="
        "PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED"
        not in result.stdout):
        blocked("8_COMBINED_COMPLETION_RECEIPT_MISSING")


if __name__=="__main__":
    try:
        main()
    except (OSError,subprocess.TimeoutExpired):
        blocked("8_PRIVATE_COMBINED_HOST_UNAVAILABLE")
