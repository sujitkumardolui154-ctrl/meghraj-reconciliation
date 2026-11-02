#!/usr/bin/env bash
# Root-owned staging-only deployment executor. Exact no-argument sudoers entry.
# Reads one 40-character lowercase SHA from stdin; only origin/main is deployable.
set -Eeuo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
[[ $# -eq 0 ]] || { echo "ERROR: arguments are forbidden"; exit 2; }
IFS= read -r SHA || { echo "ERROR: release SHA missing"; exit 2; }
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: invalid release SHA"; exit 2; }
if IFS= read -r extra; then
  echo "ERROR: extra input rejected"; exit 2
fi
exec 9>/run/lock/sbi-stage-release.lock
flock -n 9 || { echo "BLOCKED: another release is running"; exit 2; }

NAME="sbi-agent-stage"
SRC="/var/lib/sbi-stage-release/source"
LOGDIR="/var/log/sbi-stage-release"
mkdir -p "$SRC" "$LOGDIR"
chmod 700 "$SRC" "$LOGDIR"
LOG="$LOGDIR/$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.log"
exec > >(tee -a "$LOG") 2>&1
echo "REQUESTED_RELEASE_SHA=$SHA"
echo "FINANCIAL_WRITES=DISABLED"
echo "DEPLOY_TARGET=ISOLATED_AWS_STAGING_ONLY"

if [[ ! -d "$SRC/.git" ]]; then
  git init -q "$SRC"
  git -C "$SRC" remote add origin "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git"
fi
[[ "$(git -C "$SRC" remote get-url origin)" == "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git" ]] || {
  echo "ERROR: unexpected repository origin"; exit 2;
}
git -C "$SRC" -c core.hooksPath=/dev/null fetch --no-tags --depth=1 origin refs/heads/main
ACTUAL="$(git -C "$SRC" rev-parse FETCH_HEAD)"
[[ "$ACTUAL" == "$SHA" ]] || { echo "BLOCKED: SHA must equal reviewed origin/main"; exit 2; }
git -C "$SRC" -c core.hooksPath=/dev/null checkout --force --detach "$SHA"
git -C "$SRC" clean -fdx
[[ -f "$SRC/staging/railway_public/Dockerfile" ]] || { echo "BLOCKED: expected Dockerfile missing"; exit 2; }

ORIGINAL="$(docker inspect "$NAME" --format '{{.Image}}' 2>/dev/null)"
docker image inspect "$ORIGINAL" >/dev/null
ROLLBACK="sbi-stage-rollback:${SHA:0:12}"
CANDIDATE="sbi-stage-candidate:${SHA:0:12}"
docker tag "$ORIGINAL" "$ROLLBACK"
docker image inspect "$ROLLBACK" >/dev/null
echo "ROLLBACK_IMAGE=$ORIGINAL"

# Limit candidate runtime privileges. No private volumes, financial credentials or AWS IAM.
docker build --pull -t "$CANDIDATE" "$SRC/staging/railway_public"
PROBE="sbi-stage-probe-${SHA:0:12}"
MUTATED=0
finished() {
  code=$?
  trap - EXIT
  docker rm -f "$PROBE" >/dev/null 2>&1 || true
  if (( code != 0 && MUTATED == 1 )); then
    echo "ROLLBACK_TRIGGERED=YES"
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    if docker run -d --name "$NAME" --restart unless-stopped --cap-drop ALL \
      --security-opt no-new-privileges --pids-limit 128 --memory 256m \
      -p 127.0.0.1:18082:8080 -e PORT=8080 "$ROLLBACK" >/dev/null &&
      wait_for_health 18082; then
      echo "ROLLBACK_RESULT=PASS"
    else
      echo "ROLLBACK_RESULT=FAIL"
    fi
  fi
  exit "$code"
}
wait_for_health() {
  local port="$1"
  local i
  for i in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then
      [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/")" == 401 ]] || return 1
      [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/upload")" == 401 ]] || return 1
      return 0
    fi
    sleep 1
  done
  return 1
}
trap finished EXIT
docker run -d --name "$PROBE" --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 256m -p 127.0.0.1:18083:8080 \
  -e PORT=8080 "$CANDIDATE" >/dev/null
wait_for_health 18083 || { echo "PROBE_GATE=FAIL"; exit 1; }
echo "PROBE_GATE=PASS"
docker rm -f "$PROBE" >/dev/null
MUTATED=1
docker rm -f "$NAME" >/dev/null
docker run -d --name "$NAME" --restart unless-stopped --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 256m \
  -p 127.0.0.1:18082:8080 -e PORT=8080 "$CANDIDATE" >/dev/null
wait_for_health 18082 || { echo "STAGING_HEALTH=FAIL"; exit 1; }
echo "STAGING_RELEASE=PASS"
echo "FINANCIAL_PRODUCTION=UNMODIFIED"
MUTATED=0
