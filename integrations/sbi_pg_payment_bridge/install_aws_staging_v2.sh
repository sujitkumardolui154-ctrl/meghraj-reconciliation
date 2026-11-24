#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Staging-only upgrade; never modifies or routes the existing live app.
REPO='https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git'
BRANCH='feature/sbi-ft04-payment-postgres-staging-20261124'
WORK='/home/ubuntu/sbi-db-management/ft04-v2-overlay-20261124'
SRC="$WORK/repository"
APP='sbi-pr129-modern-release-final'
PG='sbi-synthetic-postgres-38-31'
NET='sbi-synthetic-isolated-38-31'
DB='sbi_ft04g_clean_0e858f93'
WRITER_ENV='/home/ubuntu/sbi-db-management/ft04q/sbi_ft04q_ingest.env'
IMAGE='sbi-ft04-staging-bridge:v2-20261124'
VOLUME='sbi-ft04-private-evidence-v2'
STAGE='sbi-ft04-payment-staging-v2'
WORKER='sbi-ft04-payment-outbox-v2'

printf '%s\n' '=== SBI FT04 V2 INTEGRATED STAGING ==='
[[ -f "$WRITER_ENV" ]] || { echo 'STOP=QA_WRITER_CREDENTIALS_MISSING'; exit 1; }
command -v git >/dev/null
python3 - <<'PY'
import json,subprocess

def docker(*args):
    return json.loads(subprocess.check_output(['sudo','-n','docker',*args],text=True))[0]
net=docker('network','inspect','sbi-synthetic-isolated-38-31')
pg=docker('inspect','sbi-synthetic-postgres-38-31')
assert net['Internal'] is True
allowed={'sbi-synthetic-postgres-38-31','sbi-ft04-payment-staging-overlay','sbi-ft04-payment-staging-v2','sbi-ft04-payment-outbox-v2'}
actual={v['Name'] for v in (net.get('Containers') or {}).values()}
assert 'sbi-synthetic-postgres-38-31' in actual and actual <= allowed,('QA_NETWORK_UNEXPECTED_MEMBER',actual)
assert pg['State']['Status']=='running'
assert not pg['HostConfig'].get('PortBindings')
assert not any(m.get('Destination','').startswith('/var/run/postgresql') for m in pg.get('Mounts') or [])
for name in actual-{'sbi-synthetic-postgres-38-31'}:
    c=docker('inspect',name)
    assert not c['HostConfig'].get('PortBindings')
    assert not any(m.get('Destination','').startswith('/var/run/postgresql') for m in c.get('Mounts') or [])
print('ISOLATED_NETWORK=PASS')
PY

DB_FOUND=$(sudo -n docker exec "$PG" psql -X -qAt -U postgres -d postgres -c \
  "SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database WHERE datname IN ('sbi_reconciliation_main','$DB')")
[[ "$DB_FOUND" == "$DB" ]] || { echo 'STOP=QA_DATABASE_IDENTITY_FAILED'; exit 1; }
echo 'QA_DB_TARGET=PASS'

mkdir -p "$WORK"
chmod 700 "$WORK"
if [[ ! -d "$SRC/.git" ]]; then
  git clone -q --depth 1 --branch "$BRANCH" "$REPO" "$SRC"
else
  git -C "$SRC" fetch -q origin "$BRANCH"
  git -C "$SRC" checkout -q --detach FETCH_HEAD
fi
FILES="$SRC/integrations/sbi_pg_payment_bridge"
for f in sbi_payment_pg_bridge.py sbi_pg_outbox.py outbox_worker.py staging_wsgi.py Dockerfile.staging; do
  [[ -s "$FILES/$f" ]] || { echo "STOP=INTEGRATION_SOURCE_MISSING:$f"; exit 1; }
done

BASE_ID=$(sudo -n docker inspect -f '{{.Image}}' "$APP")
[[ "$BASE_ID" == sha256:* ]] || { echo 'STOP=LIVE_IMAGE_UNVERIFIED'; exit 1; }
sudo -n docker tag "$BASE_ID" sbi-ft04-base:20261124
sudo -n docker build --network none -t "$IMAGE" -f "$FILES/Dockerfile.staging" "$FILES" >/dev/null
printf '%s\n' 'STAGING_V2_IMAGE=BUILT'

# Private, durable Docker volume. Unlike /tmp it survives container restarts.
sudo -n docker volume create "$VOLUME" >/dev/null
APP_UID=$(sudo -n docker run --rm --network none --entrypoint python3 "$IMAGE" -c 'import os;print(os.geteuid())')
APP_GID=$(sudo -n docker run --rm --network none --entrypoint python3 "$IMAGE" -c 'import os;print(os.getegid())')
[[ "$APP_UID" =~ ^[0-9]+$ && "$APP_GID" =~ ^[0-9]+$ ]] || { echo 'STOP=CONTAINER_IDENTITY_INVALID'; exit 1; }
sudo -n docker run --rm --network none --user 0 \
  --mount "type=volume,source=$VOLUME,target=/qa-receipts" \
  --entrypoint python3 "$IMAGE" -c \
  "import os;os.chown('/qa-receipts',$APP_UID,$APP_GID);os.chmod('/qa-receipts',0o700)" >/dev/null
printf '%s\n' 'DURABLE_PRIVATE_RECEIPT_VOLUME=PASS'

# Exact target guard; fail closed if anything is wrongly configured.
sudo -n docker run --rm --network "$NET" --read-only \
  --mount "type=volume,source=$VOLUME,target=/qa-receipts" \
  --tmpfs /tmp:rw,nosuid,size=16m \
  --env-file "$WRITER_ENV" \
  -e SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only \
  -e SBI_PAYMENT_EVIDENCE_DIR=/qa-receipts \
  --entrypoint python3 "$IMAGE" -B -c \
  'from staging_wsgi import app; from sbi_pg_outbox import _store; _store(); print("STAGING_V2_ROUTE_AND_OUTBOX=PASS")'

# Do not restart or replace an already running stage automatically.
for name in "$STAGE" "$WORKER"; do
  if sudo -n docker inspect "$name" >/dev/null 2>&1; then
    echo "STOP=STAGING_V2_CONTAINER_ALREADY_EXISTS:$name"
    exit 2
  fi
done

sudo -n docker run -d --name "$STAGE" \
  --network "$NET" --read-only \
  --tmpfs /tmp:rw,nosuid,size=32m \
  --mount "type=volume,source=$VOLUME,target=/qa-receipts" \
  --env-file "$WRITER_ENV" \
  -e SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only \
  -e SBI_PAYMENT_EVIDENCE_DIR=/qa-receipts \
  --restart on-failure:5 --entrypoint gunicorn "$IMAGE" \
  -b 0.0.0.0:8080 -w 1 staging_wsgi:app >/dev/null

sudo -n docker run -d --name "$WORKER" \
  --network "$NET" --read-only \
  --tmpfs /tmp:rw,nosuid,size=32m \
  --mount "type=volume,source=$VOLUME,target=/qa-receipts" \
  --env-file "$WRITER_ENV" \
  -e SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only \
  -e SBI_PAYMENT_EVIDENCE_DIR=/qa-receipts \
  --restart on-failure:5 --entrypoint python3 "$IMAGE" \
  -B -m outbox_worker >/dev/null

sleep 2
for name in "$STAGE" "$WORKER"; do
  if [[ $(sudo -n docker inspect -f '{{.State.Running}}' "$name") != true ]]; then
    echo "STOP=STAGING_RUNTIME_BLOCKED:$name"
    sudo -n docker logs --tail 10 "$name" 2>&1 | sed -E 's/(password|secret|token|key)=([^ ]+)/\1=[REDACTED]/Ig'
    exit 3
  fi
done
printf '%s\n' 'STAGING_V2_APP=RUNNING_ISOLATED' \
 'STAGING_V2_OUTBOX_WORKER=RUNNING_ISOLATED' \
 'NO_PUBLIC_PORTS=PASS' \
 'LIVE_APPLICATION_UNCHANGED=YES' \
 'PRODUCTION_DATABASE_WRITES=NONE' \
 'FIREBASE_AND_LIVE_REPORT_PARITY=NOT_TESTED' \
 '=== FT04 V2 STAGING READY ==='
