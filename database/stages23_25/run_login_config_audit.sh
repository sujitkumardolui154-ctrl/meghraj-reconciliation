#!/usr/bin/env bash
# SBI PR129 login setup: combined read-only Firebase/session configuration audit.
# Never prints values, dumps env, changes DB, restarts containers or publishes ports.
set -Eeuo pipefail
umask 077
STEP=START
WORK=/home/ubuntu/sbi-stage25-login-config-review
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-private-stage
REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation
PIN=a873b5b3fcd284d477866175b16e7817de463078
PY_SHA=bc664c2cc5d3848e6889c3c61f70f8d1f24ad639
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo "LOGIN_CONFIG_READONLY_QA=FAIL step=$STEP code=$rc"; fi; echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"; exit "$rc"' EXIT
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"

echo "=== A. CHECK LIVE AND PRIVATE STAGING UNCHANGED ==="
STEP=BASELINE
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
echo "PRIVATE_STAGE_RUNNING_AND_UNPUBLISHED=PASS"

echo "=== B. PINNED SOURCE INSPECTOR, SYNTAX CHECK ==="
STEP=FETCH
curl -4 -fLsS --retry 3 -o inspect_login_config_safe.py "$REPO/$PIN/database/stages23_25/inspect_login_config_safe.py"
[[ "$(git hash-object inspect_login_config_safe.py)" == "$PY_SHA" ]]
python3 -m py_compile inspect_login_config_safe.py
echo "CONFIG_INSPECTOR_VERIFIED=PASS"

echo "=== C. AUTH CONFIG IN LIVE PR129 (KEY PRESENCE ONLY) ==="
STEP=LIVE_AUTH_CONFIG
sudo -n docker exec -i "$LIVE" python3 -B - < inspect_login_config_safe.py | tee live_auth_config.txt
grep -qx 'AUTH_CONFIG_INVENTORY=COMPLETE' live_auth_config.txt

echo "=== D. AUTH CONFIG IN PRIVATE STAGING (KEY PRESENCE ONLY) ==="
STEP=STAGE_AUTH_CONFIG
sudo -n docker exec -i "$STAGE" python3 -B - < inspect_login_config_safe.py | tee stage_auth_config.txt
grep -qx 'AUTH_CONFIG_INVENTORY=COMPLETE' stage_auth_config.txt

echo "=== E. KEY-PRESENCE GAP (VALUES NEVER DISPLAYED) ==="
STEP=DIFF
awk '/^AUTH_ENV_KEY=/{if ($0 ~ / STATE=PRESENT$/) {split($1, a, "="); print a[2]}}' live_auth_config.txt | sort -u > live_present_keys.txt
awk '/^AUTH_ENV_KEY=/{if ($0 ~ / STATE=PRESENT$/) {split($1, a, "="); print a[2]}}' stage_auth_config.txt | sort -u > stage_present_keys.txt
comm -23 live_present_keys.txt stage_present_keys.txt > auth_key_gaps.txt
if [[ -s auth_key_gaps.txt ]]; then
  echo "LIVE_KEYS_ABSENT_IN_STAGING=REVIEW_REQUIRED"
  sed 's/^/STAGING_MISSING_KEY_NAME=/' auth_key_gaps.txt
else
  echo "LIVE_KEYS_ABSENT_IN_STAGING=NONE_OF_INSPECTED_KEYS"
fi
if ! grep -q 'LOGIN_SETUP_MESSAGE_LOCATION=' live_auth_config.txt &&
   ! grep -q 'LOGIN_SETUP_MESSAGE_LOCATION=' stage_auth_config.txt; then
  echo "LOGIN_MESSAGE_SOURCE=NOT_FOUND_IN_SELECTED_FILES"
fi
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
echo "LIVE_AND_STAGE_CONTAINERS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL LOGIN CONFIG DIAGNOSTIC ==="
echo "LOGIN_CONFIG_READONLY_QA=PASS"
echo "DIAGNOSIS_SCOPE=CONFIGURATION_KEY_PRESENCE_ONLY"
echo "FIREBASE_AUTHENTICATED_E2E=NOT_PERFORMED"
echo "LIVE_RELEASE=BLOCKED_PENDING_FIREBASE_AUTHENTICATED_STAGING_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REVIEW_MISSING_AUTH_CONFIGURATION_NAMES_AND_SET_UP_SECURE_STAGING_AUTH"
