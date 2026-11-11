#!/usr/bin/env bash
# Synthetic Docker-only ingress integration test. No AWS, secrets or finance access.
set -Eeuo pipefail

[[ $# -eq 2 ]] || { echo 'Usage: test_localhost_ingress.sh BACKEND_IMAGE INGRESS_IMAGE'; exit 2; }
BACKEND_IMAGE="$1"
INGRESS_IMAGE="$2"
SUFFIX="$$"
BACKEND="sbi-readonly-qa-app-$SUFFIX"
INGRESS="sbi-readonly-qa-proxy-$SUFFIX"
PRIVATE_NET="sbi-readonly-qa-internal-$SUFFIX"
HOST_NET="sbi-readonly-qa-host-$SUFFIX"

cleanup() {
  docker rm -f "$INGRESS" "$BACKEND" >/dev/null 2>&1 || true
  docker network rm "$HOST_NET" "$PRIVATE_NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create --internal "$PRIVATE_NET" >/dev/null
docker network create --driver bridge "$HOST_NET" >/dev/null
docker run -d --name "$BACKEND" --restart no --network "$PRIVATE_NET" \
  --user 10001:10001 --read-only --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  --cap-drop ALL --security-opt no-new-privileges --memory 256m \
  -e SBI_AWS_REPORT_USERNAME=synthetic \
  -e SBI_AWS_REPORT_PASSWORD=synthetic-not-a-real-secret-long-pass \
  "$BACKEND_IMAGE" >/dev/null

docker create --name "$INGRESS" --restart no --network "$HOST_NET" \
  --user 10001:10001 --read-only \
  --tmpfs /etc/nginx/conf.d:rw,nosuid,noexec,size=1m,mode=1777 \
  --tmpfs /var/cache/nginx:rw,nosuid,noexec,size=4m,mode=1777 \
  --tmpfs /var/run:rw,nosuid,noexec,size=1m,mode=1777 \
  --tmpfs /tmp:rw,nosuid,noexec,size=4m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges --memory 128m \
  -p 127.0.0.1::8080 -e BACKEND_NAME="$BACKEND" "$INGRESS_IMAGE" >/dev/null
docker network connect "$PRIVATE_NET" "$INGRESS"
docker start "$INGRESS" >/dev/null

# The credentialed backend has only the private network and no published port.
[[ "$(docker inspect -f '{{len .NetworkSettings.Networks}}' "$BACKEND")" == 1 ]]
[[ -z "$(docker port "$BACKEND")" ]]
[[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$INGRESS")" == true ]]

MAPPING="$(docker port "$INGRESS" 8080/tcp)"
[[ "$MAPPING" =~ ^127\.0\.0\.1:[0-9]+$ ]] || {
  echo "INGRESS_PUBLISH=FAIL"; exit 1;
}
HOST_PORT="${MAPPING##*:}"
echo 'INGRESS_PUBLISH=LOOPBACK_ONLY'

for attempt in $(seq 1 20); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$HOST_PORT/healthz" || true)"
  [[ "$code" == 200 ]] && break
  sleep 1
done
if [[ "$code" != 200 ]]; then
  docker logs "$INGRESS" 2>&1 | tail -25
  echo "INGRESS_HEALTH=FAIL ($code)"
  exit 1
fi

assert_code() {
  local expected="$1" path="$2" actual
  actual="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$HOST_PORT$path")"
  [[ "$actual" == "$expected" ]] || {
    echo "INGRESS_CONTRACT=FAIL path=$path expected=$expected actual=$actual"; exit 1;
  }
}
assert_code 200 /healthz
assert_code 503 /readyz
assert_code 401 /reports
assert_code 403 /api/upload

auth_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 --user 'synthetic:synthetic-not-a-real-secret-long-pass' "http://127.0.0.1:$HOST_PORT/reports")"
[[ "$auth_code" == 503 ]] || { echo 'AUTHENTICATED_FAIL_CLOSED=FAIL'; exit 1; }
echo 'INGRESS_HTTP_CONTRACT=PASS'
echo 'AUTHENTICATED_FAIL_CLOSED=PASS'
echo 'SYNTHETIC_ONLY=TRUE'
echo 'FINANCIAL_DATA=NOT_CONNECTED'
