#!/usr/bin/env bash
# PR129: private Cloud Run connectivity / identity / route preflight only.
# NO invoice IDs, Firestore reads, reconciliation, uploads or financial writes.
set -Eeuo pipefail

C=sbi-bulk-report-pr129-https-preview
DEFAULT_BACKEND=https://sbi-supervisor-backend-109590290120.asia-south1.run.app

echo '=== PR129 VERIFIED INVOICE LOOKUP BACKEND PROBE ==='
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true || {
  echo 'PREVIEW_CONTAINER=NOT_RUNNING'; exit 1;
}

sudo docker exec -i "$C" python -B - <<'PY'
import os
from urllib.parse import urlparse
import requests
from cloud_auth import get_backend_token

expected = "https://sbi-supervisor-backend-109590290120.asia-south1.run.app"
backend = expected  # Current trusted backend in production_gateway.py.
url = urlparse(backend)
assert (url.scheme == "https" and url.hostname.endswith(".run.app")
        and url.username is None and url.password is None
        and not url.query and not url.fragment)
print("BACKEND_TARGET=KNOWN_GOOGLE_CLOUD_RUN_SERVICE")
print("INVOICE_LOOKUP_BACKEND_CONFIGURED="
      + ("YES" if os.environ.get("INVOICE_LOOKUP_BACKEND") else "NO"))
print("REQUEST_CONTAINS_INVOICE_NUMBERS=NO")
print("FINANCIAL_RECORDS_READ_BY_PROBE=NONE")

try:
    # Token is passed in the HTTPS authorization header, never printed.
    token = get_backend_token(backend)
    print("PRIVATE_SERVICE_ID_TOKEN=OBTAINED")
except Exception as exc:
    print("PRIVATE_SERVICE_ID_TOKEN=UNAVAILABLE")
    print("TOKEN_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(2)

headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
try:
    health = requests.get(backend + "/health", headers=headers,
                          timeout=(5, 15), allow_redirects=False)
    print("BACKEND_HEALTH_HTTP=" + str(health.status_code))
    if health.status_code == 200 and (
        "application/json" in health.headers.get("Content-Type", "")
    ):
        health_info = health.json()
        print("BACKEND_SERVICE_IDENTITY="
              + ("EXPECTED" if health_info.get("service") == "sbi-supervisor-backend"
                 else "UNEXPECTED"))
        print("BACKEND_FINANCIAL_EXECUTION_DISABLED="
              + str(health_info.get("financial_execution_enabled") is False).upper())
    if health.status_code != 200:
        print("BACKEND_HEALTH_GATE=BLOCKED")
        raise SystemExit(3)

    # Safe invalid request: the handler must reject it BEFORE any DB read.
    # Existing backend without new route ordinarily responds 405; an updated,
    # identity-authorized handler responds 422; 403 means identity/allowlist gate.
    probe = requests.post(backend + "/reports/invoice-selection",
                          headers=headers, json={"invoice_numbers": []},
                          timeout=(5, 15), allow_redirects=False)
    print("LOOKUP_ROUTE_INVALID_INPUT_HTTP=" + str(probe.status_code))
    if probe.status_code == 422:
        print("LOOKUP_ROUTE_VALIDATION=AVAILABLE")
    elif probe.status_code == 403:
        print("LOOKUP_ROUTE_VALIDATION=BLOCKED_AUTH_OR_ALLOWLIST")
    elif probe.status_code in (404, 405):
        print("LOOKUP_ROUTE_VALIDATION=NOT_DEPLOYED_OR_NOT_ROUTED")
    else:
        print("LOOKUP_ROUTE_VALIDATION=NEEDS_REVIEW")
except requests.RequestException as exc:
    print("PRIVATE_BACKEND_NETWORK=ERROR")
    print("NETWORK_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(4)
PY

echo 'PRIVATE_BACKEND_ROUTE_PROBE=COMPLETE'
echo 'INVOICE_DATABASE_LOOKUP=NOT_PERFORMED'
echo 'PUBLIC_APPLICATION=UNCHANGED'
echo 'FINANCIAL_WRITES=NONE'
