#!/usr/bin/env bash
# Stage 6D consolidated read-only Docker candidate batch (no network or server).
# Does NOT connect Firebase, start a web service, change AWS infrastructure, or access finance.
set -u
image="${1:-sbi-stage6d-candidate:c949777ffa32}"
fail=0
block=0
check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "$name=PASS"
  else
    echo "$name=FAIL"
    fail=1
  fi
}
if ! command -v docker >/dev/null 2>&1; then
  echo "DOCKER_AVAILABLE=BLOCKED"
  echo "BATCH_QA=BLOCKED"
  echo "NEXT_GATE=INSTALL_OR_ACCESS_DOCKER_WITHOUT_CHANGE_TO_PRODUCTION"
  exit 2
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "CANDIDATE_IMAGE=BLOCKED"
  echo "BATCH_QA=BLOCKED"
  echo "NEXT_GATE=VERIFY_PINNED_LOCAL_DOCKER_IMAGE"
  exit 2
fi
echo "CANDIDATE_IMAGE=PASS"
check IMAGE_NON_ROOT test "$(docker image inspect "$image" --format '{{.Config.User}}')" = "65534:65534"
check PRIVATE_RELEASE_LABEL test "$(docker image inspect "$image" --format '{{index .Config.Labels "sbi.release.status"}}')" = "PRIVATE_AUTH_SHELL_ONLY_FINANCIAL_DISABLED"

output="$(docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  -e SBI_STAGE6_AUTH_PROFILE=aws-private-staging \
  -e SBI_STAGE6_AWS_ORIGIN=https://sbi-stage6.13-232-241-221.sslip.io \
  -e SBI_STAGE6_PRIVATE_ONLY=1 \
  -e SBI_STAGE6_FINANCIAL_EXECUTION=disabled \
  -e SBI_STAGE6_BACKEND_CONNECTED=false \
  --entrypoint python3 "$image" /app/stage6d_private_entry.py --check 2>&1)"
rc=$?
if [ "$rc" -eq 0 ] && printf '%s\n' "$output" | grep -Fxq 'STAGE6D_PRIVATE_GATE=READY_PRIVATE_AUTH_SHELL_ONLY' && printf '%s\n' "$output" | grep -Fxq 'FIREBASE_ADMIN_LIVE=NOT_VERIFIED' && printf '%s\n' "$output" | grep -Fxq 'FINANCIAL_API=BLOCKED'; then
 echo "PRIVATE_STARTUP_GATE=PASS"
 echo "REAL_FIREBASE_LOGIN=NOT_TESTED"
 echo "FINANCIAL_API_LIVE=NOT_TESTED"
else
 echo "PRIVATE_STARTUP_GATE=FAIL"
 fail=1
fi
if [ "$fail" -ne 0 ]; then
 echo "BATCH_QA=FAIL"
 echo "NEXT_GATE=REVIEW_PRIVATE_CANDIDATE_TEST_FAILURE"
 exit 1
fi
echo "BATCH_QA=PASS"
echo "NEXT_GATE=PRIVATE_LOCALHOST_HTTP_TEST_REQUIRES_SEPARATE_RUNTIME_APPROVAL"
