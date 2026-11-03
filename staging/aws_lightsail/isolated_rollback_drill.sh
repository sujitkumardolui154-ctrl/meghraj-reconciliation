#!/usr/bin/env bash
# Controlled rollback rehearsal on loopback-only CLONE of SBI AWS staging.
# NEVER stops, renames, or replaces live sbi-agent-stage or the public preview.
# Run as: sudo bash staging/aws_lightsail/isolated_rollback_drill.sh <reviewed-main-sha>
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ "$(id -u)" -eq 0 && "$#" -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
  echo "BLOCKED: root and one exact release SHA required"; exit 2;
}
SHA="$1"
REPO="https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || {
  echo "BLOCKED: checkout SHA mismatch"; exit 2;
}
[[ "$(git -C "$ROOT" remote get-url origin)" == "$REPO" ]] || {
  echo "BLOCKED: unexpected origin"; exit 2;
}
REMOTE_MAIN="$(git -C "$ROOT" ls-remote origin refs/heads/main | awk '{print $1}')"
[[ "$REMOTE_MAIN" == "$SHA" ]] || {
  echo "BLOCKED: SHA must match reviewed origin/main"; exit 2;
}
git -C "$ROOT" show "$SHA:staging/aws_lightsail/isolated_rollback_drill.sh" |
  cmp -s - "$ROOT/staging/aws_lightsail/isolated_rollback_drill.sh" || {
  echo "BLOCKED: script differs from reviewed main"; exit 2;
}
exec 9>/run/lock/sbi-stage-release.lock
flock -n 9 || { echo "BLOCKED: staging deployment currently running"; exit 2; }

LIVE="sbi-agent-stage"
CLONE="sbi-stage-rollback-drill"
PORT=18084
[[ "$(docker inspect "$LIVE" --format '{{.State.Running}}' 2>/dev/null)" == true ]] || {
  echo "BLOCKED: live staging is not running"; exit 2;
}
docker inspect "$LIVE" --format '{{json .HostConfig.PortBindings}}' |
  python3 -c '
import json, sys
p=json.load(sys.stdin)
assert p == {"8080/tcp":[{"HostIp":"127.0.0.1","HostPort":"18082"}]}, "Unexpected live staging port bindings"
' || { echo "BLOCKED: live staging is not isolated"; exit 2; }
[[ "$(docker inspect "$LIVE" --format '{{len .Mounts}}')" == 0 ]] || {
  echo "BLOCKED: live staging has attached volumes"; exit 2;
}
! docker container inspect "$CLONE" >/dev/null 2>&1 || {
  echo "BLOCKED: drill container name already exists"; exit 2;
}
LIVE_IMAGE="$(docker inspect "$LIVE" --format '{{.Image}}')"
docker image inspect "$LIVE_IMAGE" >/dev/null
AUTH_ENV_FILE="$(mktemp /run/sbi-stage-drill-auth.XXXXXXXX)"
cleanup() {
  code=$?
  trap - EXIT
  docker rm -f "$CLONE" >/dev/null 2>&1 || true
  rm -f -- "$AUTH_ENV_FILE"
  exit "$code"
}
trap cleanup EXIT
docker inspect "$LIVE" --format '{{json .Config.Env}}' |
  python3 "$ROOT/staging/aws_lightsail/preview_auth_env.py" "$AUTH_ENV_FILE"
[[ "$(stat -c '%U:%a' "$AUTH_ENV_FILE")" == "root:600" ]] || {
  echo "BLOCKED: drill credentials file permissions invalid"; exit 2;
}
curl -fsS --max-time 5 http://127.0.0.1:18082/healthz >/dev/null

start_clone() {
  # The only Docker changes in this script target the dedicated CLONE name and loopback port.
  docker run -d --name "$CLONE" --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 128 --memory 256m -p "127.0.0.1:$PORT:8080" \
    --env-file "$AUTH_ENV_FILE" -e PORT=8080 "$@" "$LIVE_IMAGE" >/dev/null
}
wait_healthy() {
  for _ in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
      [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")" == 401 ]] || return 1
      return 0
    fi
    sleep 1
  done
  return 1
}
authenticated() {
  docker exec "$CLONE" python -c '
import base64
import os
import urllib.error
import urllib.request
pair = (os.environ["PREVIEW_USERNAME"] + ":" + os.environ["PREVIEW_PASSWORD"]).encode()
authorization = "Basic " + base64.b64encode(pair).decode("ascii")
def status(path):
    request = urllib.request.Request("http://127.0.0.1:8080" + path,
                                     headers={"Authorization": authorization})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
if status("/") != 200 or status("/api/upload") != 403:
    raise SystemExit(1)
'
}
# Baseline clone: valid login and blocked upload.
start_clone
wait_healthy && authenticated || { echo "BASELINE_CLONE=FAIL"; exit 1; }
echo "BASELINE_CLONE=PASS"
docker rm -f "$CLONE" >/dev/null

# Fault injection: same image, deliberately invalid password.
# Health must still be 200, but authenticated preview must fail.
start_clone -e PREVIEW_PASSWORD=invalid
wait_healthy || { echo "FAULT_PROBE=FAIL"; exit 1; }
if authenticated; then
  echo "FAULT_DETECTION=FAIL"; exit 1
fi
echo "FAULT_DETECTION=PASS"
docker rm -f "$CLONE" >/dev/null

# Restore the exact original image and preserved preview login on the CLONE.
start_clone
wait_healthy && authenticated || { echo "CLONE_ROLLBACK=FAIL"; exit 1; }
echo "CLONE_ROLLBACK=PASS"
[[ "$(docker inspect "$LIVE" --format '{{.State.Running}}')" == true ]] || {
  echo "LIVE_STAGING=UNHEALTHY"; exit 1;
}
[[ "$(docker inspect "$LIVE" --format '{{.Image}}')" == "$LIVE_IMAGE" ]] || {
  echo "LIVE_STAGING=IMAGE_CHANGED"; exit 1;
}
curl -fsS --max-time 5 http://127.0.0.1:18082/healthz >/dev/null

LOG_DIR="/var/log/sbi-stage-release"
install -d -m 0700 -o root -g root "$LOG_DIR"
REPORT="$LOG_DIR/rollback-drill-$(date -u +%Y%m%dT%H%M%SZ).json"
REPORT="$REPORT" RELEASE_SHA="$SHA" LIVE_IMAGE="$LIVE_IMAGE" python3 - <<'PY'
import datetime
import json
import os
from pathlib import Path
path=Path(os.environ["REPORT"])
record={
  "timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "release_sha":os.environ["RELEASE_SHA"],
  "live_stage_image":os.environ["LIVE_IMAGE"],
  "baseline_clone":"PASS",
  "injected_failure_detected":"PASS",
  "isolated_clone_rollback":"PASS",
  "live_staging_unchanged":True,
  "financial_database_written":False,
  "actual_live_executor_rollback_drilled":False
}
path.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n",encoding="utf-8")
path.chmod(0o600)
PY
echo "ROLLBACK_REHEARSAL=PASS"
echo "LIVE_STAGING_UNCHANGED=PASS"
echo "LIVE_EXECUTOR_ROLLBACK=NOT_TESTED"
echo "FINANCIAL_WRITES=DISABLED"
echo "RELEASE_EVIDENCE=$REPORT"
