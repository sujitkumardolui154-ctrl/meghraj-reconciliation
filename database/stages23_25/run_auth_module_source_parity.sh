#!/usr/bin/env bash
# Restore exactly two missing PR129 source modules into an isolated AWS image.
# Never copies Google credentials, changes live, exposes a port or writes finance.
set -Eeuo pipefail
umask 077
STEP=INIT
LIVE=sbi-bulk-report-pr129-https-preview
OLD=sbi-pr129-pg-origin-stage-v2
BASE=sbi-pr129-pg-origin18080-v2:isolated
IMAGE=sbi-pr129-pg-auth-source-parity:isolated
DB=sbi_reconciliation_main
SCRATCH=""
cleanup(){
  rc=$?
  trap - EXIT
  if [[ -n "$SCRATCH" && "$SCRATCH" == /tmp/sbi_authmodules_* ]]; then
    sudo -n rm -rf -- "$SCRATCH" || rc=98
  fi
  if ((rc));then echo "AUTH_SOURCE_PARITY_QA=FAIL step=$STEP exit=$rc";else echo "AUTH_SOURCE_PARITY_QA=PASS";fi
  echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
  exit "$rc"
}
trap cleanup EXIT
counts(){ sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$DB" -c "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }

echo "=== A. PRESERVE LIVE/FINANCIAL BASELINE ==="
STEP=BASELINE
sudo -n docker info >/dev/null
sudo -n docker image inspect "$BASE" >/dev/null
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
OLD_BEFORE="$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
FIN_BEFORE="$(counts)"
[[ -z "$(sudo -n docker port "$OLD")" ]]
echo "BASELINE=PASS"

echo "=== A2. VERIFY LIVE AUTH SESSION ROUTE BEFORE BUILD ==="
sudo -n docker exec -i "$LIVE" python3 -B - <<'PY'
from app import app
found={}
for rule in app.url_map.iter_rules():
 if rule.rule in ("/auth/session","/login"):
  fn=app.view_functions.get(rule.endpoint)
  found[rule.rule]=fn.__name__ if fn else "UNBOUND"
for path,name in sorted(found.items()):
 print("LIVE_AUTH_ROUTE="+path+" HANDLER="+name)
print("LIVE_AUTH_SESSION_HANDLER_DISCOVERY=COMPLETE")
PY

echo "=== B. TWO SOURCE FILES: AWS-LOCAL COPY, NO SERVICE CREDENTIAL ==="
STEP=COPY
SCRATCH="$(mktemp -d /tmp/sbi_authmodules_XXXXXXXX)"
chmod 700 "$SCRATCH"
for file in cloud_auth.py sbi_report_access.py;do
  sudo -n docker cp "$LIVE:/app/$file" "$SCRATCH/$file"
  sudo -n chown "$(id -u):$(id -g)" "$SCRATCH/$file"
  chmod 600 "$SCRATCH/$file"
  [[ -s "$SCRATCH/$file" ]]
  (( $(stat -c '%s' "$SCRATCH/$file") < 400000 ))
  python3 -B -m py_compile "$SCRATCH/$file"
done
if grep -Eql -- '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' "$SCRATCH/"*.py; then
  echo "PRIVATE_KEY_EMBEDDED_IN_MODULE=REVIEW_REQUIRED"; exit 31
fi
echo "LIVE_APP_MODULE_COPY=PASS"
echo "CREDENTIAL_FILES_COPIED=NO"
echo "PRIVATE_SOURCE_UPLOADED_TO_GITHUB=NO"

echo "=== C. BUILD DERIVED CANDIDATE IN AWS ONLY ==="
STEP=BUILD
cat > "$SCRATCH/Dockerfile" <<'DOCKER'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
WORKDIR /app
COPY cloud_auth.py sbi_report_access.py /app/
RUN chmod 0644 /app/cloud_auth.py /app/sbi_report_access.py \
 && python3 -B -m py_compile /app/cloud_auth.py /app/sbi_report_access.py \
 && echo 'AUTH_MODULES_IN_ISOLATED_IMAGE=PASS'
DOCKER
sudo -n docker build --pull=false --build-arg BASE_IMAGE="$BASE" -f "$SCRATCH/Dockerfile" -t "$IMAGE" "$SCRATCH"
echo "NEW_IMAGE_AUTH_MODULES=BUILT"

echo "=== D. REAL REPORT POLICY, ANONYMOUS DENIAL, AUTH SERVICE ROUTING ==="
STEP=UNIT
sudo -n docker run --rm -i --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m --cap-drop ALL \
  --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 "$IMAGE" -B - <<'PY'
import inspect
from pathlib import Path
from sbi_report_access import can_view_report
from app import app
assert Path("/app/cloud_auth.py").is_file()
assert list(inspect.signature(can_view_report).parameters)==["user","identity","change_report"]
assert callable(app.config.get("SBI_PG_REPORT_AUTH_CHECK"))
r=app.test_client().get("/api/reporting/v2/postgresql-summary")
assert r.status_code in (401,403),r.status_code
print("SOURCE_PARITY=PASS")
print("REPORT_POLICY_SIGNATURE=PASS")
print("ANONYMOUS_PG_ROUTE_DENIAL=PASS")
for rule in app.url_map.iter_rules():
 if rule.rule in ("/auth/session","/login"):
  fn=app.view_functions.get(rule.endpoint)
  handler=fn.__name__ if fn else "UNBOUND"
  print("ROUTE="+rule.rule+" HANDLER="+handler)
  if rule.rule=="/auth/session" and handler=="pipeline_not_on_login_service":
   print("AUTH_SESSION_BACKEND=STUB_REQUIRES_REAL_LOGIN_SERVICE")
PY

echo "=== E. LIVE AND FINANCIAL SAFETY ==="
STEP=STABILITY
[[ "$FIN_BEFORE" == "$(counts)" ]]
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$OLD_BEFORE" == "$(sudo -n docker inspect "$OLD" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
echo "LIVE_PR129_UNCHANGED=PASS"
echo "OLD_PRIVATE_STAGE_UNCHANGED=PASS"
echo "CENTRAL_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE24 SOURCE PARITY QA ==="
echo "STAGE24_AUTH_MODULES_IN_NEW_ISOLATED_IMAGE=PASS"
echo "NEW_STAGING_SERVICE=NOT_DEPLOYED"
echo "FIREBASE_AUTHENTICATED_USER_E2E=NOT_PERFORMED"
echo "GOOGLE_APPLICATION_CREDENTIALS=NOT_COPIED"
echo "AUTHORIZED_POSTGRES_REPORT=NOT_TESTED"
echo "LIVE_RELEASE=BLOCKED_PENDING_REAL_USER_AUTH_QA_AND_APPROVAL"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "FINANCIAL_WRITES_BY_TEST=NONE"
echo "NEXT=VERIFY_LOGIN_SESSION_HANDLER_AND_STAGING_AUTH_CREDENTIAL_CONFIGURATION"
