#!/usr/bin/env bash
# AWS SBI v1.5 login-first release: stage|activate|rollback, exact source SHA.
# Never change the six existing containers or release financial APIs.
set -Eeuo pipefail
umask 077
[[ $# -eq 2 && "$1" =~ ^(stage|activate|rollback)$ && "$2" =~ ^[a-f0-9]{40}$ ]] ||
  { echo "USAGE=stage|activate|rollback PINNED_SHA"; exit 2; }
MODE="$1"
SHA="$2"
SHORT="$(printf '%s' "$SHA" | cut -c1-12)"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(id -u)" == 0 ]] || { echo "BLOCKED_REQUIRES_AUTHORIZED_SUDO"; exit 2; }
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] ||
  { echo "BLOCKED_GIT_SOURCE_MISMATCH"; exit 2; }
git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_aws_login_v150.sh" |
  cmp -s - "$0" || { echo "BLOCKED_SCRIPT_NOT_PINNED"; exit 2; }
exec 9>/run/lock/sbi-aws-login-v150.lock
flock -n 9 || { echo "BLOCKED_CONCURRENT_LOGIN_RELEASE"; exit 2; }

OLD="aws_lightsail-sbi-preview-1"
PROXY="aws_lightsail-caddy-1"
LOGIN="sbi-login-v150-stage"
IMAGE="sbi-aws-login-v150:$SHORT"
CONFIG="/etc/sbi-aws-login-v150"
ENVFILE="$CONFIG/login.env"
KEYFILE="$CONFIG/firebase-service-account.json"
OLD_CONFIG="$ROOT/staging/aws_lightsail/Caddyfile"
NEW_CONFIG="$ROOT/staging/aws_login_v150/Caddyfile.phase1"
BACKUP="$CONFIG/Caddyfile.before-v150"
PUBLIC="https://sbi-preview.13-232-241-221.sslip.io"
docker inspect "$OLD" "$PROXY" >/dev/null ||
  { echo "BLOCKED_EXISTING_PREVIEW_NOT_FOUND"; exit 2; }
[[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true &&
   "$(docker inspect -f '{{.State.Running}}' "$PROXY")" == true ]] ||
  { echo "BLOCKED_EXISTING_PREVIEW_NOT_RUNNING"; exit 2; }
OLD_IMAGE="$(docker inspect -f '{{.Image}}' "$OLD")"
PROXY_IMAGE="$(docker inspect -f '{{.Image}}' "$PROXY")"
check_existing() {
  [[ "$(docker inspect -f '{{.Image}}' "$OLD")" == "$OLD_IMAGE" &&
     "$(docker inspect -f '{{.Image}}' "$PROXY")" == "$PROXY_IMAGE" ]]
}

check_auth_config() {
  [[ -f "$ENVFILE" && ! -L "$ENVFILE" &&
     "$(stat -c '%u:%a' "$ENVFILE")" == "0:600" ]] ||
    { echo "BLOCKED_PRIVATE_FIREBASE_ENV_REQUIRED"; return 1; }
  [[ -f "$KEYFILE" && ! -L "$KEYFILE" &&
     "$(stat -c '%u:%g:%a' "$KEYFILE")" == "0:10001:440" ]] ||
    { echo "BLOCKED_PRIVATE_FIREBASE_ADMIN_KEY_REQUIRED"; return 1; }
  python3 - "$ENVFILE" "$KEYFILE" <<'PY'
import json, pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
field = "FIREBASE_WEB_" + "API_KEY"
assert len(lines) == 1 and lines[0].startswith(field + "=")
key = lines[0].split("=",1)[1]
assert 20 <= len(key) <= 256 and key.isascii() and not any(c.isspace() for c in key)
creds = json.loads(pathlib.Path(sys.argv[2]).read_text())
assert creds.get("type") == "service_account"
assert creds.get("project_id") == "meghraj-reconciliation"
assert creds.get("client_email") and creds.get("private_key")
PY
}
shared_network() {
  local one two n
  one="$(docker inspect -f '{{range $name, $cfg := .NetworkSettings.Networks}}{{$name}} {{end}}' "$OLD")"
  two="$(docker inspect -f '{{range $name, $cfg := .NetworkSettings.Networks}}{{$name}} {{end}}' "$PROXY")"
  for n in $one; do
    if [[ " $two " == *" $n "* && "$n" != host && "$n" != bridge && "$n" != none ]]; then
      echo "$n"; return 0
    fi
  done
  return 1
}
check_login() {
  docker exec -i "$LOGIN" python3 - <<'PY'
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
opener = build_opener(NoRedirect())
def status(path, method="GET"):
    try:
        with opener.open(Request("http://127.0.0.1:8080"+path, method=method),timeout=5) as r:
            return r.status
    except HTTPError as e:
        return e.code
assert status("/healthz")==200
assert status("/login")==200
assert status("/login.css")==200
assert status("/login.js")==200
assert status("/auth/csrf")==200
assert status("/auth/config")==200
assert status("/")==303
assert status("/api/reports")==401
assert status("/api/upload",method="POST")==403
print("AWS_LOGIN_V150_LOCAL_HTTP=PASS")
print("FIREBASE_REAL_SIGNIN=NOT_TESTED")
PY
}

if [[ "$MODE" == stage ]]; then
  echo "=== AWS SBI V150 LOGIN STAGE ==="
  check_auth_config || { echo "AWS_LOGIN_STAGE=BLOCKED_AUTH_CONFIG"; exit 2; }
  NET="$(shared_network)" || { echo "BLOCKED_NO_SHARED_WEB_NETWORK"; exit 2; }
  if docker inspect "$LOGIN" >/dev/null 2>&1; then
    echo "BLOCKED_LOGIN_STAGE_ALREADY_EXISTS"; exit 2
  fi
  docker build -f "$ROOT/staging/aws_login_v150/Dockerfile" \
    --build-arg SBI_SOURCE_SHA="$SHA" -t "$IMAGE" "$ROOT"
  [[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" == "$SHA" ]] ||
    { echo "BLOCKED_IMAGE_SOURCE_LABEL_MISMATCH"; exit 2; }
  docker run -d --name "$LOGIN" --restart unless-stopped \
    --network "$NET" --network-alias sbi-login-v150 \
    --user 10001:10001 --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 128 --memory 384m \
    --env-file "$ENVFILE" \
    -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-service-account.json \
    --mount "type=bind,src=$KEYFILE,dst=/run/secrets/firebase-service-account.json,readonly" \
    "$IMAGE" >/dev/null
  if ! check_login; then
    docker stop "$LOGIN" >/dev/null 2>&1 || true
    docker rm "$LOGIN" >/dev/null 2>&1 || true
    echo "AWS_LOGIN_STAGE=FAILED_CLEANED_UP"
    exit 2
  fi
  check_existing || { echo "EXISTING_IMAGE_PARITY=FAIL"; exit 2; }
  echo "AWS_LOGIN_STAGE=PASS"
  echo "PUBLIC_PREVIEW=UNMODIFIED"
  echo "NEXT=ACTIVATE_AFTER_AUTHORIZED_DOMAIN_CHECK"
  exit 0
fi

HOST_CADDY="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$PROXY")"
[[ -n "$HOST_CADDY" && -f "$HOST_CADDY" && ! -L "$HOST_CADDY" ]] ||
  { echo "BLOCKED_CADDY_BIND_CONFIG_NOT_FOUND"; exit 2; }
mkdir -p "$CONFIG"
chmod 700 "$CONFIG"

if [[ "$MODE" == rollback ]]; then
  [[ -f "$BACKUP" && ! -L "$BACKUP" ]] || { echo "BLOCKED_NO_CADDY_BACKUP"; exit 2; }
  cmp -s "$HOST_CADDY" "$NEW_CONFIG" ||
    { echo "BLOCKED_PUBLIC_CADDY_MODIFIED_SINCE_ACTIVATION"; exit 2; }
  cat "$BACKUP" > "$HOST_CADDY"
  docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile
  echo "AWS_LOGIN_CADDY_ROLLBACK=PASS"
  echo "OLD_PREVIEW=UNCHANGED"
  exit 0
fi

echo "=== AWS SBI V150 LOGIN ACTIVATION ==="
[[ "$(docker inspect -f '{{.State.Running}}' "$LOGIN" 2>/dev/null)" == true ]] ||
  { echo "BLOCKED_LOGIN_STAGE_NOT_RUNNING"; exit 2; }
[[ "$(docker inspect -f '{{.Config.Image}}' "$LOGIN")" == "$IMAGE" ]] ||
  { echo "BLOCKED_LOGIN_STAGE_NOT_PINNED_IMAGE"; exit 2; }
check_auth_config
check_login
cmp -s "$HOST_CADDY" "$OLD_CONFIG" ||
  { echo "BLOCKED_EXISTING_CADDY_HAS_CUSTOM_CHANGES"; exit 2; }
[[ ! -e "$BACKUP" ]] || { echo "BLOCKED_CADDY_BACKUP_ALREADY_EXISTS"; exit 2; }
docker exec -i "$PROXY" caddy adapt --config /dev/stdin --adapter caddyfile --validate < "$NEW_CONFIG" >/dev/null ||
  { echo "BLOCKED_NEW_CADDY_SYNTAX"; exit 2; }
cp -- "$HOST_CADDY" "$BACKUP"
chmod 600 "$BACKUP"
chown root:root "$BACKUP"
MUTATED=1
restore() {
  if [[ "$MUTATED" == 1 ]]; then
    cat "$BACKUP" > "$HOST_CADDY" || true
    docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
    echo "LOGIN_ROUTE_AUTOMATIC_ROLLBACK=ATTEMPTED"
  fi
}
trap restore EXIT
cat "$NEW_CONFIG" > "$HOST_CADDY"
docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile
status() {
  curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$PUBLIC$1" || true
}
[[ "$(status /login)" == 200 ]] || { echo "PUBLIC_LOGIN_HTTP_NOT_200"; exit 2; }
[[ "$(status /)" == 303 ]] || { echo "PUBLIC_ROOT_NOT_REDIRECT_TO_LOGIN"; exit 2; }
[[ "$(status /pipeline)" == 401 ]] ||
  { echo "LEGACY_PIPELINE_LOGIN_GUARD_CHANGED"; exit 2; }
[[ "$(status /auth/config)" == 200 ]] || { echo "PUBLIC_FIREBASE_CONFIG_MISSING"; exit 2; }
check_existing || { echo "EXISTING_IMAGE_PARITY=FAIL"; exit 2; }
MUTATED=0
trap - EXIT
echo "AWS_LOGIN_V150_PUBLIC_ROUTE=ACTIVE"
echo "AWS_LOGIN_URL=$PUBLIC/login"
echo "PIPELINE_PREVIEW=UNCHANGED_BASIC_AUTH"
echo "REAL_FIREBASE_LOGIN=REQUIRES_USER_BROWSER_TEST"
echo "REPORTS_AND_IMPORTS=DISABLED"
echo "FINANCIAL_WRITES=DISABLED"
echo "PRODUCTION_FINANCIAL_CUTOVER=BLOCKED"
