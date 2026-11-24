#!/usr/bin/env bash
# R5 development-only isolated offline canary. Never touches AWS or finance.
set -Eeuo pipefail
umask 077
: "${R5_IMAGE:?R5_IMAGE_REQUIRED}"
: "${R5_SOURCE_SHA:?R5_SOURCE_SHA_REQUIRED}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID_REQUIRED}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT_REQUIRED}"
[[ "$R5_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'R5_BLOCKED_BAD_SOURCE_SHA'; exit 2; }
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]] || { echo 'R5_BLOCKED_BAD_RUN_ID'; exit 2; }
CANARY="sbi-r5-offline-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
[[ "$R5_IMAGE" == sbi-r5-offline:* ]] || { echo 'R5_BLOCKED_UNEXPECTED_IMAGE'; exit 2; }
[[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$R5_IMAGE")" == "$R5_SOURCE_SHA" ]] || { echo 'R5_BLOCKED_IMAGE_SHA_MISMATCH'; exit 2; }
if docker container inspect "$CANARY" >/dev/null 2>&1; then
  echo 'R5_BLOCKED_CANARY_NAME_ALREADY_USED'; exit 2
fi
BASELINE="$(docker ps -a --format '{{.ID}}' | sort)"
cleanup() {
  local result=$?
  trap - EXIT
  if docker container inspect "$CANARY" >/dev/null 2>&1; then
    docker rm -f "$CANARY" >/dev/null || result=1
  fi
  if docker container inspect "$CANARY" >/dev/null 2>&1; then
    echo 'R5_CANARY_ROLLBACK=FAIL_CONTAINER_REMAINS'
    result=1
  fi
  if [[ "$(docker ps -a --format '{{.ID}}' | sort)" != "$BASELINE" ]]; then
    echo 'R5_CANARY_ROLLBACK=FAIL_EXISTING_CONTAINER_INVENTORY_CHANGED'
    result=1
  fi
  if [[ "$result" -eq 0 ]]; then
    echo 'R5_CANARY_ROLLBACK=PASS'
    echo 'R5_OFFLINE_GITHUB_CANARY=PASS_ROLLED_BACK'
  else
    echo 'R5_OFFLINE_GITHUB_CANARY=FAIL_OR_BLOCKED'
  fi
  exit "$result"
}
trap cleanup EXIT

docker run -d --name "$CANARY" \
  --network none \
  --read-only --user 10001:10001 \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 384m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --restart no \
  "$R5_IMAGE" >/dev/null

[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$CANARY")" == 'none' ]]
[[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$CANARY")" == 'true' ]]
[[ "$(docker inspect -f '{{.Config.User}}' "$CANARY")" == '10001:10001' ]]
[[ "$(docker inspect -f '{{json .Mounts}}' "$CANARY")" == '[]' ]]
[[ "$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$CANARY")" == '{}' || "$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$CANARY")" == 'null' ]]
[[ "$(docker inspect -f '{{.HostConfig.Privileged}}' "$CANARY")" == 'false' ]]
[[ "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$CANARY")" == 'no' ]]
[[ "$(docker inspect -f '{{.HostConfig.Memory}}' "$CANARY")" == '402653184' ]]
echo 'R5_DOCKER_ISOLATION=PASS'

ready=0
for i in $(seq 1 30); do
  if docker exec "$CANARY" python -c 'from urllib.request import urlopen; urlopen("http://127.0.0.1:8080/healthz", timeout=2)' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
[[ "$ready" -eq 1 ]] || { echo 'R5_HEALTH_TIMEOUT'; exit 3; }

docker exec -i "$CANARY" python - <<'PY'
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
opener = build_opener(NoRedirect())
base = 'http://127.0.0.1:8080'

def status(path, method='GET'):
    request = Request(base + path, method=method)
    try:
        with opener.open(request, timeout=5) as response:
            return response.status
    except HTTPError as exc:
        return exc.code

checks = (
    ('/healthz', 'GET', 200),
    ('/login', 'GET', 200),
    ('/', 'GET', 303),
    ('/api/payment-reconciliation/status', 'GET', 401),
    ('/api/payment-evidence/uploads', 'GET', 401),
    ('/api/payment-evidence/template', 'GET', 401),
    ('/api/payment-evidence/upload', 'POST', 403),
    ('/api/payment-reconciliation/preflight', 'POST', 403),
    ('/api/payment-reconciliation/run', 'POST', 403),
    ('/api/imports/apply', 'POST', 403),
)
for path, method, expected in checks:
    actual = status(path, method)
    assert actual == expected, (path, method, actual, expected)
with opener.open(base + '/healthz', timeout=5) as response:
    health = json.load(response)
assert health['financial_data_connected'] is False
assert health['financial_execution_enabled'] is False
assert health['report_data_connected'] is False
print('R5_OFFLINE_HTTP_HEALTH_AND_DENIAL=PASS')
print('R5_FINANCIAL_APPLY=LOCKED')
print('R5_REAL_FIREBASE_TEST=NOT_EXECUTED')
print('R5_AWS_CANARY=NOT_EXECUTED')
PY
