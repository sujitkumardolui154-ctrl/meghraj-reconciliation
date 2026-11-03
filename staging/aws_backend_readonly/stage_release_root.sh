#!/usr/bin/env bash
# Install as root-owned 0750 /usr/local/sbin/sbi_backend_readonly_stage_release.sh.
# The only permitted sudo action for the dedicated sbi-backend-deployer identity.
# NEVER target the public dashboard, its Caddy container, 18081, 18082, 80 or 443.
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
[[ $# -eq 0 && "$(id -u)" == 0 ]] || { echo 'BLOCKED: root stdin-only interface required'; exit 2; }
IFS= read -r REQUEST || { echo 'BLOCKED: missing command'; exit 2; }
REMAINDER=''
if IFS= read -r REMAINDER || [[ -n "$REMAINDER" ]]; then
  echo 'BLOCKED: extra input'; exit 2
fi

ENVFILE=/etc/sbi-backend-readonly/stage.env
SRC=/var/lib/sbi-backend-readonly/source
NAME=sbi-backend-readonly-stage
NETWORK=sbi-backend-readonly-net
PROBE=sbi-backend-readonly-probe
IMAGE_PREFIX=sbi-backend-readonly-candidate
LOGDIR=/var/log/sbi-backend-readonly

check_config() {
  [[ -f "$ENVFILE" && ! -L "$ENVFILE" ]] || { echo 'BLOCKED: host-only credential file missing'; exit 2; }
  [[ "$(stat -c '%u:%a' "$ENVFILE")" == '0:600' ]] || {
    echo 'BLOCKED: host credential ownership/mode must be root:0600'; exit 2;
  }
  # This file is prepared by the host administrator and never fetched from Git.
  # shellcheck disable=SC1090
  source "$ENVFILE"
  [[ -n "${SBI_AWS_REPORT_USERNAME:-}" && "${#SBI_AWS_REPORT_PASSWORD}" -ge 24 ]] || {
    echo 'BLOCKED: distinct, strong staging report login required'; exit 2;
  }
  [[ "$SBI_AWS_REPORT_USERNAME" != *:* ]] || { echo 'BLOCKED: invalid username'; exit 2; }
  [[ "$SBI_AWS_REPORT_USERNAME" != *$'\n'* && "$SBI_AWS_REPORT_PASSWORD" != *$'\n'* ]] || {
    echo 'BLOCKED: newline in credentials'; exit 2;
  }
  for binary in git docker curl python3 flock; do
    command -v "$binary" >/dev/null || { echo "BLOCKED: dependency missing ($binary)"; exit 2; }
  done
}

if [[ "$REQUEST" == status ]]; then
  check_config
  echo 'SBI_BACKEND_EXECUTOR=READONLY_V1'
  echo 'DEPLOY_TARGET=LOOPBACK_ONLY_18086'
  echo 'FINANCIAL_WRITES=DISABLED'
  exit 0
fi
[[ "$REQUEST" =~ ^[a-f0-9]{40}$ ]] || { echo 'BLOCKED: valid full Git SHA required'; exit 2; }
SHA="$REQUEST"
check_config
exec 9>/run/lock/sbi-backend-readonly-stage.lock
flock -n 9 || { echo 'BLOCKED: another backend staging release is running'; exit 2; }
mkdir -p "$SRC" "$LOGDIR"
chmod 700 "$SRC" "$LOGDIR"
LOG="$LOGDIR/$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.log"
exec > >(tee -a "$LOG") 2>&1
echo "BACKEND_STAGING_SOURCE_SHA=$SHA"
echo 'PUBLIC_DASHBOARD=UNMODIFIED'
echo 'FINANCIAL_DATA=NOT_CONNECTED'
echo 'FINANCIAL_WRITES=DISABLED'
[[ ! -e "$SRC/.git" || -d "$SRC/.git" ]] || { echo 'BLOCKED: invalid source directory'; exit 2; }
if [[ ! -d "$SRC/.git" ]]; then
  [[ -z "$(find "$SRC" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
    echo 'BLOCKED: staging source directory not empty'; exit 2;
  }
  git init -q "$SRC"
  git -C "$SRC" remote add origin 'https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git'
fi
[[ "$(git -C "$SRC" remote get-url origin)" == 'https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git' ]] || {
  echo 'BLOCKED: unexpected repository origin'; exit 2;
}
git -C "$SRC" -c core.hooksPath=/dev/null fetch --no-tags --depth=1 origin refs/heads/main
[[ "$(git -C "$SRC" rev-parse FETCH_HEAD)" == "$SHA" ]] || {
  echo 'BLOCKED: release SHA must be the reviewed main HEAD'; exit 2;
}
git -C "$SRC" -c core.hooksPath=/dev/null checkout --force --detach "$SHA"
[[ -f "$SRC/staging/aws_backend_readonly/Dockerfile" ]] || { echo 'BLOCKED: no backend Dockerfile'; exit 2; }
CANDIDATE="$IMAGE_PREFIX:${SHA:0:12}"
# Financial engine, Firebase and all private report data are absent from image.
docker build --build-arg SBI_SOURCE_SHA="$SHA" -f "$SRC/staging/aws_backend_readonly/Dockerfile" -t "$CANDIDATE" "$SRC"
if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --internal "$NETWORK" >/dev/null
fi
[[ "$(docker network inspect -f '{{.Internal}}' "$NETWORK")" == 'true' ]] || {
  echo 'BLOCKED: staging network must be internal'; exit 2;
}

run_candidate() {
  local name="$1" port="$2" image="$3"
  docker run -d --name "$name" --restart no --network "$NETWORK" \
    --user 10001:10001 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 256m \
    -p "127.0.0.1:$port:8080" --env-file "$ENVFILE" -e SBI_SOURCE_SHA="$SHA" "$image" >/dev/null
}
probe_http() {
  local port="$1" attempt
  for attempt in $(seq 1 25); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$port/healthz")" == 200 ]]; then
      [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$port/readyz")" == 503 ]] || return 1
      [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$port/reports")" == 401 ]] || return 1
      [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$port/api/upload")" == 403 ]] || return 1
      return 0
    fi
    sleep 1
  done
  return 1
}
# Test authentication inside the container without copying secrets to logs,
# command-line arguments, GitHub, or host curl history.
probe_authenticated() {
  docker exec "$1" python -c '
import base64, json, os, urllib.request, urllib.error
auth = "Basic " + base64.b64encode(
    (os.environ["SBI_AWS_REPORT_USERNAME"]+":"+os.environ["SBI_AWS_REPORT_PASSWORD"]).encode()
).decode()
def get(path):
    req = urllib.request.Request("http://127.0.0.1:8080"+path, headers={"Authorization":auth})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as ex:
        return ex.code
assert get("/reports") == 503
assert get("/reports/unpaid.csv") == 503
assert get("/api/upload") == 403
'
}
OLD_IMAGE=''
if docker container inspect "$NAME" >/dev/null 2>&1; then
  OLD_IMAGE="$(docker inspect --format '{{.Image}}' "$NAME")"
  docker image inspect "$OLD_IMAGE" >/dev/null || { echo 'BLOCKED: rollback image missing'; exit 2; }
fi
MUTATED=0
cleanup() {
  local code=$?
  trap - EXIT
  docker rm -f "$PROBE" >/dev/null 2>&1 || true
  if (( code != 0 && MUTATED == 1 )); then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    if [[ -n "$OLD_IMAGE" ]]; then
      if run_candidate "$NAME" 18086 "$OLD_IMAGE" && probe_http 18086 && probe_authenticated "$NAME"; then
        echo 'BACKEND_ROLLBACK=PASS'
      else
        echo 'BACKEND_ROLLBACK=FAILED_MANUAL_INTERVENTION_REQUIRED'
      fi
    else
      echo 'BACKEND_ROLLBACK=NO_PREVIOUS_STAGE'
    fi
  fi
  exit "$code"
}
trap cleanup EXIT
docker rm -f "$PROBE" >/dev/null 2>&1 || true
run_candidate "$PROBE" 18087 "$CANDIDATE"
probe_http 18087 && probe_authenticated "$PROBE" || { echo 'BACKEND_CANARY=FAIL'; exit 1; }
echo 'BACKEND_CANARY=PASS'
docker rm -f "$PROBE" >/dev/null
MUTATED=1
docker rm -f "$NAME" >/dev/null 2>&1 || true
run_candidate "$NAME" 18086 "$CANDIDATE"
probe_http 18086 && probe_authenticated "$NAME" || { echo 'BACKEND_STAGING_HEALTH=FAIL'; exit 1; }
echo "BACKEND_STAGING_RELEASE_SHA=$SHA"
echo 'BACKEND_STAGING=PASS'
echo 'PUBLIC_DASHBOARD=UNMODIFIED'
MUTATED=0
