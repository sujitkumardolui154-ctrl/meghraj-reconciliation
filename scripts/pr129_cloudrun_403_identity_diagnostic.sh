#!/usr/bin/env bash
# PR129 403 diagnostic. Read-only Cloud Run /health request only.
# Never outputs bearer tokens, private keys or credential JSON.
# Does NOT change IAM, Cloud Run, Caddy, container config or financial records.
set -Eeuo pipefail

C=sbi-bulk-report-pr129-https-preview
echo '=== PR129 GOOGLE CLOUD RUN 403 DIAGNOSIS ==='
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true || {
  echo 'PREVIEW_CONTAINER=NOT_RUNNING'; exit 1;
}

sudo docker exec -i "$C" python -B - <<'PY'
import base64
import datetime
import json
from urllib.parse import urlparse
import requests
from cloud_auth import get_backend_token

backend = "https://sbi-supervisor-backend-109590290120.asia-south1.run.app"
url = urlparse(backend)
assert url.scheme == "https" and url.hostname.endswith(".run.app")
print("TARGET_SERVICE=sbi-supervisor-backend")
print("PROBE_PATH=/health")
print("FINANCIAL_RECORDS_REQUESTED=NONE")

try:
    token = get_backend_token(backend)
    print("SERVICE_ID_TOKEN=OBTAINED")
except Exception as exc:
    print("SERVICE_ID_TOKEN=FAILED")
    print("TOKEN_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(2)

# Unverified JWT payload: used ONLY to diagnose token routing, NEVER to
# authorize access. Cloud Run independently validates the signed token.
try:
    piece = token.split(".")[1]
    piece += "=" * (-len(piece) % 4)
    claims = json.loads(base64.urlsafe_b64decode(piece).decode("utf-8"))
    print("TOKEN_AUDIENCE_MATCH=" + str(claims.get("aud") == backend).upper())
    print("TOKEN_GOOGLE_ISSUER=" + str(claims.get("iss") in (
        "https://accounts.google.com", "accounts.google.com"
    )).upper())
    print("TOKEN_EXPIRY_FUTURE=" + str(
        int(claims.get("exp", 0)) > int(datetime.datetime.now(
            datetime.timezone.utc).timestamp())
    ).upper())
    # Email is not a credential. It identifies precisely which service account
    # is being evaluated by Google IAM, if included in this ID token.
    email = claims.get("email", "")
    print("CALLER_SERVICE_ACCOUNT=" +
          (email if isinstance(email, str) and
           email.endswith(".gserviceaccount.com") else "NOT_EXPOSED_IN_TOKEN"))
except (IndexError, UnicodeError, ValueError, TypeError) as exc:
    print("JWT_CLAIM_INSPECTION=UNAVAILABLE")
    print("JWT_INSPECTION_ERROR_TYPE=" + type(exc).__name__)

try:
    r = requests.get(
        backend + "/health",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json"},
        allow_redirects=False,
        timeout=(5, 15),
    )
    print("HEALTH_HTTP=" + str(r.status_code))
    media = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
    print("RESPONSE_CONTENT_TYPE=" + (media or "UNKNOWN"))
    if r.status_code == 403:
        print("NEXT_GATE=VERIFY_SERVICE_ACCOUNT_RUN_INVOKER_AND_AUDIENCE")
    elif r.status_code == 200:
        print("NEXT_GATE=INSPECT_PRIVATE_LOOKUP_ROUTE_SEPARATELY")
    else:
        print("NEXT_GATE=REVIEW_BACKEND_STATUS_AND_INGRESS")
except requests.RequestException as exc:
    print("HEALTH_REQUEST=NETWORK_ERROR")
    print("REQUEST_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(3)

print("JWT_CLAIMS_USED_FOR_AUTHORIZATION=NO")
print("PRIVATE_KEY_OR_BEARER_TOKEN_OUTPUT=NO")
print("IAM_CHANGES=NONE")
print("DATABASE_ROWS_READ=NONE")
print("PUBLIC_APPLICATION=UNCHANGED")
print("FINANCIAL_WRITES=NONE")
print("PR129_403_DIAGNOSTIC=COMPLETE")
PY
