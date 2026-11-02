#!/usr/bin/env bash
# SBI AWS preview consolidated release gate. No financial backend or database access.
set -Eeuo pipefail
ROOT="${ROOT:-$HOME/sbi-aws-app}"
cd "$ROOT/staging/aws_lightsail"
DOMAIN="${SITE_DOMAIN_OVERRIDE:-sbi-preview.13-232-241-221.sslip.io}"
URL="https://${DOMAIN}"
IMAGE="aws_lightsail-sbi-preview"
REPORT="$ROOT/staging/aws_dashboard_v1/preview_release_gate.txt"
mkdir -p "$(dirname "$REPORT")"
pass=0; fail=0
record() { printf '%s=%s\n' "$1" "$2" | tee -a "$REPORT"; if [ "$2" = PASS ]; then pass=$((pass+1)); else fail=$((fail+1)); fi; }
: > "$REPORT"
test -f .env && record CONFIG_FILE PASS || record CONFIG_FILE FAIL
test -f "$ROOT/staging/railway_public/app.py" && record PREVIEW_SOURCE PASS || record PREVIEW_SOURCE FAIL
for x in index.html dashboard.js account.js; do
  test -s "$ROOT/staging/railway_public/dashboard_assets/$x" && record "ASSET_${x//./_}" PASS || record "ASSET_${x//./_}" FAIL
done
python3 -m py_compile "$ROOT/staging/railway_public/app.py" && record PYTHON_SYNTAX PASS || record PYTHON_SYNTAX FAIL
sudo docker compose config --quiet && record COMPOSE_CONFIG PASS || record COMPOSE_CONFIG FAIL
if [ "$fail" -gt 0 ]; then echo "RELEASE=BLOCKED_PRECHECK"; exit 1; fi
# Building does not replace the live container.
sudo docker compose build sbi-preview
# The source supports either the original long test-password rule or the preview-only 8-10 rule.
if grep -q '8 <= len(password) <= 10' "$ROOT/staging/railway_public/app.py"; then TEST_PASS="TestP@1234"; else TEST_PASS="a-very-long-test-only-password"; fi
if sudo docker run --rm --network none --env "PREVIEW_USERNAME=qa_test" --env "PREVIEW_PASSWORD=$TEST_PASS" "$IMAGE" python -c '
import base64
from app import app
from pathlib import Path
from flask import json
import os,sys
c=app.test_client()
u=os.environ["PREVIEW_USERNAME"]
p=os.environ["PREVIEW_PASSWORD"]
h={"Authorization":"Basic "+base64.b64encode((u+":"+p).encode()).decode()}
tests={
"anonymous_login":c.get("/").status_code==401,
"authenticated_dashboard":c.get("/",headers=h).status_code==200,
"dashboard_js":c.get("/dashboard.js",headers=h).status_code==200,
"account_js":c.get("/account.js",headers=h).status_code==200,
"health":c.get("/healthz").status_code==200 and c.get("/healthz").json.get("financial_data_connected") is False,
"upload_denied":c.post("/api/upload",headers=h).status_code==403,
"import_denied":c.post("/api/imports/apply",headers=h).status_code==403,
"reports_denied":c.get("/api/reports",headers=h).status_code==403,
}
for k,v in tests.items(): print("TEST_"+k.upper()+"="+("PASS" if v else "FAIL"))
sys.exit(0 if all(tests.values()) else 1)
'; then record CONTAINER_INTEGRATION_TESTS PASS; else record CONTAINER_INTEGRATION_TESTS FAIL; fi
if [ "$fail" -gt 0 ]; then echo "RELEASE=BLOCKED_TESTS"; exit 1; fi
if [ "${DEPLOY:-0}" = 1 ]; then
  previous="$(sudo docker inspect aws_lightsail-sbi-preview-1 --format '{{.Image}}' 2>/dev/null || true)"
  if [ -n "$previous" ]; then sudo docker image tag "$previous" sbi-preview:pre-consolidated-rollback; fi
  sudo docker compose up -d --no-deps --force-recreate sbi-preview
  echo "DEPLOY_ACTION=EXECUTED" | tee -a "$REPORT"
else
  echo "DEPLOY_ACTION=SKIPPED_SET_DEPLOY_1" | tee -a "$REPORT"
fi
# HTTPS smoke, never send passwords or auth tokens over external network.
home="$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' "$URL/" || true)"
health="$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' "$URL/healthz" || true)"
[ "$home" = 401 ] && record HTTPS_LOGIN_REQUIRED PASS || record HTTPS_LOGIN_REQUIRED FAIL
[ "$health" = 200 ] && record HTTPS_HEALTH PASS || record HTTPS_HEALTH FAIL
if [ "$fail" -gt 0 ] && [ "${DEPLOY:-0}" = 1 ] && [ -n "${previous:-}" ]; then
  echo "ROLLBACK_REQUIRED=YES" | tee -a "$REPORT"
  sudo docker image tag sbi-preview:pre-consolidated-rollback "$IMAGE"
  sudo docker compose up -d --no-deps --force-recreate sbi-preview
  echo "ROLLBACK_ATTEMPTED=YES" | tee -a "$REPORT"
fi
echo "CHECKS_PASSED=$pass CHECKS_FAILED=$fail"
echo "FINANCIAL_BACKEND=NOT_CONNECTED"
echo "FINANCIAL_RELEASE=BLOCKED"
echo "REPORT=$REPORT"
[ "$fail" -eq 0 ]
