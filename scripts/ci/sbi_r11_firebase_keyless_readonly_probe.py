"""R11: one read-only Firebase Auth API check using keyless impersonation.

This is deliberately NEVER called in GitHub CI. It reads a single page
(maxResults=1) from the already-created sbi-r9-staging Firebase project.
It does not create users, sessions, access tokens on disk, or financial writes.
Do not print HTTP response bodies, bearer tokens, user IDs or emails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT = "sbi-r9-staging"
SERVICE = "sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com"
GATE = "SBI_R11_READ_ONLY_STAGING_FIREBASE_APPROVED"
ENDPOINT = (
    "https://identitytoolkit.googleapis.com/v1/projects/"
    "sbi-r9-staging/accounts:batchGet?maxResults=1"
)


def refuse(reason: str):
    raise RuntimeError("R11_PREFLIGHT_REFUSED: " + reason)


def check_environment(env=None):
    v = os.environ if env is None else env
    if v.get("SBI_R11_READONLY_FIREBASE") != GATE:
        refuse("R11 explicit read-only intent missing")
    if v.get("FIREBASE_AUTH_EMULATOR_HOST"):
        refuse("Auth Emulator forbidden for real Firebase API verification")
    if v.get("GOOGLE_APPLICATION_CREDENTIALS"):
        refuse("private credential file environment forbidden")
    for name in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        if v.get(name) and v[name] != PROJECT:
            refuse("inherited Google project is not exact staging project")
    if v.get("SBI_PAYMENT_EVIDENCE_DIR") or v.get("SBI_PRIVATE_WORKSPACE_DB"):
        refuse("financial evidence/database variables must be absent")
    if v.get("SBI_R9_REAL_STAGING_PROBE"):
        refuse("R9 user-creating probe must not be enabled")
    return PROJECT, SERVICE


def command(args):
    result = subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=25
    )
    return result.stdout.strip()


def verify_read_only_api():
    project, target = check_environment()
    # Fail before any bearer token is generated if Cloud Shell points elsewhere.
    selected_project = command(["gcloud", "config", "get-value", "project"])
    if selected_project != project:
        refuse("gcloud active project differs from isolated Firebase staging")
    # gcloud creates an in-memory short-lived token; no file, logs, stdout.
    bearer = command([
        "gcloud", "auth", "print-access-token",
        "--impersonate-service-account=" + target,
    ])
    if len(bearer) < 25 or any(c.isspace() for c in bearer):
        refuse("invalid short-lived impersonated credential")
    request = Request(ENDPOINT, headers={
        "Authorization": "Bearer " + bearer,
        "Accept": "application/json",
    }, method="GET")
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("R11_FIREBASE_READONLY_FAILED: unexpected HTTP status")
        data = json.load(response)
        if not isinstance(data, dict):
            raise RuntimeError("R11_FIREBASE_READONLY_FAILED: invalid API response")
    # NEVER print the account records or the temporary bearer token.
    print("R11_REAL_FIREBASE_AUTH_API=PASS_READONLY")
    print("R11_PROJECT=sbi-r9-staging")
    print("R11_QA_PRINCIPAL=KEYLESS_IMPERSONATED")
    print("R11_SIGNED_ID_SESSION_TOKEN=NOT_TESTED")
    print("R11_FIREBASE_USER_MUTATIONS=NONE")
    print("R11_AWS=UNCHANGED")
    print("R11_FINANCIAL_APPLY=LOCKED")


def main():
    try:
        verify_read_only_api()
    except HTTPError as exc:
        # Only status code; HTTP response body can expose sensitive data.
        print(f"R11_FIREBASE_READONLY_FAILED_HTTP={exc.code}", file=sys.stderr)
        sys.exit(1)
    except (URLError, subprocess.SubprocessError, OSError) as exc:
        # Never echo tokens, process args, HTTP URLs with key material or users.
        del exc
        print("R11_FIREBASE_READONLY_FAILED_TRANSPORT_OR_IAM", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        # Error messages here are authored in this file, without credentials.
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
