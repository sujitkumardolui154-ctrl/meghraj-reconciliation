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
git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_bulk_reports_v1.sh" |
  cmp -s - "$0" || { echo "BLOCKED_DEPLOY_SCRIPT_CHANGED"; exit 2; }
exec 9>/run/lock/sbi-aws-bulk-reports-v1.lock
flock -n 9 || { echo "BLOCKED_CONCURRENT_CONTROL_TOWER_DEPLOY"; exit 2; }

OLD="aws_lightsail-sbi-preview-1"
PROXY="aws_lightsail-caddy-1"
PREV="sbi-source-reports-v1-stage"
NEW="sbi-bulk-reports-v1-stage"
IMAGE="sbi-aws-bulk-reports-v1:$SHORT"
CONF="/etc/sbi-aws-login-v150"
ENVFILE="$CONF/login.env"
ADMIN="$CONF/firebase-service-account.json"
BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.source_reports_v1"
CANDIDATE="$ROOT/staging/aws_login_v150/Caddyfile.bulk_reports_v1"
BACKUP="$CONF/Caddyfile.before-bulk-reports-v1"
PUBLIC="https://sbi-preview.13-232-241-221.sslip.io"
WORKSPACE_DIR="/var/lib/sbi-control-tower-workspace"
DB="$WORKSPACE_DIR/workspace.sqlite3"
EVIDENCE_DIR="/var/lib/sbi-payment-evidence-staging"
# Optional private report source. No report data is created or bundled here.
# A separate finance reviewer must approve the source manifest and pin.
REPORT_DIR="/var/lib/sbi-certified-report-snapshot"
REPORT_ENV="$CONF/certified-reports.env"

HOST_CADDY="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$PROXY")"
[[ -n "$HOST_CADDY" && -f "$HOST_CADDY" && ! -L "$HOST_CADDY" ]] ||
  { echo "BLOCKED_CADDY_BIND_FILE"; exit 2; }
# Fail closed if previous authenticated workspace or Caddy changes.
# Reuse exactly the existing private SQLite volume, never create a second DB.
if [[ "$MODE" == rollback ]]; then
  [[ -f "$BACKUP" && ! -L "$BACKUP" ]] ||
    { echo "BLOCKED_BULK_ROLLBACK_BACKUP_MISSING"; exit 2; }
  cmp -s "$BACKUP" "$BASELINE" ||
    { echo "BLOCKED_BULK_UNVERIFIED_BACKUP"; exit 2; }
else
  cmp -s "$HOST_CADDY" "$BASELINE" ||
    { echo "BLOCKED_UNRECOGNIZED_WORKSPACE_CADDY"; exit 2; }
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

report_config() {
  REPORT_OPTS=()
  if [[ ! -e "$REPORT_ENV" && ! -e "$REPORT_DIR" ]]; then
    echo "REPORT_DATA=NOT_CONNECTED"
    return 0
  fi
  [[ -f "$REPORT_ENV" && ! -L "$REPORT_ENV" &&
     "$(stat -c '%u:%a' "$REPORT_ENV")" == "0:600" ]] ||
    { echo "BLOCKED_REPORT_ENV_REQUIRED"; exit 2; }
  [[ -d "$REPORT_DIR" && ! -L "$REPORT_DIR" &&
     "$(stat -c '%u:%g:%a' "$REPORT_DIR")" == "0:10001:750" ]] ||
    { echo "BLOCKED_REPORT_PRIVATE_DIR"; exit 2; }
  python3 - "$REPORT_ENV" <<'PY'
import re,sys
from pathlib import Path
lines=Path(sys.argv[1]).read_text().splitlines()
keys={"SBI_AWS_REPORT_MANIFEST_SHA256",
      "SBI_AWS_APPROVED_53_HEADERS_SHA256"}
items={}
for line in lines:
    if "=" not in line:raise SystemExit("BLOCKED_REPORT_ENV_FORMAT")
    k,v=line.split("=",1)
    if k not in keys or k in items or not re.fullmatch(r"[a-f0-9]{64}",v):
        raise SystemExit("BLOCKED_REPORT_INDEPENDENT_PIN_REQUIRED")
    items[k]=v
if set(items)!=keys:
    raise SystemExit("BLOCKED_REPORT_ENV_INCOMPLETE")
PY
  for name in manifest.json unpaid.csv ok.csv error-value.csv balance-review.csv; do
    [[ -f "$REPORT_DIR/$name" && ! -L "$REPORT_DIR/$name" &&
       "$(stat -c '%u:%g:%a' "$REPORT_DIR/$name")" == "0:10001:440" ]] ||
      { echo "BLOCKED_PRIVATE_REPORT_FILE=$name"; exit 2; }
  done
  REPORT_OPTS=(--env-file "$REPORT_ENV"
    -e SBI_AWS_REPORT_SNAPSHOT_DIR=/report-snapshot
    --mount "type=bind,src=$REPORT_DIR,dst=/report-snapshot,readonly")
  echo "REPORT_DATA=PRIVATE_SOURCE_CONFIGURED"
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
    ("/api/payment-evidence/template",401),
    ("/api/payment-evidence/uploads",401),
    ("/api/payment-evidence/upload",401),
    ("/dashboard-theme.css",401),
    ("/control-tower/theme.css",401),
    ("/api/reports",401),
    ("/api/reporting/v2",401),
    ("/api/reporting/v2/unpaid.csv",401),
    ("/api/bulk-report/status",401),
    ("/api/bulk-report/generate",401),
):
    actual=status(path)
    assert actual==expected,(path,actual,expected)
print("SBI_BULK_REPORTS_PRIVATE_HTTP=PASS")
print("REAL_FIREBASE_SIGNIN=REQUIRES_BROWSER_TEST")
PY
  docker exec -i "$NEW" python3 - <<'PY'
import os
from aws_readonly_snapshot_reports import load_snapshot
if os.environ.get("SBI_AWS_REPORT_SNAPSHOT_DIR"):
    for kind in ("unpaid","ok","error-value","balance-review"):
        catalog,payload=load_snapshot(kind)
        assert kind in catalog["reports"] and payload is not None
        assert catalog["reports"][kind]["columns"]==53
        assert catalog["reconciliation_executed"] is False
    print("PRIVATE_SOURCE_REPORT_PARITY=PASS")
else:
    print("PRIVATE_SOURCE_REPORT_PARITY=NOT_CONNECTED_SAFE")
PY

  # Write only a tiny nonfinancial probe; never use live bank data for smoke tests.
  docker exec -i "$NEW" python3 - <<'PY'
import os, stat, tempfile
directory="/evidence"
info=os.stat(directory)
assert stat.S_ISDIR(info.st_mode)
assert info.st_uid==os.getuid()
assert stat.S_IMODE(info.st_mode)==0o700
fd,path=tempfile.mkstemp(prefix=".evidence-stage-check-",dir=directory)
try:
    os.write(fd,b"private-volume-ok")
finally:
    os.close(fd)
    os.unlink(path)
print("PAYMENT_EVIDENCE_PRIVATE_VOLUME_WRITE=PASS")
PY
}

if [[ "$MODE" == stage ]]; then
  echo "=== SBI AWS BULK REPORT STAGING ==="
  check_credentials
  # This release does not migrate or modify the existing notes/tasks DB.
  [[ -d "$WORKSPACE_DIR" && ! -L "$WORKSPACE_DIR" &&
     "$(stat -c '%u:%g:%a' "$WORKSPACE_DIR")" == "10001:10001:700" ]] ||
    { echo "BLOCKED_EXISTING_WORKSPACE_NOT_PRESERVED"; exit 2; }
  [[ ! -L "$EVIDENCE_DIR" ]] ||
    { echo "BLOCKED_EVIDENCE_VOLUME_IS_SYMLINK"; exit 2; }
  install -d -o 10001 -g 10001 -m 700 "$EVIDENCE_DIR"
  [[ -d "$EVIDENCE_DIR" && ! -L "$EVIDENCE_DIR" &&
     "$(stat -c '%u:%g:%a' "$EVIDENCE_DIR")" == "10001:10001:700" ]] ||
    { echo "BLOCKED_PRIVATE_EVIDENCE_PERMISSIONS"; exit 2; }
  echo "EXISTING_PERSONAL_TASK_DATABASE=UNMODIFIED"
  echo "PAYMENT_EVIDENCE_VOLUME=PRIVATE_UID_10001"
  report_config
  NET="$(shared_network)" || { echo "BLOCKED_NO_SHARED_CADDY_NETWORK"; exit 2; }
  if docker inspect "$NEW" >/dev/null 2>&1; then
    # A previous attempt may have completed staging before the shell exited.
    # Re-verify the EXACT pinned image, volume, and private route; never delete.
    [[ "$(docker inspect -f '{{.State.Running}}' "$NEW")" == true ]] ||
      { echo "BLOCKED_PREVIOUS_BULK_CANDIDATE_STOPPED"; exit 2; }
    [[ "$(docker inspect -f '{{.Config.Image}}' "$NEW")" == "$IMAGE" ]] ||
      { echo "BLOCKED_PREVIOUS_BULK_IMAGE_MISMATCH"; exit 2; }
    [[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" == "$SHA" ]] ||
      { echo "BLOCKED_PREVIOUS_BULK_SHA_MISMATCH"; exit 2; }
    ACTUAL_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/evidence"}}{{.Source}}{{end}}{{end}}' "$NEW")"
    [[ "$ACTUAL_VOLUME" == "$EVIDENCE_DIR" ]] ||
      { echo "BLOCKED_PREVIOUS_BULK_EVIDENCE_VOLUME_MISMATCH"; exit 2; }
    if [[ -e "$REPORT_ENV" ]]; then
      CURRENT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/report-snapshot"}}{{.Source}}{{end}}{{end}}' "$NEW")"
      [[ "$CURRENT" == "$REPORT_DIR" ]] || { echo "BLOCKED_EXISTING_REPORT_MOUNT_MISMATCH"; exit 2; }
    else
      CURRENT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/report-snapshot"}}{{.Source}}{{end}}{{end}}' "$NEW")"
      [[ -z "$CURRENT" ]] || { echo "BLOCKED_UNEXPECTED_EXISTING_REPORT_MOUNT"; exit 2; }
    fi
    check_stage
    check_images || { echo "BLOCKED_ORIGINAL_IMAGE_PARITY"; exit 2; }
    echo "SBI_BULK_REPORTS_STAGE=PASS"
    echo "EXISTING_CANDIDATE_VERIFIED=YES"
    echo "PUBLIC_AWS_ROUTE=UNCHANGED"
    exit 0
  fi
  docker build -f "$ROOT/staging/aws_login_v150/Dockerfile" \
    --build-arg SBI_SOURCE_SHA="$SHA" -t "$IMAGE" "$ROOT"
  [[ "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" == "$SHA" ]] ||
    { echo "BLOCKED_IMAGE_SHA_LABEL"; exit 2; }
  docker run -d --name "$NEW" --restart unless-stopped \
    --network "$NET" --network-alias sbi-bulk-reports-v1 \
    --user 10001:10001 --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 128 --memory 384m \
    --env-file "$ENVFILE" \
    -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-service-account.json \
    -e SBI_PRIVATE_WORKSPACE_DB=/data/workspace.sqlite3 \
    -e SBI_PAYMENT_EVIDENCE_DIR=/evidence \
    "${REPORT_OPTS[@]}" \
    --mount "type=bind,src=$EVIDENCE_DIR,dst=/evidence" \
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
    echo "SBI_BULK_REPORTS_STAGE=FAILED_CLEANED_UP"
    exit 2
  fi
  check_images || { echo "BLOCKED_ORIGINAL_IMAGE_PARITY"; exit 2; }
  echo "SBI_BULK_REPORTS_STAGE=PASS"
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
  echo "SBI_BULK_REPORTS_CADDY_ROLLBACK=PASS"
  echo "PREVIOUS_FIREBASE_LOGIN=RESTORED"
  exit 0
fi

echo "=== SBI AWS BULK REPORT ACTIVATION ==="
check_credentials
report_config
ACTUAL_REPORT_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/report-snapshot"}}{{.Source}}{{end}}{{end}}' "$NEW" 2>/dev/null || true)"
if [[ -e "$REPORT_ENV" ]]; then
  [[ "$ACTUAL_REPORT_MOUNT" == "$REPORT_DIR" ]] ||
    { echo "BLOCKED_STAGED_REPORT_VOLUME_NOT_MATCHING_APPROVED_SOURCE"; exit 2; }
else
  [[ -z "$ACTUAL_REPORT_MOUNT" ]] ||
    { echo "BLOCKED_STAGED_REPORT_SOURCE_UNEXPECTED"; exit 2; }
fi
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
    echo "SBI_BULK_REPORTS_ROLLBACK=ATTEMPTED"
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
echo "SBI_BULK_REPORTS_PUBLIC_ROUTE=ACTIVE"
echo "SBI_BULK_REPORTS_URL=$PUBLIC/dashboard"
echo "SAME_FIREBASE_LOGIN=ENABLED"
echo "LEGACY_PIPELINE=UNCHANGED_BASIC_AUTH"
echo "PRIVATE_NOTES_STORAGE=EXISTING_HOST_VOLUME_PRESERVED"
echo "REPORT_GATEWAY=READ_ONLY_CERTIFIED_SOURCE_ONLY"
echo "BULK_REPORT=ENABLED_SOURCE_ONLY_XLSX"
echo "BULK_REPORT_FINANCIAL_WRITES=DISABLED"
echo "SOURCE_REPORTS=REQUIRE_INDEPENDENT_CERTIFICATION"
echo "EVIDENCE_UPLOAD=ENABLED_FIXED_XLSX"
echo "EVIDENCE_STORAGE=PRIVATE_HOST_VOLUME"
echo "PAYMENT_RECONCILIATION=DISABLED"
echo "FINANCIAL_WRITES=DISABLED"
echo "PRODUCTION_FINANCIAL_CUTOVER=BLOCKED"
