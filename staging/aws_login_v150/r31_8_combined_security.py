#!/usr/bin/env python3
"""DB-R31.8 ONE-COMMAND COMBINED private security QA on existing AWS stage.

Strictly uses the already deployed R31.6 private image and isolated DB.
No Docker build, Caddy editing, public port, Firebase account changes,
production DB, financial allocation or unapproved user data uploads.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
import selectors
import subprocess
import time

from r31_real_firebase_qa_acceptance import (
    STAGE, docker, preflight, firebase_api_key,
    obtain_firebase_test_id_token, blocked,
)

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/"r31_8_combined_security_incontainer.py"


# No Firebase token, password, complete email or user UID may be sent to
# stdout. Emit only exact-prefixed QA receipt lines while the isolated test
# executes. The inner script uses python3 -u; the old capture_output=True
# buffered ALL results for up to 120 s, falsely appearing to hang.
PASS_PREFIX="DB_R31_8_"
STOP_PREFIX="STOP=DB_R31_8_"


def accepted_qa_line(line: str) -> bool:
    if len(line)>512 or any(ord(ch)<32 and ch!="\\t" for ch in line):
        return False
    return (line.startswith(PASS_PREFIX)
            or line.startswith(STOP_PREFIX)
            or line in (
                "=== DB-R31.8 PRIVATE COMBINED SECURITY QA ===",
                "=== DB-R31.8 PRIVATE COMBINED QA COMPLETE ===",
            ))


def run_streamed_qa(source: str, token: str, *, timeout: int=180):
    """Bounded binary-pipe streaming so no raw stderr/tracebacks are exposed.

    Short-lived Firebase ID token passes ONLY by stdin of the existing,
    isolated Docker process. Never in environment, argv, shell, or logs.
    """
    proc=subprocess.Popen(
        ["sudo","-n","docker","exec","-i","-w","/app",
         STAGE,"python3","-u","-c",source],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,bufsize=0
    )
    lines=[]
    partial=b""
    deadline=time.monotonic()+timeout
    previous_heartbeat=time.monotonic()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps({"id_token":token}).encode("utf-8"))
        proc.stdin.close()
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout,selectors.EVENT_READ)
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    print("STOP=DB_R31_8_STREAMING_TIMEOUT",flush=True)
                    return 1,lines
                events=sel.select(timeout=min(10,remaining))
                if not events:
                    if time.monotonic()-previous_heartbeat>=10:
                        print("DB_R31_8_RUNNING_WAITING_FOR_CHECK=YES",flush=True)
                        previous_heartbeat=time.monotonic()
                    continue
                chunk=os.read(proc.stdout.fileno(),4096)
                if not chunk:
                    break
                partial+=chunk
                # A malicious or accidental binary/log output must never be
                # copied unboundedly into the host runner.
                if len(partial)>65536:
                    print("STOP=DB_R31_8_UNEXPECTED_OUTPUT_SIZE",flush=True)
                    return 1,lines
                while b"\n" in partial:
                    raw,partial=partial.split(b"\n",1)
                    line=raw.decode("utf-8",errors="replace").rstrip("\r")
                    if accepted_qa_line(line):
                        print(line,flush=True)
                        lines.append(line)
                        previous_heartbeat=time.monotonic()
        if partial:
            line=partial.decode("utf-8",errors="replace").rstrip("\r")
            if accepted_qa_line(line):
                print(line,flush=True)
                lines.append(line)
        try:
            return proc.wait(timeout=5),lines
        except subprocess.TimeoutExpired:
            print("STOP=DB_R31_8_PROCESS_EXIT_TIMEOUT",flush=True)
            return 1,lines
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()


def main():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        blocked("8_SECURITY_HARNESS_NOT_VERIFIED")
    print("DB_R31_8_PREFLIGHT=RUNNING",flush=True)
    # The already passed DB-R31.7 private stage/image/PG identity guard.
    preflight()
    print("DB_R31_8_CADDY_GUARD=RUNNING",flush=True)
    # Read existing Caddy configuration, never edit it or publish the stage.
    caddy=docker("exec","aws_lightsail-caddy-1","cat","/etc/caddy/Caddyfile")
    if "sbi-r31-auth-private-qa" in caddy or "sbi-r31-auth-qa" in caddy:
        blocked("8_CADDY_PRIVATE_QA_ROUTE_DETECTED")
    print("DB_R31_8_PUBLIC_CADDY_QA_ROUTE=ABSENT",flush=True)
    print("DB_R31_8_FIREBASE_TEST_LOGIN=READY_FOR_PRIVATE_INPUT",flush=True)
    token=obtain_firebase_test_id_token(firebase_api_key())
    if not token:
        blocked("8_FIREBASE_ID_TOKEN_NOT_AVAILABLE")
    print("DB_R31_8_AUTHENTICATION=PASS_EXECUTING_PRIVATE_CHECKS",flush=True)
    status,lines=run_streamed_qa(
        SOURCE.read_text(encoding="utf-8"),token,timeout=180)
    token=None
    if status!=0:
        if not any(s.startswith(STOP_PREFIX) for s in lines):
            print("STOP=DB_R31_8_PRIVATE_COMBINED_RUNTIME_ERROR",flush=True)
        raise SystemExit(1)
    if ("DB_R31_8_RELEASE_STATUS="
        "PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED"
        not in lines):
        blocked("8_COMBINED_COMPLETION_RECEIPT_MISSING")


if __name__=="__main__":
    try:
        main()
    except (OSError,subprocess.TimeoutExpired):
        blocked("8_PRIVATE_COMBINED_HOST_UNAVAILABLE")
