#!/usr/bin/env bash
# SBI staging-only release. Must run as authorized local operator, never from SSH forced-command.
# Does not touch Caddy, production compose, Firestore, or financial settings.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
IMAGE="sbi-agent-stage"
NAME="sbi-agent-stage"
PORT=18082
RELEASE="${1:-}"
[[ "$RELEASE" =~ ^[0-9a-f]{40}$ ]] || { echo "BLOCKED: expected full Git SHA"; exit 2; }
[[ "$(git rev-parse HEAD)" == "$RELEASE" ]] || { echo "BLOCKED: checkout SHA mismatch"; exit 2; }
[[ -f staging/railway_public/Dockerfile ]] || exit 2
mkdir -p "$HOME/sbi-agent-logs"
log="$HOME/sbi-agent-logs/staging-release-${RELEASE:0:12}.txt"
exec > >(tee -a "$log") 2>&1
echo "RELEASE_SHA=$RELEASE"
echo "FINANCIAL_WRITES=DISABLED"
# The known-good image must be saved before building the candidate.
old="$(sudo docker inspect "$NAME" --format '{{.Image}}' 2>/dev/null || true)"
[[ -n "$old" ]] || { echo "BLOCKED: existing staging not found"; exit 2; }
sudo docker image inspect "$old" >/dev/null
rollback="sbi-stage-rollback:${RELEASE:0:12}"
sudo docker tag "$old" "$rollback"
sudo docker image inspect "$rollback" >/dev/null
echo "ROLLBACK_IMAGE=$old"
candidate="sbi-stage-candidate:${RELEASE:0:12}"
sudo docker build --pull -t "$candidate" staging/railway_public
candidate_id="$(sudo docker image inspect "$candidate" --format '{{.Id}}')"
echo "CANDIDATE_IMAGE=$candidate_id"
# Test new image on separate loopback port; do not replace running staging until qualified.
probe="sbi-stage-probe-${RELEASE:0:12}"
cleanup() { sudo docker rm -f "$probe" >/dev/null 2>&1 || true; }
trap cleanup EXIT
sudo docker run -d --name "$probe" -p 127.0.0.1:18083:8080 -e PORT=8080 "$candidate" >/dev/null
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:18083/healthz >/dev/null; then break; fi
  sleep 1
done
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18083/healthz)" = 200
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18083/)" = 401
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18083/api/upload)" = 401
echo "PROBE_SECURITY=PASS"
# Replace only the isolated staging container; retain pinned rollback image.
cleanup
trap - EXIT
sudo docker rm -f "$NAME" >/dev/null
restore() {
 echo "STAGING_ROLLBACK_STARTED"
 sudo docker rm -f "$NAME" >/dev/null 2>&1 || true
 sudo docker run -d --name "$NAME" --restart unless-stopped -p 127.0.0.1:$PORT:8080 -e PORT=8080 "$rollback" >/dev/null
}
trap restore ERR
sudo docker run -d --name "$NAME" --restart unless-stopped -p 127.0.0.1:$PORT:8080 -e PORT=8080 "$candidate" >/dev/null
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:$PORT/healthz >/dev/null; then break; fi
  sleep 1
done
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/healthz)" = 200
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/)" = 401
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/api/upload)" = 401
trap - ERR
echo "STAGING_RELEASE=PASS"
echo "PRODUCTION_PREVIEW=UNMODIFIED"
