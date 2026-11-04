#!/usr/bin/env python3
"""Stage 6C-4: explicit, read-only Firebase Admin connectivity probe on AWS.

Never prints tokens, UID, credential paths, e-mail or exception details.
No Firebase mutations, financial database access, HTTP listener or Docker changes.
Do not use a service-account private-key JSON. AWS WIF external_account only.
"""
import argparse
import json
import os
from pathlib import Path

PROJECT = "meghraj-reconciliation"

def preflight(env=None):
    env = os.environ if env is None else env
    if env.get("SBI_STAGE6_AUTH_PROFILE") != "aws-private-staging":
        return "BLOCKED_AUTH_PROFILE"
    path = env.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path or not Path(path).is_file():
        return "BLOCKED_WIF_CONFIG_MISSING"
    try:
        conf = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return "BLOCKED_WIF_CONFIG_INVALID"
    if not isinstance(conf, dict) or conf.get("type") != "external_account":
        return "BLOCKED_WIF_REQUIRED_NO_PRIVATE_KEYS"
    if "private_key" in conf or "client_email" in conf:
        return "BLOCKED_WIF_REQUIRED_NO_PRIVATE_KEYS"
    if not str(conf.get("audience", "")).startswith("//iam.googleapis.com/projects/"):
        return "BLOCKED_WIF_CONFIG_INVALID"
    if not isinstance(conf.get("credential_source"), dict):
        return "BLOCKED_WIF_CONFIG_INVALID"
    if env.get("SBI_STAGE6_TEST_FIREBASE_UID", "") == "":
        return "BLOCKED_TEST_UID_MISSING"
    return "READY_FOR_LIVE_FIREBASE_AUTH_READ_ONLY"

def verify_live():
    import firebase_admin
    from firebase_admin import auth
    from firebase_admin import credentials
    from google.auth import default
    # Google client obtains short-lived credentials via AWS WIF, not a key.
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    app = firebase_admin.initialize_app(
        credential=credentials.ApplicationDefault(),
        options={"projectId": PROJECT},
        name="stage6c4-read-only",
    )
    try:
        # The selected user is queried read-only; do not create/update accounts.
        user = auth.get_user(os.environ["SBI_STAGE6_TEST_FIREBASE_UID"], app=app)
        if user.disabled or (user.custom_claims or {}).get("dil_dashboard") is not True:
            return "FIREBASE_AUTH_READ=PASS_ACCOUNT_NOT_ELIGIBLE"
        return "FIREBASE_AUTH_READ=PASS_ACCOUNT_ELIGIBLE"
    finally:
        firebase_admin.delete_app(app)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Perform one authorized Firebase Admin get_user read")
    args=parser.parse_args()
    status=preflight()
    print("STAGE6C4_PREFLIGHT="+status)
    if status != "READY_FOR_LIVE_FIREBASE_AUTH_READ_ONLY":
        print("STAGE6C4_LIVE=NOT_PERFORMED")
        return 2
    if not args.live:
        print("STAGE6C4_LIVE=NOT_PERFORMED")
        return 0
    try:
        result=verify_live()
    except Exception:
        # Never print credential metadata, API error bodies, UID or tokens.
        print("STAGE6C4_LIVE=BLOCKED_AUTH_OR_NETWORK")
        return 3
    print(result)
    print("STAGE6C4_BROWSER_LOGIN=NOT_TESTED")
    print("FINANCIAL_DATA=NOT_ACCESSED")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
