#!/usr/bin/env bash
# R30 private-host staging deployment: ONLY the isolated R29 candidate gateway.
# No public gateway/Caddy touch, no financial engine, no Finance certificate.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT/staging/aws_calculation_prescreen/compose.local.yml"
PROJECT="sbi-r30-calc-preview-staging"
SERVICE="sbi-calc-prescreen-staging"
PORT="18088"
MODE="${1:-}"
RELEASE_SHA="${2:-}"
SECRET_FILE="${SBI_R30_SECRET_FILE:-/etc/sbi-calc-prescreen/stage.env}"
OLD_REF=""
ROLLBACK_REF=""
SWAPPED=0

refuse() { echo "R30_REFUSED:$1" >&2; exit 2; }
require_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || refuse "REVIEWED_SHA_REQUIRED"; }
require_repo() {
  require_sha "$RELEASE_SHA"
  [[ -f "$COMPOSE" ]] || refuse "R29_COMPOSE_MISSING"
  [[ "$(git -c "safe.directory=$ROOT" -C "$ROOT" rev-parse HEAD)" == "$RELEASE_SHA" ]] || refuse "SOURCE_SHA_MISMATCH"
  command -v docker >/dev/null || refuse "DOCKER_NOT_AVAILABLE"
  docker compose version >/dev/null || refuse "DOCKER_COMPOSE_NOT_AVAILABLE"
  command -v curl >/dev/null || refuse "CURL_NOT_AVAILABLE"
  python3 - "$COMPOSE" <<'PY' || exit 2
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
required=(
    '127.0.0.1:18088:8080',
    'SBI_FINANCIAL_APPLY: LOCKED',
    'read_only: true',
    'cap_drop: [ALL]',
    'no-new-privileges:true',
    'sbi-calc-prescreen:${SBI_CALC_RELEASE_SHA:-unreleased}',
)
for marker in required:
    if marker not in s:
        raise SystemExit("R30_REFUSED:COMPOSE_ISOLATION_CONTRACT")
print("R30_COMPOSE_ISOLATION=PASS")
PY
}
validate_secrets() {
  [[ "$EUID" -eq 0 ]] || refuse "ROOT_ONLY_STAGE_ACCESS"
  python3 - "$SECRET_FILE" <<'PY' || refuse "PRIVATE_STAGING_SECRET_INVALID"
import os,re,stat,sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.is_absolute() or p.is_symlink():
    raise SystemExit(3)
s=p.stat()
if s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or not stat.S_ISREG(s.st_mode):
    raise SystemExit(3)
if p.parent.is_symlink() or (p.parent.stat().st_mode & 0o022):
    raise SystemExit(3)
b=p.read_bytes()
if not b or len(b)>1024 or b"\r" in b or b"\x00" in b:
    raise SystemExit(3)
lines=b.decode("utf-8").splitlines()
if len(lines)!=3 or any("=" not in line for line in lines):
    raise SystemExit(3)
values=dict(line.split("=",1) for line in lines)
if set(values)!={"SBI_CALC_PREVIEW_ENABLED","SBI_CALC_PREVIEW_USERNAME",
                 "SBI_CALC_PREVIEW_PASSWORD"}:
    raise SystemExit(3)
if values["SBI_CALC_PREVIEW_ENABLED"]!="true":
    raise SystemExit(3)
if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}",values["SBI_CALC_PREVIEW_USERNAME"]):
    raise SystemExit(3)
if not re.fullmatch(r"[A-Za-z0-9_.-]{24,128}",values["SBI_CALC_PREVIEW_PASSWORD"]):
    raise SystemExit(3)
print("R30_PRIVATE_STAGING_SECRETS=VALID_CONFIGURATION_PRESENT")
PY
}
compose() {
  SBI_CALC_RELEASE_SHA="$RELEASE_SHA" docker compose \
    --project-name "$PROJECT" --env-file "$SECRET_FILE" -f "$COMPOSE" "$@"
}
verify_live() {
  local h r d a
  h="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:$PORT/healthz")" || return 1
  r="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:$PORT/readyz")" || return 1
  d="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' -X POST "http://127.0.0.1:$PORT/database/update")" || return 1
  a="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/candidate-screen")" || return 1
  [[ "$h" == 200 && "$r" == 200 && "$d" == 403 && "$a" == 401 ]] || return 1
  curl --silent --show-error --max-time 5 "http://127.0.0.1:$PORT/healthz" |
    python3 -c 'import json,sys; p=json.load(sys.stdin); assert p["full_v251_v239_engine_connected"] is False; assert p["real_database_writes"]==0; assert p["financial_apply"]=="LOCKED"' || return 1
}
rollback() {
  local result=0
  trap - EXIT
  if [[ "$SWAPPED" == 1 ]]; then
    echo "R30_STAGE_HEALTH_FAILED_ROLLBACK_ATTEMPT" >&2
    if [[ -n "$OLD_REF" ]]; then
      local rollback_sha="${OLD_REF#sbi-calc-prescreen:}"
      if [[ "$rollback_sha" =~ ^[0-9a-f]{40}$ ]] &&
          docker image inspect "$ROLLBACK_REF" >/dev/null 2>&1; then
        docker tag "$ROLLBACK_REF" "$OLD_REF" || result=1
        RELEASE_SHA="$rollback_sha"
        compose up --detach --no-build --force-recreate "$SERVICE" || result=1
        verify_live || result=1
      else
        result=1
      fi
    else
      compose down --remove-orphans || result=1
    fi
  fi
  if [[ "$result" != 0 ]]; then echo "R30_ROLLBACK_FAILED_MANUAL_HOST_REVIEW" >&2; fi
}
require_repo
case "$MODE" in
  preflight)
    # Deliberately requires no credentials and makes no AWS/Docker changes.
    echo "R30_PREFLIGHT=PASS"
    echo "R30_STAGING_SERVICE=NOT_DEPLOYED_BY_PREFLIGHT"
    ;;
  status)
    local_result=0
    verify_live || local_result=1
    if [[ "$local_result" != 0 ]]; then refuse "STAGING_HEALTH_NOT_VERIFIED"; fi
    echo "R30_STAGING_PRESCREEN_READY=PASS"
    echo "R30_FULL_RECONCILIATION_ENGINE=NOT_CONNECTED"
    ;;
  stage)
    validate_secrets
    [[ "${SBI_R30_STAGE_SCOPE:-}" == "PRIVATE_LOOPBACK_ONLY" ]] ||
       refuse "EXPLICIT_PRIVATE_HOST_STAGE_SCOPE_REQUIRED"
    # Do not replace any unrelated service already bound to the staging port.
    old_container="$(compose ps -q "$SERVICE")"
    if [[ -n "$old_container" ]]; then
      OLD_REF="$(docker inspect --format '{{.Config.Image}}' "$old_container")"
      [[ "$OLD_REF" =~ ^sbi-calc-prescreen:[0-9a-f]{40}$ ]] ||
        refuse "UNKNOWN_EXISTING_STAGING_IMAGE"
      verify_live || refuse "EXISTING_STAGING_NOT_HEALTHY"
    else
      if (echo >/dev/tcp/127.0.0.1/$PORT) >/dev/null 2>&1; then
        refuse "PORT_18088_OCCUPIED_BY_UNRELATED_SERVICE"
      fi
    fi
    # Keep the old image manifest pinned BEFORE the same-SHA rebuild can
    # reassign its tag. Never depend on a container config digest as a tag.
    if [[ -n "$OLD_REF" ]]; then
      ROLLBACK_REF="sbi-calc-prescreen:rollback-$RELEASE_SHA"
      docker tag "$OLD_REF" "$ROLLBACK_REF"
    fi
    compose build --pull "$SERVICE"
    # Test *uncredentialed disabled* behavior without network access or host writes.
    docker run --rm --network none --read-only --cap-drop ALL \
      --security-opt no-new-privileges --user 10001:10001 \
      "sbi-calc-prescreen:$RELEASE_SHA" python -c \
      'from app import app; c=app.test_client(); assert c.get("/healthz").status_code==200; assert c.get("/readyz").status_code==503; assert c.post("/database/update").status_code==403'
    SWAPPED=1
    trap rollback EXIT
    compose up --detach --no-build --force-recreate "$SERVICE"
    passed=0
    for i in 1 2 3 4 5 6 7 8 9 10; do
      if verify_live; then passed=1; break; fi
      sleep 1
    done
    [[ "$passed" == 1 ]] || refuse "POST_STAGE_PROBES_FAILED"
    SWAPPED=0
    trap - EXIT
    if [[ -n "$ROLLBACK_REF" ]]; then
      docker image rm "$ROLLBACK_REF" >/dev/null 2>&1 || true
    fi
    echo "R30_PRIVATE_STAGING_DEPLOYMENT=PASS"
    echo "R30_RELEASE_SHA=$RELEASE_SHA"
    echo "R30_FULL_V251_V239_ENGINE=NOT_CONNECTED"
    echo "R30_FINANCIAL_APPLY=LOCKED"
    echo "R30_REAL_DATABASE_WRITES=0"
    ;;
  *) refuse "MODE_EXPECTED_PREFLIGHT_STATUS_OR_STAGE" ;;
esac
