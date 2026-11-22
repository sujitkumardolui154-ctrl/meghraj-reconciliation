#!/usr/bin/env bash
# Stage 28: fresh PostgreSQL backup, disposable full restore, encrypted
# off-host backup package and read-only PR129 rollback readiness inventory.
# No changes to source financial DB, live containers, Caddy routing, or engine.
set -Eeuo pipefail
umask 077
STEP=INIT
DB=sbi_reconciliation_main
LIVE=sbi-bulk-report-pr129-https-preview
S25=sbi-pr129-pg-stage25-firebase-adc
S26=sbi-pr129-pg-modernui-stage26r2
CADDY=aws_lightsail-caddy-1
ROOT=/home/ubuntu/sbi-db-backups
TMPDB=""
CREATED=NO
DIR=""
DUMP=""
ENCRYPTED=""

sql(){ local db="$1"; shift; sudo -n -u postgres psql -X -A -t -v ON_ERROR_STOP=1 -d "$db" -c "$1"; }
counts(){ sql "$1" "SELECT (SELECT count(*) FROM sbi.invoices),(SELECT count(*) FROM sbi.payments),(SELECT count(*) FROM sbi.allocations),(SELECT count(*) FROM sbi.credit_notes);"; }
objects(){ sql "$1" "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='sbi' AND c.relkind='r'),(SELECT count(*) FROM pg_views WHERE schemaname='sbi');"; }
finish(){
 local rc=$?
 trap - EXIT
 if [[ "$CREATED" == YES ]];then
  if sudo -n -u postgres dropdb "$TMPDB" >/dev/null 2>&1;then
   echo "STAGE28_TEMP_RESTORE_DATABASE_CLEANUP=PASS"
  else
   echo "STAGE28_TEMP_RESTORE_DATABASE_CLEANUP=FAIL name=$TMPDB"
   rc=98
  fi
 fi
 if ((rc));then echo "STAGE28_COMBINED_QA=FAIL step=$STEP exit=$rc"
 else echo "STAGE28_COMBINED_QA=PASS_LOCAL";fi
 echo "STAGE28_OFF_HOST_BACKUP_VERIFICATION=NOT_PERFORMED"
 echo "LIVE_PR129_CUTOVER=NOT_PERFORMED"
 echo "FINANCIAL_SOURCE_WRITES_BY_TEST=NONE"
 exit "$rc"
}
trap finish EXIT

echo "=== A. RECORD LIVE AND DATABASE BASELINES ==="
STEP=BASELINE
sudo -n docker info >/dev/null
for c in "$LIVE" "$S25" "$S26" "$CADDY";do
 [[ "$(sudo -n docker inspect "$c" --format '{{.State.Running}}')" == true ]] ||
  { echo "REQUIRED_CONTAINER_NOT_RUNNING=$c";exit 11; }
done
LIVE_BEFORE="$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
S25_BEFORE="$(sudo -n docker inspect "$S25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
S26_BEFORE="$(sudo -n docker inspect "$S26" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
CADDY_BEFORE="$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')"
[[ -z "$(sudo -n docker port "$S26")" ]]
BASE_COUNTS="$(counts "$DB")"
BASE_OBJECTS="$(objects "$DB")"
[[ "$BASE_OBJECTS" != "0|0" ]]
echo "STAGE28_BASELINE=PASS"

echo "=== B. FRESH PROTECTED LOCAL BACKUP ==="
STEP=BACKUP
[[ -d "$ROOT" ]] || { echo "BACKUP_ROOT=MISSING";exit 12; }
command -v openssl >/dev/null
command -v pg_restore >/dev/null
DIR="$(mktemp -d "$ROOT/stage28_XXXXXXXX")"
chmod 700 "$DIR"
DUMP="$DIR/sbi_reconciliation_main.dump"
ENCRYPTED="$DIR/sbi_reconciliation_main.dump.enc"
sudo -n -u postgres pg_dump -Fc --no-owner --no-acl -d "$DB" > "$DUMP"
chmod 600 "$DUMP"
[[ -s "$DUMP" ]]
pg_restore -l "$DUMP" >/dev/null
DUMP_SHA="$(sha256sum "$DUMP" | awk '{print $1}')"
echo "STAGE28_FRESH_DUMP_CATALOG=PASS"
echo "STAGE28_FRESH_DUMP_SHA256=$DUMP_SHA"

echo "=== C. FULL RESTORE INTO DISPOSABLE POSTGRESQL DB ==="
STEP=RESTORE
TMPDB="sbi_stage28_$(basename "$DIR" | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')"
[[ "$TMPDB" =~ ^sbi_stage28_[a-z0-9]+$ ]]
[[ -z "$(sql postgres "SELECT 1 FROM pg_database WHERE datname='$TMPDB'")" ]] ||
 { echo "TEMP_RESTORE_DB_ALREADY_EXISTS=FAIL";exit 13; }
sudo -n -u postgres createdb -T template0 "$TMPDB"
CREATED=YES
sudo -n -u postgres pg_restore --exit-on-error --no-owner --no-acl \
 --dbname "$TMPDB" < "$DUMP"
[[ "$BASE_OBJECTS" == "$(objects "$TMPDB")" ]] ||
 { echo "STAGE28_RESTORE_SCHEMA_PARITY=FAIL";exit 14; }
[[ "$BASE_COUNTS" == "$(counts "$TMPDB")" ]] ||
 { echo "STAGE28_RESTORE_ROW_PARITY=FAIL";exit 15; }
[[ "$BASE_COUNTS" == "$(counts "$DB")" ]] ||
 { echo "STAGE28_SOURCE_COUNTS_CHANGED=REVIEW_REQUIRED";exit 16; }
echo "STAGE28_ISOLATED_RESTORE_REHEARSAL=PASS"
echo "STAGE28_SCHEMA_AND_RECORD_COUNTS_PARITY=PASS"

echo "=== D. PASSWORD-PROTECTED ENCRYPTED OFF-HOST PACKAGE ==="
STEP=ENCRYPT
[[ -r /dev/tty ]] || { echo "STAGE28_INTERACTIVE_PASSWORD_TTY=REQUIRED";exit 17; }
echo "Create a strong 16+ character backup passphrase; input is hidden."
echo "Save it separately in a password manager. Never share it in chat."
IFS= read -r -s -p "Stage28 backup passphrase: " PASS </dev/tty
printf '\n'
IFS= read -r -s -p "Confirm backup passphrase: " AGAIN </dev/tty
printf '\n'
LENGTH="$(printf '%s' "$PASS" | wc -c)"
if [[ "$PASS" != "$AGAIN" ]] || ((LENGTH<16));then
 unset PASS AGAIN
 echo "STAGE28_BACKUP_PASSPHRASE=INVALID_OR_MISMATCH";exit 18
fi
unset AGAIN
openssl enc -aes-256-cbc -pbkdf2 -iter 250000 -salt \
 -in "$DUMP" -out "$ENCRYPTED" -pass fd:3 3<<<"$PASS"
chmod 600 "$ENCRYPTED"
ENCRYPTED_SHA="$(sha256sum "$ENCRYPTED" | awk '{print $1}')"
DECRYPTED_SHA="$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 250000 \
 -in "$ENCRYPTED" -pass fd:3 3<<<"$PASS" | sha256sum | awk '{print $1}')"
unset PASS
[[ "$DECRYPTED_SHA" == "$DUMP_SHA" ]] ||
 { echo "STAGE28_ENCRYPTED_BACKUP_RECOVERY=FAIL";exit 19; }
echo "STAGE28_ENCRYPTION_RECOVERY_SHA256=PASS"
echo "STAGE28_ENCRYPTED_BACKUP_PATH=$ENCRYPTED"
echo "STAGE28_ENCRYPTED_BACKUP_SHA256=$ENCRYPTED_SHA"
echo "STAGE28_BACKUP_PASSPHRASE=NOT_DISPLAYED"

echo "=== E. NON-INVASIVE ROLLBACK INVENTORY ==="
STEP=ROLLBACK
LIVE_IMAGE="$(sudo -n docker inspect "$LIVE" --format '{{.Image}}')"
NEW_IMAGE="$(sudo -n docker inspect "$S26" --format '{{.Image}}')"
sudo -n docker image inspect "$LIVE_IMAGE" "$NEW_IMAGE" >/dev/null
echo "STAGE28_LIVE_ROLLBACK_IMAGE_AVAILABLE=PASS"
echo "STAGE28_STAGE26_CANDIDATE_IMAGE_AVAILABLE=PASS"
echo "STAGE28_LIVE_ROLLBACK_IMAGE_ID=$LIVE_IMAGE"
echo "STAGE28_STAGE26_CANDIDATE_IMAGE_ID=$NEW_IMAGE"
if sudo -n docker exec "$CADDY" sh -c 'grep -q "sbi-bulk-report-pr129-https-preview" /etc/caddy/Caddyfile';then
 echo "STAGE28_CADDY_LIVE_PR129_ROUTE_REFERENCE=FOUND"
else
 echo "STAGE28_CADDY_LIVE_PR129_ROUTE_REFERENCE=REVIEW_REQUIRED"
fi
if sudo -n docker exec "$CADDY" sh -c 'test -r /etc/caddy/Caddyfile';then
 echo "STAGE28_CADDY_CONFIG_SHA256=$(sudo -n docker exec "$CADDY" sha256sum /etc/caddy/Caddyfile | awk '{print $1}')"
else
 echo "STAGE28_CADDY_CONFIG_SHA256=NOT_AVAILABLE"
fi
echo "STAGE28_ROLLBACK_EXECUTION=NOT_PERFORMED"
echo "STAGE28_CADDY_CHANGE=NOT_PERFORMED"

echo "=== F. PROTECT LIVE, PRIVATE STAGES AND FINANCIAL DATABASE ==="
STEP=STABILITY
[[ "$LIVE_BEFORE" == "$(sudo -n docker inspect "$LIVE" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$S25_BEFORE" == "$(sudo -n docker inspect "$S25" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$S26_BEFORE" == "$(sudo -n docker inspect "$S26" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$CADDY_BEFORE" == "$(sudo -n docker inspect "$CADDY" --format '{{.Id}}|{{.Image}}|{{.State.Running}}')" ]]
[[ "$BASE_COUNTS" == "$(counts "$DB")" ]]
[[ "$BASE_OBJECTS" == "$(objects "$DB")" ]]
[[ -z "$(sudo -n docker port "$S26")" ]]
echo "STAGE28_LIVE_PR129_UNCHANGED=PASS"
echo "STAGE28_STAGE25_UNCHANGED=PASS"
echo "STAGE28_STAGE26_UNCHANGED=PASS"
echo "STAGE28_CADDY_UNCHANGED=PASS"
echo "STAGE28_SOURCE_FINANCIAL_COUNTS_UNCHANGED=PASS"

STEP=COMPLETE
echo "=== FINAL STAGE28 BACKUP AND ROLLBACK READINESS ==="
echo "STAGE28_LOCAL_BACKUP=PASS"
echo "STAGE28_DISPOSABLE_RESTORE=PASS"
echo "STAGE28_ENCRYPTED_LOCAL_ARCHIVE=PASS"
echo "STAGE28_ROLLBACK_IMAGE_INVENTORY=PASS"
echo "STAGE28_OFF_HOST_COPY=NOT_YET_TRANSFERRED"
echo "STAGE28_OFF_HOST_SHA256=NOT_YET_VERIFIED"
echo "STAGE28_RELEASE_READINESS=BLOCKED_PENDING_OFFHOST_BACKUP_AND_OWNER_APPROVAL"
echo "STAGE29_OWNER_APPROVAL=NOT_GIVEN"
echo "STAGE30_LIVE_PR129_CUTOVER=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
echo "NEXT=TRANSFER_ENCRYPTED_ARCHIVE_OFF_SERVER_AND_VERIFY_SHA256"
