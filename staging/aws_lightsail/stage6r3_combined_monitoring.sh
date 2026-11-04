#!/usr/bin/env bash
# Stage 6R.3 one-command private test of ORIGINAL read-only monitoring code.
# Reuses existing Stage 6R.2 local image; never connects Firebase or Firestore.
set -Eeuo pipefail
umask 077
repo="${1:?Expected local Git repository}"
commit="${2:?Expected pinned Stage 6R.3 Git commit}"
base="sbi-stage6r2-recovered:14115d966475"
image="sbi-stage6r3-original-static:${commit:0:12}"
temporary="$(mktemp -d /tmp/sbi-stage6r3.XXXXXXXX)"
container="sbi-stage6r3-test-$$"
cleanup() {
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  if [[ "$temporary" == /tmp/sbi-stage6r3.* && -d "$temporary" ]]; then
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
if ! git -C "$repo" cat-file -e "${commit}^{commit}" 2>/dev/null; then
  blocked "PINNED_SOURCE" "FETCH_PINNED_GITHUB_COMMIT"
fi
if ! git -C "$repo" archive "$commit" | tar -xf - -C "$temporary"; then
  failed "ARCHIVE" "CHECK_GITHUB_SOURCE_ARCHIVE"
fi
echo "PINNED_SOURCE=PASS"
if ! command -v docker >/dev/null 2>&1 || ! sudo docker info >/dev/null 2>&1; then
  blocked "DOCKER" "REVIEW_EXISTING_LIGHTSAIL_DOCKER_ACCESS"
fi
if ! sudo docker image inspect "$base" >/dev/null 2>&1; then
  blocked "RECOVERED_BACKEND_IMAGE" "VERIFY_STAGE6R2_COMPLETED_IMAGE"
fi
if [[ "$(sudo docker image inspect "$base" --format '{{index .Config.Labels "sbi.release.status"}}')" != "PRIVATE_RECOVERY_BACKEND_PACKAGE_ONLY_NO_FINANCE" ]]; then
  blocked "RECOVERED_BACKEND_RELEASE" "REVIEW_STAGE6R2_IMAGE_IDENTITY"
fi
echo "RECOVERED_BACKEND_IMAGE=PASS"
if ! sudo docker build --pull=false --network none -t "$image" \
  -f "$temporary/staging/aws_lightsail/Dockerfile.stage6r3" "$temporary" >/dev/null; then
  failed "ORIGINAL_MONITORING_BUILD" "REVIEW_STAGE6R3_OFFLINE_BUILD"
fi
echo "ORIGINAL_MONITORING_BUILD=PASS"
if [[ "$(sudo docker image inspect "$image" --format '{{.Config.User}}')" != "65534:65534" ]]; then
  failed "IMAGE_NONROOT" "REVIEW_NONROOT_RUNTIME"
fi
if [[ "$(sudo docker image inspect "$image" --format '{{index .Config.Labels "sbi.release.status"}}')" != "PRIVATE_ORIGINAL_STATIC_MONITORING_NO_FINANCE" ]]; then
  failed "IMAGE_PRIVATE_LABEL" "REVIEW_PRIVATE_RELEASE_GUARD"
fi
echo "IMAGE_NONROOT=PASS"
echo "IMAGE_PRIVATE_LABEL=PASS"
environment=(
  -e SBI_RECOVERY_PROFILE=lightsail-original-readonly-monitoring
  -e SBI_FINANCIAL_EXECUTION=disabled
  -e SBI_BACKEND_CONNECTED=false
  -e SBI_SOURCE_REVISION_PARITY=unverified
)
gate="$(sudo docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 128m \
  "${environment[@]}" "$image" --check 2>&1)" || failed "STARTUP_GATE" "REVIEW_PRIVATE_MONITORING_CONTRACT"
if [[ "$gate" != *"STAGE6R3_GATE=READY_PRIVATE_ORIGINAL_MONITOR_ONLY"* || "$gate" != *"ORIGINAL_MONITORING_CONTRACT=PASS"* ]]; then
  failed "STARTUP_GATE" "REVIEW_ORIGINAL_MAIN_SOURCE_CONTRACT"
fi
echo "STARTUP_GATE=PASS"
if ! sudo docker run -d --name "$container" --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 128m \
  --tmpfs /tmp:rw,nosuid,noexec,size=8m \
  "${environment[@]}" "$image" >/dev/null; then
  failed "TEMPORARY_CONTAINER" "REVIEW_STAGE6R3_START"
fi
echo "TEMPORARY_CONTAINER=PASS"
mode="$(sudo docker inspect "$container" --format '{{.HostConfig.NetworkMode}}' 2>/dev/null || true)"
ports="$(sudo docker inspect "$container" --format '{{json .HostConfig.PortBindings}}' 2>/dev/null || true)"
if [[ "$mode" != "none" || ( "$ports" != "{}" && "$ports" != "null" ) ]]; then
  failed "NETWORK_ISOLATION" "REVIEW_NETWORK_NONE_ENFORCEMENT"
fi
echo "NETWORK_ISOLATION=PASS"
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if sudo docker exec "$container" python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8082/healthz",timeout=1).close()' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  failed "LOCAL_HTTP_READY" "REVIEW_STATIC_MONITORING_LISTENER"
fi
echo "LOCAL_HTTP_READY=PASS"
if ! sudo docker exec -i "$container" python3 - <<'PY'
import json
from urllib import request, error
failed=[]
def check(name,path,expected,fields=None,method="GET"):
    req=request.Request("http://127.0.0.1:8082"+path,method=method)
    try:
        response=request.urlopen(req,timeout=2)
    except error.HTTPError as exc:
        response=exc
    except Exception:
        print(name+"=FAIL")
        failed.append(name)
        return
    with response:
        payload=json.loads(response.read(8192))
        ok=response.status==expected and (fields is None or all(payload.get(k)==v for k,v in fields.items()))
    print(name+"="+("PASS" if ok else "FAIL"))
    if not ok:
        failed.append(name)
check("SOURCE_HEALTHZ","/healthz",200,{"financial_database":"NOT_CONNECTED","financial_execution":False})
check("ORIGINAL_HEALTH","/health",200,{"financial_execution_enabled":False,"project":"meghraj-reconciliation"})
check("ORIGINAL_QA","/qa",200,{"production_release":"BLOCKED","data_source":"STATIC_BASELINE"})
check("ORIGINAL_SUPERVISOR","/supervisor",200,{"financial_engine":"NOT_DEPLOYED","monitoring_mode":"STATIC_BASELINE"})
check("ORIGINAL_AGENTS","/agents",200,{"live_agent_connection":False,"data_source":"DEMONSTRATION_ONLY"})
for name,path,method in [
    ("REPORTS_DENIED","/reports","GET"),
    ("CREDIT_NOTE_DENIED","/reports/credit-note.csv","GET"),
    ("IMPORT_PREVIEW_DENIED","/imports/preview","POST"),
    ("IMPORT_APPLY_DENIED","/imports/receipt/apply","POST"),
    ("UPLOAD_DENIED","/upload","POST"),
    ("USER_ADMIN_DENIED","/api/admin/users","POST"),
    ("MONITORING_FEED_DENIED","/monitoring-feed","GET"),
    ("ROOT_DENIED","/","GET"),
    ("HEALTH_MUTATION_DENIED","/health","POST")]:
    check(name,path,503,method=method)
print("REAL_FIREBASE_LOGIN=NOT_TESTED")
print("GCP_FIRESTORE_DATA=NOT_CONNECTED")
print("ORIGINAL_SOURCE_PARITY=NOT_VERIFIED")
print("PRIVATE_HTTP_BATCH="+("FAIL" if failed else "PASS"))
raise SystemExit(1 if failed else 0)
PY
then
  failed "PRIVATE_HTTP_BATCH" "REVIEW_STATIC_MONITORING_TEST_FAILURE"
fi
sudo docker rm -f "$container" >/dev/null 2>&1 || failed "TEMPORARY_CLEANUP" "REMOVE_STAGE6R3_TEST_CONTAINER_ONLY"
if sudo docker inspect "$container" >/dev/null 2>&1; then
  failed "TEMPORARY_CLEANUP" "REMOVE_STAGE6R3_TEST_CONTAINER_ONLY"
fi
echo "TEMPORARY_CLEANUP=PASS"
echo "BATCH_QA=PASS"
echo "NEXT_GATE=RECOVER_GCP_FIRESTORE_EXPORT_AND_FIREBASE_TRUST_SEPARATELY"
