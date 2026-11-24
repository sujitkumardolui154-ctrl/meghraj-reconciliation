#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Installs only a separate staging overlay. No production app source, Caddy,
# database schema, routing or credentials are changed.
REPO='https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git'
BRANCH='feature/sbi-ft04-payment-postgres-staging-20261124'
WORK='/home/ubuntu/sbi-db-management/ft04-staging-overlay-20261124'
SOURCE="$WORK/source"
PG='sbi-synthetic-postgres-38-31'
NETWORK='sbi-synthetic-isolated-38-31'
DATABASE='sbi_ft04g_clean_0e858f93'
LIVE='sbi-pr129-modern-release-final'
STAGE='sbi-ft04-payment-staging-overlay'
ENV_FILE='/home/ubuntu/sbi-db-management/ft04q/sbi_ft04q_ingest.env'

printf '%s\n' '=== SBI FT04 APPLICATION INTEGRATION ==='
[[ -f "$ENV_FILE" ]] || { echo 'STOP=STAGING_CREDENTIALS_MISSING'; exit 1; }
command -v git >/dev/null
command -v sudo >/dev/null
command -v python3 >/dev/null

# Verify the network is internal, its only current container is the synthetic
# PostgreSQL instance, and the production database is absent from QA.
python3 - <<'PY'
import json, subprocess

def get(*args):
    return json.loads(subprocess.check_output(['sudo','-n','docker',*args],text=True))[0]

net=get('network','inspect','sbi-synthetic-isolated-38-31')
pg=get('inspect','sbi-synthetic-postgres-38-31')
assert net['Internal'] is True
assert {v['Name'] for v in net.get('Containers',{}).values()}=={'sbi-synthetic-postgres-38-31'}
assert pg['State']['Status']=='running'
assert not pg['HostConfig'].get('PortBindings')
assert not any(m.get('Destination','').startswith('/var/run/postgresql') for m in pg.get('Mounts',[]))
print('QA_NETWORK_SAFETY=PASS')
PY

DB_FOUND=$(sudo -n docker exec "$PG" psql -X -qAt -U postgres -d postgres -c \
  "SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database WHERE datname IN ('sbi_reconciliation_main','$DATABASE')")
[[ "$DB_FOUND" == "$DATABASE" ]] || { echo 'STOP=QA_DATABASE_SAFETY'; exit 1; }
echo 'QA_DATABASE_SAFETY=PASS'

mkdir -p "$WORK"
chmod 700 "$WORK"
if [[ -e "$SOURCE" ]]; then
  [[ -s "$SOURCE/integrations/sbi_pg_payment_bridge/sbi_payment_pg_bridge.py" ]] || {
    echo 'STOP=EXISTING_STAGING_SOURCE_INVALID'; exit 1;
  }
else
  git clone -q --depth 1 --branch "$BRANCH" "$REPO" "$SOURCE"
fi
[[ -s "$SOURCE/integrations/sbi_pg_payment_bridge/sbi_payment_pg_bridge.py" ]] || { echo 'STOP=BRIDGE_MISSING'; exit 1; }

BASE_ID=$(sudo -n docker inspect -f '{{.Image}}' "$LIVE")
[[ "$BASE_ID" == sha256:* ]] || { echo 'STOP=LIVE_IMAGE_UNVERIFIED'; exit 1; }
sudo -n docker tag "$BASE_ID" sbi-ft04-base:20261124
sudo -n docker build --network none \
  -t sbi-ft04-staging-bridge:20261124 \
  -f "$SOURCE/integrations/sbi_pg_payment_bridge/Dockerfile.staging" \
  "$SOURCE/integrations/sbi_pg_payment_bridge" >/dev/null
printf '%s\n' 'STAGING_OVERLAY_IMAGE=BUILT'

# Import the original app and install the bridge in a disposable container.
# It will fail closed if the live image requires staging-only Firebase secrets
# or storage services that were not provided; production is never altered.
set +e
PROBE=$(sudo -n docker run --rm \
  --network "$NETWORK" --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --env-file "$ENV_FILE" \
  -e SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only \
  -e SBI_PAYMENT_EVIDENCE_DIR=/tmp/sbi-stage-receipts \
  --entrypoint python3 sbi-ft04-staging-bridge:20261124 -B -c \
  'from staging_wsgi import app; print("STAGING_APP_ROUTE_WIRING=PASS")' 2>&1)
STATUS=$?
set -e
if ((STATUS)); then
  echo 'STAGING_APP_ROUTE_WIRING=BLOCKED'
  echo "$PROBE" | tail -n 12
  echo 'LIVE_APPLICATION_UNCHANGED=YES'
  exit 2
fi
echo "$PROBE"

# Start locally accessible *inside the isolated Docker network only*.
if sudo -n docker inspect "$STAGE" >/dev/null 2>&1; then
  echo 'STAGING_CONTAINER_ALREADY_EXISTS=REVIEW_REQUIRED'
  exit 3
fi
sudo -n docker run -d \
  --name "$STAGE" \
  --network "$NETWORK" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --env-file "$ENV_FILE" \
  -e SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only \
  -e SBI_PAYMENT_EVIDENCE_DIR=/tmp/sbi-stage-receipts \
  --entrypoint gunicorn \
  sbi-ft04-staging-bridge:20261124 \
  -b 0.0.0.0:8080 -w 1 staging_wsgi:app >/dev/null

sleep 2
if [[ $(sudo -n docker inspect -f '{{.State.Running}}' "$STAGE") != true ]]; then
  echo 'STAGING_APP_RUNTIME=BLOCKED'
  sudo -n docker logs --tail 14 "$STAGE" 2>&1 | sed -E 's/(password|token|secret|key)=([^ ]+)/\1=[REDACTED]/Ig'
  echo 'LIVE_APPLICATION_UNCHANGED=YES'
  exit 4
fi
printf '%s\n' 'STAGING_APP_RUNTIME=RUNNING_ISOLATED' \
 'PUBLIC_PORTS=NONE' \
 'LIVE_APPLICATION_UNCHANGED=YES' \
 'PRODUCTION_DATABASE_WRITES=NONE' \
 'ACTUAL_FIREBASE_AUTH_AND_LIVE_REPORT_PARITY=NOT_YET_TESTED' \
 '=== FT04 STAGING CODE INTEGRATED ==='
