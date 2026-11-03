#!/usr/bin/env bash
# One-time remediation of the isolated AWS staging preview login.
# Run only from an exact reviewed origin/main commit; never mutates financial APIs.
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ "$(id -u)" -eq 0 && "$#" -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
  echo "BLOCKED: root and one full reviewed main SHA are required"; exit 2;
}
SHA="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || {
  echo "BLOCKED: source checkout SHA mismatch"; exit 2;
}
[[ "$(git -C "$ROOT" remote get-url origin)" == "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git" ]] || {
  echo "BLOCKED: unexpected repository origin"; exit 2;
}
[[ "$(git -C "$ROOT" ls-remote origin refs/heads/main | awk '{print $1}')" == "$SHA" ]] || {
  echo "BLOCKED: source is not current reviewed main"; exit 2;
}
git -C "$ROOT" show "$SHA:staging/aws_lightsail/bootstrap_stage_preview_login.sh" |
  cmp -s - "$ROOT/staging/aws_lightsail/bootstrap_stage_preview_login.sh" || {
    echo "BLOCKED: bootstrap code differs from reviewed SHA"; exit 2;
  }
NAME="sbi-agent-stage"
PORT=18082
PROBE_PORT=18083
AUTH_FILE="/etc/sbi-stage-preview-login.env"
BACKUP_NAME="sbi-stage-pre-auth-backup"
PROBE_NAME="sbi-stage-auth-probe"
ROLLBACK_IMAGE="sbi-stage-pre-auth:$(date -u +%Y%m%dT%H%M%SZ)"
exec 9>/run/lock/sbi-stage-release.lock
flock -n 9 || { echo "BLOCKED: concurrent staging operation"; exit 2; }
[[ "$(docker inspect "$NAME" --format '{{.State.Running}}' 2>/dev/null)" == true ]] || {
  echo "BLOCKED: isolated staging container not running"; exit 2;
}
docker inspect "$NAME" --format '{{json .HostConfig.PortBindings}}' |
  python3 -c '
import json, sys
p=json.load(sys.stdin)
assert p == {"8080/tcp":[{"HostIp":"127.0.0.1","HostPort":"18082"}]}, "Unexpected container ports"
' || { echo "BLOCKED: staging port isolation differs"; exit 2; }
[[ "$(docker inspect "$NAME" --format '{{len .Mounts}}')" == 0 ]] || {
  echo "BLOCKED: staging container has mounted data"; exit 2;
}
! docker container inspect "$BACKUP_NAME" >/dev/null 2>&1 || {
  echo "BLOCKED: existing backup container requires review"; exit 2;
}
! docker container inspect "$PROBE_NAME" >/dev/null 2>&1 || {
  echo "BLOCKED: existing probe container requires review"; exit 2;
}
# Only known preview credentials may be persisted, never import financial settings.
if [[ ! -e "$AUTH_FILE" ]]; then
  TEMP="$(mktemp /etc/.sbi-stage-preview-login.XXXXXXXX)"
  python3 - "$TEMP" <<'PY'
from pathlib import Path
from secrets import token_urlsafe
import sys
Path(sys.argv[1]).write_text(
    "PREVIEW_USERNAME=stage-reviewer\nPREVIEW_PASSWORD=" + token_urlsafe(36) + "\n",
    encoding="utf-8"
)
PY
  chmod 0600 "$TEMP"
  chown root:root "$TEMP"
  mv -n "$TEMP" "$AUTH_FILE"
  [[ ! -e "$TEMP" ]] || { rm -f "$TEMP"; echo "BLOCKED: credential file collision"; exit 2; }
fi
[[ "$(stat -c '%U:%a' "$AUTH_FILE")" == "root:600" ]] || {
  echo "BLOCKED: credential file permissions"; exit 2;
}
python3 - "$AUTH_FILE" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert len(lines)==2 and lines[0].startswith("PREVIEW_USERNAME=")
assert lines[1].startswith("PREVIEW_PASSWORD=")
username=lines[0].split("=",1)[1]
password=lines[1].split("=",1)[1]
assert username and ":" not in username and len(password)>=20
assert not any("\r" in line or "\x00" in line for line in lines)
PY
IMAGE="$(docker inspect "$NAME" --format '{{.Image}}')"
docker image inspect "$IMAGE" >/dev/null
docker tag "$IMAGE" "$ROLLBACK_IMAGE"
echo "ISOLATED_STAGE_IMAGE_BACKUP=PASS"
echo "CREDENTIAL_FILE_SECURED=PASS"
echo "CREDENTIAL_VALUES_NOT_PRINTED=YES"

wait_for_health() {
  local port="$1"
  for _ in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then
      [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/")" == 401 ]] || return 1
      return 0
    fi
    sleep 1
  done
  return 1
}
verify_login() {
  docker exec "$1" python -c '
import base64, os, urllib.request, urllib.error
username=os.environ["PREVIEW_USERNAME"]
password=os.environ["PREVIEW_PASSWORD"]
auth="Basic "+base64.b64encode((username+":"+password).encode()).decode()
def status(url):
    request=urllib.request.Request("http://127.0.0.1:8080"+url,headers={"Authorization":auth})
    try:
        with urllib.request.urlopen(request,timeout=5) as response: return response.status
    except urllib.error.HTTPError as error: return error.code
assert status("/")==200
assert status("/api/upload")==403
'
}
MUTATED=0
rollback() {
  local code=$?
  trap - EXIT
  docker rm -f "$PROBE_NAME" >/dev/null 2>&1 || true
  if (( code != 0 && MUTATED == 1 )); then
    echo "STAGING_LOGIN_ROLLBACK=STARTED"
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    if docker rename "$BACKUP_NAME" "$NAME" &&
       docker start "$NAME" >/dev/null &&
       curl -fsS --max-time 5 "http://127.0.0.1:$PORT/healthz" >/dev/null; then
      echo "STAGING_LOGIN_ROLLBACK=PASS"
    else
      echo "STAGING_LOGIN_ROLLBACK=FAIL"
    fi
  fi
  exit "$code"
}
trap rollback EXIT
docker run -d --name "$PROBE_NAME" --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 256m -p "127.0.0.1:$PROBE_PORT:8080" \
  --env-file "$AUTH_FILE" -e PORT=8080 "$IMAGE" >/dev/null
wait_for_health "$PROBE_PORT" && verify_login "$PROBE_NAME" || {
  echo "BLOCKED: stage preview image does not support secure login"; exit 2;
}
echo "AUTH_PROBE=PASS"
docker rm -f "$PROBE_NAME" >/dev/null
# Retain original container configuration until replacement passes all gates.
docker stop "$NAME" >/dev/null
docker rename "$NAME" "$BACKUP_NAME"
MUTATED=1
docker run -d --name "$NAME" --restart unless-stopped \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 256m \
  -p "127.0.0.1:$PORT:8080" --env-file "$AUTH_FILE" -e PORT=8080 "$IMAGE" >/dev/null
wait_for_health "$PORT" && verify_login "$NAME" || {
  echo "STAGING_LOGIN_ACTIVATION=FAIL"; exit 2;
}
MUTATED=0
docker rm -f "$BACKUP_NAME" >/dev/null
trap - EXIT
echo "STAGING_LOGIN_BOOTSTRAP=PASS"
echo "EXISTING_STAGING_IMAGE_REUSED=YES"
echo "AUTH_FILE=$AUTH_FILE"
echo "PRODUCTION_PREVIEW=UNMODIFIED"
echo "FINANCIAL_WRITES=DISABLED"
echo "NEXT_STEP=RETRY_SINGLE_GITHUB_STAGING_RELEASE"
