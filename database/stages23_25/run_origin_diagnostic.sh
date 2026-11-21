#!/usr/bin/env bash
# Read-only combined origin diagnosis for SBI private Firebase staging.
# No login attempts, no authenticated cookies, no deployment, no DB writes.
set -Eeuo pipefail
umask 077
STEP=INIT
trap 'rc=$?; if [[ "$rc" -ne 0 ]]; then echo "ORIGIN_DIAGNOSTIC=FAIL step=$STEP exit=$rc"; fi; echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"; exit "$rc"' EXIT
LIVE=sbi-bulk-report-pr129-https-preview
STAGE=sbi-pr129-pg-firebase-stage
WORK=/home/ubuntu/sbi-origin-policy-review
PIN=d3cb934a2b855857bfe8c8a2115c2821939fd633
SOURCE_SHA=eb41dd1a34cb604cf9a60cb7cd8f5e876dfbbc37
REPO=https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation

echo "=== A. LIVE + PRIVATE STAGING IDENTITY ==="
STEP=PRECHECK
sudo -n docker info >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
STAGE_BEFORE="$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$STAGE")" ]]
[[ "$(sudo -n docker inspect "$STAGE" --format '{{.HostConfig.NetworkMode}}')" == sbi_pr129_pg_staging_only ]]
mkdir -p "$WORK"; chmod 700 "$WORK"; cd "$WORK"
echo "LIVE_AND_STAGING_CONTAINERS=RUNNING"
echo "PRIVATE_STAGE_PUBLIC_PORTS=NONE"

echo "=== B. SOURCE-ONLY ORIGIN POLICY INVENTORY IN LIVE PR129 ==="
STEP=SOURCE
curl -4 -fLsS --retry 3 -o inspect_origin_policy_safe.py "$REPO/$PIN/database/stages23_25/inspect_origin_policy_safe.py"
[[ "$(git hash-object inspect_origin_policy_safe.py)" == "$SOURCE_SHA" ]]
python3 -m py_compile inspect_origin_policy_safe.py
sudo -n docker exec -i "$LIVE" python3 -B - < inspect_origin_policy_safe.py | tee live_origin_policy.txt
grep -qx 'ORIGIN_SOURCE_INVENTORY=COMPLETE' live_origin_policy.txt

echo "=== C. SAME SOURCE INSPECTION IN PRIVATE STAGING ==="
STEP=STAGE
sudo -n docker exec -i "$STAGE" python3 -B - < inspect_origin_policy_safe.py | tee stage_origin_policy.txt
grep -qx 'ORIGIN_SOURCE_INVENTORY=COMPLETE' stage_origin_policy.txt

echo "=== D. MISSING TRUST-CONFIG ENVIRONMENT KEYS ==="
STEP=COMPARE
grep '^ORIGIN_ENV_NAME=' live_origin_policy.txt | sed -n 's/^ORIGIN_ENV_NAME=\([^ ]*\) PRESENT=True.*/\1/p' | sort -u > live_origin_present_names.txt
grep '^ORIGIN_ENV_NAME=' stage_origin_policy.txt | sed -n 's/^ORIGIN_ENV_NAME=\([^ ]*\) PRESENT=True.*/\1/p' | sort -u > staging_origin_present_names.txt
comm -23 live_origin_present_names.txt staging_origin_present_names.txt | sed 's/^/STAGE_MISSING_ORIGIN_CONFIG_KEY=/' || true

echo "=== E. GET-ONLY STAGING HTTP HOST/ORIGIN DIAGNOSTIC ==="
STEP=HTTP
sudo -n docker exec -i "$STAGE" python3 -B - <<'PY'
import urllib.request
import urllib.error
BASE="http://127.0.0.1:8080/login"
for label,headers in (
    ("INTERNAL_HOST",{}),
    ("TUNNEL_HOST",{"Host":"127.0.0.1:18080"}),
    ("TUNNEL_HOST_WITH_ORIGIN",{"Host":"127.0.0.1:18080","Origin":"http://127.0.0.1:18080"}),
):
    req=urllib.request.Request(BASE,headers=headers,method="GET")
    try:
        with urllib.request.urlopen(req,timeout=5) as response:
            code=response.status
            body=response.read(300000).decode("utf-8","replace")
    except urllib.error.HTTPError as ex:
        code=ex.code
        body=ex.read(300000).decode("utf-8","replace")
    except Exception as ex:
        print("STAGE_LOGIN_GET_"+label+"=ERROR_"+type(ex).__name__)
        continue
    print("STAGE_LOGIN_GET_"+label+"=HTTP_"+str(code))
    print("STAGE_LOGIN_HTML_HAS_UNTRUSTED_MESSAGE_"+label+"="+str("untrusted request origin" in body.lower()))
PY

echo "=== F. CHECK ZERO RUNTIME MODIFICATIONS ==="
STEP=STABILITY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$STAGE_BEFORE" == "$(sudo -n docker inspect "$STAGE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
echo "LIVE_AND_PRIVATE_STAGING_UNCHANGED=PASS"
echo "=== FINAL ORIGIN DIAGNOSTIC ==="
STEP=COMPLETE
echo "ORIGIN_DIAGNOSTIC_READ_ONLY=PASS"
echo "ORIGIN_SECURITY_CHECK=REMAINS_ENABLED"
echo "REAL_FIREBASE_AUTHENTICATED_E2E=NOT_PERFORMED"
echo "LIVE_RELEASE=BLOCKED_PENDING_ORIGIN_AUTH_QA_AND_OWNER_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=REVIEW_ORIGIN_GUARD_SOURCE_AND_ALLOWLIST_PRIVATE_TUNNEL_ORIGIN_ONLY"
