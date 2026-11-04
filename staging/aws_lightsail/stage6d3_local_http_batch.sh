#!/usr/bin/env bash
# Stage 6D.3: isolated localhost HTTP combined QA. No published ports or network.
# Owner authorization: temporary container only. Never modifies existing services.
set -u
IMAGE="${1:-sbi-stage6d-candidate:c949777ffa32}"
NAME="sbi-stage6d-http-$$"
finish() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap finish EXIT INT TERM
blocked() {
  echo "$1=BLOCKED"
  echo "BATCH_QA=BLOCKED"
  echo "NEXT_GATE=$2"
  exit 2
}
if ! command -v docker >/dev/null 2>&1; then
  blocked "DOCKER_ACCESS" "CHECK_EXISTING_DOCKER_ACCESS"
fi
if ! docker info >/dev/null 2>&1; then
  blocked "DOCKER_ACCESS" "CHECK_EXISTING_DOCKER_ACCESS"
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  blocked "IMAGE_AVAILABLE" "VERIFY_APPROVED_STAGE6D_IMAGE"
fi
echo "IMAGE_AVAILABLE=PASS"
# Hard stop for source images from another stage (no unrestricted runtime).
if [ "$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "sbi.release.status"}}')" != "PRIVATE_AUTH_SHELL_ONLY_FINANCIAL_DISABLED" ]; then
  blocked "PRIVATE_IMAGE_LABEL" "USE_APPROVED_STAGE6D_IMAGE"
fi
echo "PRIVATE_IMAGE_LABEL=PASS"
# Name is per-run unique, no auto-restart, no host port, no bridge network or secrets.
if ! docker run -d --name "$NAME" --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 256m \
  --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  --env SBI_STAGE6_AUTH_PROFILE=aws-private-staging \
  --env SBI_STAGE6_AWS_ORIGIN=https://sbi-stage6.13-232-241-221.sslip.io \
  --env SBI_STAGE6_PRIVATE_ONLY=1 \
  --env SBI_STAGE6_FINANCIAL_EXECUTION=disabled \
  --env SBI_STAGE6_BACKEND_CONNECTED=false \
  "$IMAGE" >/dev/null; then
    echo "CONTAINER_START=FAIL"
    echo "BATCH_QA=FAIL"
    echo "NEXT_GATE=REVIEW_LOCAL_IMAGE_RUNTIME"
    exit 1
fi
echo "CONTAINER_START=PASS"
# Inspect only this uniquely named container; no existing services are touched.
network="$(docker inspect "$NAME" --format '{{.HostConfig.NetworkMode}}' 2>/dev/null || true)"
ports="$(docker inspect "$NAME" --format '{{json .HostConfig.PortBindings}}' 2>/dev/null || true)"
if [ "$network" != "none" ] || { [ "$ports" != "{}" ] && [ "$ports" != "null" ]; }; then
  echo "NO_PUBLIC_NETWORK=FAIL"
  echo "BATCH_QA=FAIL"
  echo "NEXT_GATE=REVIEW_ISOLATION"
  exit 1
fi
echo "NO_PUBLIC_NETWORK=PASS"
# Probe the HTTP listener from *inside* the network-none container. No host ports.
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if docker exec "$NAME" python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/login",timeout=2).close()' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "LOCAL_HTTP_READY=FAIL"
  echo "BATCH_QA=FAIL"
  echo "NEXT_GATE=REVIEW_CANDIDATE_STARTUP_WITHOUT_CHANGING_LIVE_SERVICES"
  exit 1
fi
echo "LOCAL_HTTP_READY=PASS"
docker exec -i "$NAME" python3 - <<'PY'
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

open_no_redirect = build_opener(NoRedirect())
failed = []
def case(name, path, expected, method="GET", headers=None, body=None, verify=None):
    url = "http://127.0.0.1:8080"+path
    req = Request(url,data=body,headers=headers or {},method=method)
    try:
        response = open_no_redirect.open(req,timeout=5)
    except HTTPError as e:
        response = e
    except Exception:
        print(name+"=FAIL")
        failed.append(name)
        return
    try:
        content = response.read(8192)
        ok = response.status == expected
        if verify:
            ok = ok and verify(response,content)
    except Exception:
        ok = False
    finally:
        response.close()
    print(name+"="+("PASS" if ok else "FAIL"))
    if not ok:
        failed.append(name)

case("ANONYMOUS_ROOT_REDIRECT","/",303,verify=lambda r,b:r.headers.get("Location","").endswith("/login"))
case("LOGIN_PAGE_LOCAL_HTTP","/login",200,verify=lambda r,b:b"login" in b.lower() and "default-src 'none'" in r.headers.get("Content-Security-Policy",""))
case("LOGIN_JS","/login.js",200)
case("ANONYMOUS_DASHBOARD_DENIED","/dashboard.js",401)
case("CSRF_COOKIE_SECURE","/auth/csrf",200,verify=lambda r,b:"Secure" in r.headers.get("Set-Cookie","") and "HttpOnly" in r.headers.get("Set-Cookie","") and "csrf_token" in json.loads(b))
case("UNTRUSTED_POST_ORIGIN_DENIED","/auth/session",403,method="POST",headers={"Origin":"https://untrusted.example","Content-Type":"application/json"},body=b'{"idToken":"fake"}')
case("TRUSTED_ORIGIN_WITHOUT_CSRF_DENIED","/auth/session",403,method="POST",headers={"Origin":"https://sbi-stage6.13-232-241-221.sslip.io","Content-Type":"application/json"},body=b'{"idToken":"fake"}')
case("FINANCIAL_MONITORING_DENIED","/api/health",503)
case("FINANCIAL_REPORT_DENIED","/reports/credit-note.csv",503)
case("IMPORT_API_DENIED","/api/imports/preview",503)
case("FIREBASE_CONFIG_UNSET","/auth/config",503)
print("FIREBASE_REAL_LOGIN=NOT_TESTED")
print("FINANCIAL_DATABASE=NOT_CONNECTED")
print("HOST_PUBLIC_PORTS=NONE")
print("BATCH_QA="+("FAIL" if failed else "PASS"))
print("NEXT_GATE="+("REVIEW_STAGE6D_HTTP_FAILURE" if failed else "DESIGN_APPROVED_LIGHTSAIL_KEYLESS_FIREBASE_IDENTITY"))
sys.exit(1 if failed else 0)
PY
result=$?
exit "$result"
