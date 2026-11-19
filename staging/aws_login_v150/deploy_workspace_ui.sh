#!/usr/bin/env bash
# Blue/green professional SBI UI and personal workspace: stage|activate|rollback FULL_SHA.
# Leaves prior Firebase login and existing /pipeline preview running for rollback.
set -Eeuo pipefail
umask 077
[[ $# -eq 2 && "$1" =~ ^(stage|activate|rollback)$ && "$2" =~ ^[a-f0-9]{40}$ ]] ||
  { echo "USAGE=stage|activate|rollback FULL_REVIEWED_SHA"; exit 2; }
MODE="$1"
SHA="$2"
SHORT="$(printf '%.12s' "$SHA")"
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
[[ "$(id -u)" == 0 ]] || { echo "BLOCKED_SUDO_REQUIRED"; exit 2; }
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] ||
  { echo "BLOCKED_SOURCE_SHA_CHANGED"; exit 2; }
git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_workspace_ui.sh" |
  cmp -s - "$0" || { echo "BLOCKED_DEPLOY_SCRIPT_CHANGED"; exit 2; }
exec 9>/run/lock/sbi-aws-workspace.lock
flock -n 9 || { echo "BLOCKED_CONCURRENT_CONTROL_TOWER_DEPLOY"; exit 2; }

OLD="aws_lightsail-sbi-preview-1"
PROXY="aws_lightsail-caddy-1"
PREV=""
NEW="sbi-login-workspace-stage"
IMAGE="sbi-aws-workspace:$SHORT"
CONF="/etc/sbi-aws-login-v150"
ENVFILE="$CONF/login.env"
ADMIN="$CONF/firebase-service-account.json"
BASELINE=""
CANDIDATE="$ROOT/staging/aws_login_v150/Caddyfile.workspace"
BACKUP="$CONF/Caddyfile.before-workspace"
PUBLIC="https://sbi-preview.13-232-241-221.sslip.io"
WORKSPACE_DIR="/var/lib/sbi-control-tower-workspace"
HOST_CADDY="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$PROXY")"
[[ -n "$HOST_CADDY" && -f "$HOST_CADDY" && ! -L "$HOST_CADDY" ]] ||
  { echo "BLOCKED_CADDY_BIND_FILE"; exit 2; }
# Detect the actual installed Control Tower release; fail if custom-modified.
if cmp -s "$HOST_CADDY" "$ROOT/staging/aws_login_v150/Caddyfile.control_tower_tab"; then
  PREV="sbi-login-control-tower-tab-stage"
  BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.control_tower_tab"
elif cmp -s "$HOST_CADDY" "$ROOT/staging/aws_login_v150/Caddyfile.control_tower"; then
  PREV="sbi-login-control-tower-stage"
  BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.control_tower"
else
  echo "BLOCKED_UNRECOGNIZED_LIVE_CADDY_BASELINE"
  exit 2
fi
echo "VERIFIED_BASELINE_CONTAINER=$PREV"

for c in "$OLD" "$PROXY" "$PREV"; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" == true ]] ||
    { echo "BLOCKED_EXISTING_CONTAINER_NOT_RUNNING=$c"; exit 2; }
done
OLD_IMAGE="$(docker inspect -f '{{.Image}}' "$OLD")"
PROXY_IMAGE="$(docker inspect -f '{{.Image}}' "$PROXY")"
PREV_IMAGE="$(docker inspect -f '{{.Image}}' "$PREV")"
check_images() {
  [[ "$(docker inspect -f '{{.Image}}' "$OLD")" == "$OLD_IMAGE" &&
     "$(docker inspect -f '{{.Image}}' "$PROXY")" == "$PROXY_IMAGE" &&
     "$(docker inspect -f '{{.Image}}' "$PREV")" == "$PREV_IMAGE" ]]
}
check_credentials() {
  [[ -f "$ENVFILE" && ! -L "$ENVFILE" &&
     "$(stat -c '%u:%a' "$ENVFILE")" == "0:600" ]] ||
    { echo "BLOCKED_PRIVATE_FIREBASE_ENV"; exit 2; }
  [[ -f "$ADMIN" && ! -L "$ADMIN" &&
     "$(stat -c '%u:%g:%a' "$ADMIN")" == "0:10001:440" ]] ||
    { echo "BLOCKED_PRIVATE_FIREBASE_ADMIN"; exit 2; }
}
shared_network() {
  local a b n
  a="$(docker inspect -f '{{range $name,$value := .NetworkSettings.Networks}}{{$name}} {{end}}' "$PREV")"
  b="$(docker inspect -f '{{range $name,$value := .NetworkSettings.Networks}}{{$name}} {{end}}' "$PROXY")"
  for n in $a; do
    if [[ " $b " == *" $n "* && "$n" != bridge && "$n" != host && "$n" != none ]]; then
      echo "$n"; return 0
    fi
  done
  return 1
}
check_stage() {
  docker exec -i "$NEW" python3 - <<'PY'
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
opener=build_opener(NoRedirect())
def status(path):
    try:
        return opener.open(Request("http://127.0.0.1:8080"+path),timeout=5).status
    except HTTPError as error:
        return error.code
for path,expected in (
    ("/healthz",200),("/login",200),("/",303),
    ("/control-tower",401),("/control-tower/api/pipeline/status",401),
    ("/control-tower/api/pipeline/history.csv",401),
    ("/control-tower/api/workspace",401),
    ("/dashboard-theme.css",401),
    ("/control-tower/theme.css",401),
    ("/api/reports",401),
):
    actual=status(path)
    assert actual==expected,(path,actual,expected)
print("SBI_WORKSPACE_PRIVATE_HTTP=PASS")
print("REAL_FIREBASE_SIGNIN=REQUIRES_BROWSER_TEST")
PY
}

if [[ "$MODE" == stage ]]; then
  echo "=== SBI PROFESSIONAL WORKSPACE STAGING ==="
  check_credentials
  install -d -o 10001 -g 10001 -m 700 "$WORKSPACE_DIR"
  [[ "$(stat -c '%u:%g:%a' "$WORKSPACE_DIR")" == "10001:10001:700" ]] ||
    { echo "BLOCKED_WORKSPACE_DIR_PERMISSIONS"; exit 2; }
  NET="$(shared_network)" || { echo "BLOCKED_NO_SHARED_CADDY_NETWORK"; exit 2; }
  if docker inspect "$NEW" >/dev/null 2>&1; then
    echo "BLOCKED_CONTROL_TOWER_STAGE_ALREADY_EXISTS"; exit 2
  fi
  docker build -f "$ROOT/staging/aws_login_v150/Dockerfile" \
    --build-arg SBI_SOURCE_SHA="$SHA" -t "$IMAGE" "$ROOT"
  [[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" == "$SHA" ]] ||
    { echo "BLOCKED_IMAGE_SHA_LABEL"; exit 2; }
  docker run -d --name "$NEW" --restart unless-stopped \
    --network "$NET" --network-alias sbi-login-workspace \
    --user 10001:10001 --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 128 --memory 384m \
    --env-file "$ENVFILE" \
    -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-service-account.json \
    -e SBI_PRIVATE_WORKSPACE_DB=/data/workspace.sqlite3 \
    --mount "type=bind,src=$WORKSPACE_DIR,dst=/data" \
    --mount "type=bind,src=$ADMIN,dst=/run/secrets/firebase-service-account.json,readonly" \
    "$IMAGE" >/dev/null
  for i in $(seq 1 20); do
    if docker exec "$NEW" python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! check_stage; then
    docker rm -f "$NEW" >/dev/null 2>&1 || true
    echo "CONTROL_TOWER_STAGE=FAILED_CLEANED_UP"
    exit 2
  fi
  check_images || { echo "BLOCKED_ORIGINAL_IMAGE_PARITY"; exit 2; }
  echo "SBI_WORKSPACE_STAGE=PASS"
  echo "PUBLIC_AWS_ROUTE=UNCHANGED"
  echo "LEGACY_PIPELINE=UNCHANGED"
  echo "NEXT=ACTIVATE_AFTER_REVIEW"
  exit 0
fi

if [[ "$MODE" == rollback ]]; then
  [[ -f "$BACKUP" && ! -L "$BACKUP" ]] || { echo "BLOCKED_NO_CONTROL_TOWER_BACKUP"; exit 2; }
  cmp -s "$HOST_CADDY" "$CANDIDATE" ||
    { echo "BLOCKED_CONFIG_CHANGED_AFTER_TOWER_ACTIVATION"; exit 2; }
  cat "$BACKUP" > "$HOST_CADDY"
  docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile
  echo "SBI_WORKSPACE_CADDY_ROLLBACK=PASS"
  echo "PREVIOUS_FIREBASE_LOGIN=RESTORED"
  exit 0
fi

echo "=== SBI PROFESSIONAL WORKSPACE ACTIVATION ==="
check_credentials
[[ "$(docker inspect -f '{{.State.Running}}' "$NEW" 2>/dev/null)" == true ]] ||
  { echo "BLOCKED_TOWER_STAGE_NOT_RUNNING"; exit 2; }
[[ "$(docker inspect -f '{{.Config.Image}}' "$NEW")" == "$IMAGE" ]] ||
  { echo "BLOCKED_TOWER_IMAGE_NOT_PINNED"; exit 2; }
check_stage
cmp -s "$HOST_CADDY" "$BASELINE" ||
  { echo "BLOCKED_EXISTING_CADDY_CHANGED"; exit 2; }
[[ ! -e "$BACKUP" ]] || { echo "BLOCKED_EXISTING_TOWER_BACKUP"; exit 2; }
docker exec -i "$PROXY" caddy adapt --config /dev/stdin \
  --adapter caddyfile --validate < "$CANDIDATE" >/dev/null ||
  { echo "BLOCKED_TOWER_CADDY_SYNTAX"; exit 2; }
cp -- "$HOST_CADDY" "$BACKUP"
chmod 600 "$BACKUP"
chown root:root "$BACKUP"
CHANGED=1
restore() {
  if [[ "$CHANGED" == 1 ]]; then
    cat "$BACKUP" > "$HOST_CADDY" || true
    docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
    echo "SBI_WORKSPACE_ROLLBACK=ATTEMPTED"
  fi
}
trap restore EXIT
cat "$CANDIDATE" > "$HOST_CADDY"
docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile
status() { curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$PUBLIC$1" || true; }
for path in /login / /control-tower /control-tower/api/pipeline/status /pipeline /auth/config; do
  case "$path" in
    /login|/auth/config) expected=200 ;;
    /) expected=303 ;;
    *) expected=401 ;;
  esac
  actual="$(status "$path")"
  [[ "$actual" == "$expected" ]] ||
    { echo "PUBLIC_TOWER_ROUTE_FAILED=$path STATUS=$actual"; exit 2; }
done
check_images || { echo "BLOCKED_ORIGINAL_IMAGE_PARITY"; exit 2; }
CHANGED=0
trap - EXIT
echo "SBI_WORKSPACE_PUBLIC_ROUTE=ACTIVE"
echo "SBI_WORKSPACE_URL=$PUBLIC/dashboard"
echo "SAME_FIREBASE_LOGIN=ENABLED"
echo "LEGACY_PIPELINE=UNCHANGED_BASIC_AUTH"
echo "PRIVATE_NOTES_STORAGE=HOST_PERSISTENT_ENABLED"
echo "FINANCIAL_WRITES=DISABLED"
echo "PRODUCTION_FINANCIAL_CUTOVER=BLOCKED"
