#!/usr/bin/env python3
"""Stage 6D private-only entrypoint with strict launch-time checks.

Intended for a future single disposable container using Docker
-p 127.0.0.1:18085:8080. No reverse proxy route; no production cutover.
Does not configure Firebase credentials, WIF or backend connections.
"""
import os
import sys
from stage6_origin_policy import private_aws_origin

def startup_gate(env=None):
    env = os.environ if env is None else env
    if env.get("SBI_STAGE6_AUTH_PROFILE") != "aws-private-staging":
        return "BLOCKED_PROFILE"
    if private_aws_origin(env) is None:
        return "BLOCKED_ORIGIN"
    if env.get("SBI_STAGE6_PRIVATE_ONLY") != "1":
        return "BLOCKED_PRIVATE_ONLY"
    if env.get("SBI_STAGE6_FINANCIAL_EXECUTION", "disabled").lower() != "disabled":
        return "BLOCKED_FINANCIAL_EXECUTION"
    if env.get("SBI_STAGE6_BACKEND_CONNECTED", "false").lower() != "false":
        return "BLOCKED_BACKEND_CONNECTED"
    # No WIF config or Firebase Admin credentials assumed here.
    # The existing production_gateway retains all Firebase Admin security checks;
    # with no usable Google credentials those operations fail closed.
    return "READY_PRIVATE_AUTH_SHELL_ONLY"

def main():
    result = startup_gate()
    print("STAGE6D_PRIVATE_GATE="+result, flush=True)
    if result != "READY_PRIVATE_AUTH_SHELL_ONLY":
        return 78
    if "--check" in sys.argv:
        print("FIREBASE_ADMIN_LIVE=NOT_VERIFIED", flush=True)
        print("FINANCIAL_API=BLOCKED", flush=True)
        return 0
    # Separate from any existing live service; no public host binding here.
    # Container must additionally be published only to 127.0.0.1 on host.
    os.execvp("gunicorn", [
        "gunicorn", "--bind", "0.0.0.0:8080",
        "--workers", "1", "--threads", "2",
        "--timeout", "30", "production_gateway:app"
    ])

if __name__=="__main__":
    raise SystemExit(main())
