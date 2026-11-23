#!/usr/bin/env bash
# R8 staging Docker smoke, GitHub-hosted with synthetic values only.
set -Eeuo pipefail
umask 077
: "$R8_STAGING_IMAGE"
: "$R8_STAGING_SHA"
: "$GITHUB_RUN_ID"
: "$GITHUB_RUN_ATTEMPT"
[[ "$R8_STAGING_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]] || exit 2
[[ "$R8_STAGING_IMAGE" == sbi-r8-staging:* ]] || exit 2
[[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$R8_STAGING_IMAGE")" == "$R8_STAGING_SHA" ]] || exit 2

set +e
timeout 25s docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  "$R8_STAGING_IMAGE" > /tmp/r8-staging-expected-refusal.log 2>&1
refusal=$?
set -e
[[ "$refusal" -ne 0 && "$refusal" -ne 124 ]] || { echo 'R8_STAGING_DEFAULT_DENIAL=FAIL'; exit 1; }
grep -Fq 'R8_STAGING_STARTUP_REFUSED: explicit nonproduction mode required' /tmp/r8-staging-expected-refusal.log || {
  echo 'R8_STAGING_DEFAULT_DENIAL=FAIL_WRONG_ERROR'
  exit 1
}
echo 'R8_STAGING_DEFAULT_DENIAL=PASS'

CANARY="sbi-r8-ci-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
if docker container inspect "$CANARY" >/dev/null 2>&1; then
  echo 'R8_STAGING_NAME_COLLISION=BLOCKED'
  exit 2
fi
BASELINE="$(docker ps -a --format '{{.ID}}' | sort)"
cleanup() {
  local result=$?
  trap - EXIT
  docker rm -f "$CANARY" >/dev/null 2>&1 || true
  if docker container inspect "$CANARY" >/dev/null 2>&1; then
    echo 'R8_STAGING_CANARY_CLEANUP=FAILED'
    result=1
  fi
  if [[ "$(docker ps -a --format '{{.ID}}' | sort)" != "$BASELINE" ]]; then
    echo 'R8_STAGING_CANARY_CLEANUP=BASELINE_CHANGED'
    result=1
  fi
  if [[ "$result" == 0 ]]; then
    echo 'R8_STAGING_CANARY_CLEANUP=PASS'
    echo 'R8_STAGING_GITHUB_CANARY=PASS_ROLLED_BACK'
  else
    echo 'R8_STAGING_GITHUB_CANARY=FAIL'
  fi
  exit "$result"
}
trap cleanup EXIT

docker run -d --name "$CANARY" \
  --network none --read-only --user 10001:10001 \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 384m --cpus 1 --restart no \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --tmpfs /var/lib/sbi-r8-staging-evidence:rw,noexec,nosuid,uid=10001,gid=10001,mode=0700,size=16m \
  -e SBI_R8_STAGING_MODE=SBI_R8_STAGING_ONLY_NONFINANCIAL \
  -e SBI_R8_STAGING_FIREBASE_PROJECT_ID=sbi-r9-staging \
  -e SBI_R8_STAGING_SITE_ORIGIN=https://sbi-r9-staging-qa.example.invalid \
  -e SBI_R8_STAGING_FIREBASE_WEB_API_KEY=r8-synthetic-only-00000000000000000001 \
  -e SBI_R8_STAGING_EVIDENCE_DIR=/var/lib/sbi-r8-staging-evidence \
  -e SBI_READONLY_QUARANTINE_SOL_KEYS=7001,7002,7003 \
  "$R8_STAGING_IMAGE" >/dev/null

[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$CANARY")" == 'none' ]]
[[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$CANARY")" == 'true' ]]
[[ "$(docker inspect -f '{{.Config.User}}' "$CANARY")" == '10001:10001' ]]
[[ "$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$CANARY")" == '{}' || "$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$CANARY")" == 'null' ]]
[[ "$(docker inspect -f '{{json .Mounts}}' "$CANARY")" == '[]' ]]
echo 'R8_STAGING_DOCKER_ISOLATION=PASS'

ready=0
for attempt in $(seq 1 30); do
  if docker exec "$CANARY" python -c 'from urllib.request import urlopen; urlopen("http://127.0.0.1:8080/healthz",timeout=2)' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo 'R8_STAGING_HEALTH_TIMEOUT'
  echo 'R8_STAGING_CONTAINER_DIAGNOSTICS_START'
  docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$CANARY" || true
  docker logs --tail 30 "$CANARY" 2>&1 || true
  echo 'R8_STAGING_CONTAINER_DIAGNOSTICS_END'
  exit 3
fi

docker exec -i "$CANARY" python - <<'PY'
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

base = "http://127.0.0.1:8080"
with urlopen(base + "/healthz", timeout=5) as response:
    info=json.load(response)
    assert response.status == 200
    assert response.headers["X-SBI-Environment"] == "R8-STAGING-NONFINANCIAL"
    assert info["financial_data_connected"] is False
    assert info["financial_execution_enabled"] is False
    assert info["report_data_connected"] is False

def code(path, method="GET"):
    try:
        with urlopen(Request(base + path, method=method), timeout=5) as r:
            return r.status
    except HTTPError as e:
        return e.code

assert code("/api/payment-reconciliation/status") == 401
assert code("/api/payment-reconciliation/run", "POST") == 403
assert code("/api/imports/apply", "POST") == 403
print("R8_STAGING_INTERNAL_HEALTH_AND_DENIAL=PASS")
print("R8_FINANCIAL_APPLY=LOCKED")
print("R8_REAL_FIREBASE=NOT_EXECUTED")
print("R8_AWS=NOT_EXECUTED")
PY
