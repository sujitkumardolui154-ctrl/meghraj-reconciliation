#!/usr/bin/env bash
# Stage 6R.2: one-time private backend-package candidate and no-finance HTTP QA.
# No public ports, no cloud account credentials, no existing services changed.
set -Eeuo pipefail
umask 077
repo="${1:?Expected local Git working repository}"
commit="${2:?Expected pinned migration commit SHA}"
recovered="${3:?Expected existing recovered source directory}"
base="sbi-stage6d-candidate:c949777ffa32"
temporary="$(mktemp -d /tmp/sbi-stage6r2.XXXXXXXX)"
container="sbi-stage6r2-check-$$"
cleanup() {
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  if [[ "$temporary" == /tmp/sbi-stage6r2.* && -d "$temporary" ]]; then
    rm -rf -- "$temporary"
  fi
}
trap cleanup EXIT INT TERM
blocked() {
  echo "$1=BLOCKED"
  echo "BATCH_QA=BLOCKED"
  echo "NEXT_GATE=$2"
  exit 2
}
failed() {
  echo "$1=FAIL"
  echo "BATCH_QA=FAIL"
  echo "NEXT_GATE=$2"
  exit 1
}
if [[ ! -f "$recovered/backend_source/main.py" || ! -f "$recovered/dashboard_source/production_gateway.py" ]]; then
  blocked "RECOVERED_SOURCE" "VERIFY_EXISTING_RECOVERY_LOCATION"
fi
echo "RECOVERED_SOURCE=PASS"
if ! git -C "$repo" cat-file -e "${commit}^{commit}" 2>/dev/null; then
  blocked "PINNED_GITHUB_SOURCE" "FETCH_APPROVED_SOURCE_COMMIT"
fi
if ! git -C "$repo" archive "$commit" | tar -xf - -C "$temporary"; then
  failed "ARCHIVE_SOURCE" "REVIEW_PINNED_SOURCE_EXPORT"
fi
echo "ARCHIVE_SOURCE=PASS"
if ! command -v docker >/dev/null 2>&1 || ! sudo docker info >/dev/null 2>&1; then
  blocked "DOCKER_ACCESS" "VERIFY_EXISTING_LIGHTSAIL_DOCKER"
fi
if ! sudo docker image inspect "$base" >/dev/null 2>&1; then
  blocked "BASE_IMAGE" "VERIFY_PREVIOUSLY_APPROVED_STAGE6D_IMAGE"
fi
if [[ "$(sudo docker image inspect "$base" --format '{{index .Config.Labels "sbi.release.status"}}')" != "PRIVATE_AUTH_SHELL_ONLY_FINANCIAL_DISABLED" ]]; then
  blocked "BASE_IMAGE_LABEL" "REVIEW_SOURCE_AND_IMAGE_IDENTITY"
fi
echo "BASE_IMAGE=PASS"
image="sbi-stage6r2-recovered:${commit:0:12}"
if ! sudo docker build --pull=false --network none \
  -t "$image" \
  -f "$temporary/staging/aws_lightsail/Dockerfile.stage6r2" "$temporary" >/dev/null; then
  failed "PRIVATE_BACKEND_BUILD" "REVIEW_OFFLINE_IMAGE_BUILD_FAILURE"
fi
echo "PRIVATE_BACKEND_BUILD=PASS"
if [[ "$(sudo docker image inspect "$image" --format '{{.Config.User}}')" != "65534:65534" ]]; then
  failed "BACKEND_NON_ROOT" "REVIEW_BACKEND_CONTAINER_PERMISSIONS"
fi
if [[ "$(sudo docker image inspect "$image" --format '{{index .Config.Labels "sbi.release.status"}}')" != "PRIVATE_RECOVERY_BACKEND_PACKAGE_ONLY_NO_FINANCE" ]]; then
  failed "BACKEND_RELEASE_LABEL" "REVIEW_BACKEND_RELEASE_GUARD"
fi
echo "BACKEND_NON_ROOT=PASS"
echo "BACKEND_RELEASE_LABEL=PASS"
check="$(sudo docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 128m \
  -e SBI_RECOVERY_PROFILE=lightsail-isolated-no-finance \
  -e SBI_FINANCIAL_EXECUTION=disabled -e SBI_BACKEND_CONNECTED=false \
  "$image" --check 2>&1)" || failed "STARTUP_GUARD" "REVIEW_BACKEND_SOURCE_GUARD"
if [[ "$check" != *"STAGE6R2_PACKAGE_GATE=READY_INERT_BACKEND_PACKAGE"* || "$check" != *"LIVE_DATABASE=NOT_CONNECTED"* ]]; then
  failed "STARTUP_GUARD" "REVIEW_BACKEND_SOURCE_GUARD"
fi
echo "STARTUP_GUARD=PASS"
if ! sudo docker run -d --name "$container" --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 128m \
  --tmpfs /tmp:rw,nosuid,noexec,size=8m \
  -e SBI_RECOVERY_PROFILE=lightsail-isolated-no-finance \
  -e SBI_FINANCIAL_EXECUTION=disabled -e SBI_BACKEND_CONNECTED=false \
  "$image" >/dev/null; then
  failed "CONTAINER_START" "REVIEW_PRIVATE_BACKEND_STARTUP"
fi
echo "CONTAINER_START=PASS"
mode="$(sudo docker inspect "$container" --format '{{.HostConfig.NetworkMode}}' 2>/dev/null || true)"
ports="$(sudo docker inspect "$container" --format '{{json .HostConfig.PortBindings}}' 2>/dev/null || true)"
if [[ "$mode" != "none" || ( "$ports" != "{}" && "$ports" != "null" ) ]]; then
  failed "NETWORK_ISOLATION" "REVIEW_PRIVATE_NETWORK_AND_PORTS"
fi
echo "NETWORK_ISOLATION=PASS"
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if sudo docker exec "$container" python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8081/healthz",timeout=1).close()' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  failed "PRIVATE_LOOPBACK_HTTP" "REVIEW_BACKEND_SHELL_STARTUP"
fi
echo "PRIVATE_LOOPBACK_HTTP=PASS"
if ! sudo docker exec -i "$container" python3 - <<'PY'
import json
from urllib import request, error
failed=[]
def check(name,path,method,expected,verify=None):
    req=request.Request("http://127.0.0.1:8081"+path,method=method)
    try:
        resp=request.urlopen(req,timeout=2)
    except error.HTTPError as exc:
        resp=exc
    except Exception:
        print(name+"=FAIL")
        failed.append(name)
        return
    with resp:
        data=resp.read(4096)
        good=(resp.status==expected)
        if verify is not None:
            good=good and verify(data)
    print(name+"="+("PASS" if good else "FAIL"))
    if not good:
        failed.append(name)
check("STATIC_HEALTH_NO_FINANCE","/healthz","GET",200,
      lambda data: (lambda p: p.get("financial_execution") is False and
                    p.get("backend_connected") is False and
                    p.get("live_database")=="NOT_CONNECTED")(json.loads(data)))
for name,path,method in [
    ("REPORTS_DENIED","/reports","GET"),
    ("CREDIT_NOTE_DENIED","/reports/credit-note.csv","GET"),
    ("IMPORT_PREVIEW_DENIED","/imports/preview","POST"),
    ("IMPORT_APPLY_DENIED","/imports/test/apply","POST"),
    ("UPLOAD_DENIED","/upload","POST"),
    ("ADMIN_USERS_DENIED","/api/admin/users","POST"),
    ("MONITORING_DENIED","/monitoring-feed","GET")]:
    check(name,path,method,503)
print("FINANCIAL_DATABASE=NOT_CONNECTED")
print("FIREBASE_REAL_LOGIN=NOT_TESTED")
print("BACKEND_API_IMPLEMENTATION=NOT_CONNECTED")
print("HTTP_BATCH="+("FAIL" if failed else "PASS"))
raise SystemExit(1 if failed else 0)
PY
then
  failed "PRIVATE_HTTP_BATCH" "REVIEW_DENIAL_TEST_FAILURE"
fi
sudo docker rm -f "$container" >/dev/null 2>&1 || failed "CONTAINER_CLEANUP" "REMOVE_ONLY_NAMED_TEST_CONTAINER"
if sudo docker inspect "$container" >/dev/null 2>&1; then
  failed "CONTAINER_CLEANUP" "REMOVE_ONLY_NAMED_TEST_CONTAINER"
fi
echo "CONTAINER_CLEANUP=PASS"
echo "BATCH_QA=PASS"
echo "NEXT_GATE=AUTH_AND_GCP_DATA_RECOVERY_BEFORE_FINANCIAL_BACKEND_INTEGRATION"
