#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
# One QA-only transaction. SQL explicitly ROLLBACKs; existing stage unchanged.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
FILE="$ROOT/db_r31_owner_scope_qa_tx.sql"
PG='sbi-synthetic-postgres-38-31'
NET='sbi-synthetic-isolated-38-31'
DB='sbi_ft04g_clean_0e858f93'
[[ -s "$FILE" ]] || { echo 'STOP=OWNER_SCOPE_QA_SQL_MISSING'; exit 1; }
python3 - <<'PY'
import json, subprocess
def docker(*args):
    return json.loads(subprocess.check_output(
        ['sudo','-n','docker',*args],text=True))[0]
network=docker('network','inspect','sbi-synthetic-isolated-38-31')
pg=docker('inspect','sbi-synthetic-postgres-38-31')
names={x.get('Name') for x in (network.get('Containers') or {}).values()}
allowed={'sbi-synthetic-postgres-38-31',
         'sbi-ft04-payment-staging-overlay',
         'sbi-ft04-payment-staging-v2',
         'sbi-ft04-payment-outbox-v2'}
assert network['Internal'] is True and names <= allowed
assert 'sbi-synthetic-postgres-38-31' in names
assert set(pg.get('NetworkSettings',{}).get('Networks',{})) == {'sbi-synthetic-isolated-38-31'}
for name in names:
    container=docker('inspect',name)
    assert container['State']['Status']=='running'
    assert not container['HostConfig'].get('PortBindings')
    assert not any(m.get('Destination','').startswith('/var/run/postgresql')
                   for m in container.get('Mounts') or [])
print('DB_R31_ISOLATED_NETWORK_SAFETY=PASS')
PY

psql_db(){ sudo -n docker exec "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$1" -c "$2"; }
found="$(psql_db postgres "SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database WHERE datname IN ('sbi_reconciliation_main','$DB')")"
[[ "$found" == "$DB" ]] || { echo 'STOP=ISOLATED_QA_DATABASE_IDENTITY'; exit 1; }
echo 'DB_R31_PRODUCTION_DB_IN_QA_INSTANCE=ABSENT'

counts(){ psql_db "$DB" \
  "SELECT (SELECT count(*) FROM sbi.import_batches)::text||'|'||
          (SELECT count(*) FROM sbi.payment_source_rows)::text||'|'||
          (SELECT count(*) FROM sbi.payments)::text||'|'||
          (SELECT count(*) FROM sbi.invoices)::text||'|'||
          (SELECT count(*) FROM sbi.payment_source_status_v1)::text"; }
before="$(counts)"
schema_before="$(psql_db "$DB" \
  "SELECT (SELECT count(*) FROM pg_constraint WHERE conrelid='sbi.import_batches'::regclass
     AND contype='u' AND pg_get_constraintdef(oid) LIKE
       'UNIQUE (source_system, source_kind, source_sha256)%')::text||'|'||
     (SELECT count(*) FROM pg_indexes WHERE schemaname='sbi' AND
       indexname IN ('ux_r31_qa_owned_source_sha','ux_r31_qa_legacy_source_sha'))::text")"
[[ "$schema_before" == '1|0' ]] || { echo 'STOP=OWNER_SCOPE_QA_START_SCHEMA_CONFLICT'; exit 1; }

# DO NOT remove explicit SQL ROLLBACK. A failed query automatically aborts
# the session's open transaction without committing any synthetic data.
result="$(sudo -n docker exec -i "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$DB" -f - < "$FILE" 2>&1)"
printf '%s\n' "$result" | grep -F 'DB_R31_OWNER_SCOPE_QA_TRANSACTION=ROLLED_BACK' >/dev/null || {
  echo 'STOP=QA_SQL_ROLLBACK_MARKER_MISSING'; exit 1;
}

after="$(counts)"
schema_after="$(psql_db "$DB" \
  "SELECT (SELECT count(*) FROM pg_constraint WHERE conrelid='sbi.import_batches'::regclass
     AND contype='u' AND pg_get_constraintdef(oid) LIKE
       'UNIQUE (source_system, source_kind, source_sha256)%')::text||'|'||
     (SELECT count(*) FROM pg_indexes WHERE schemaname='sbi' AND
       indexname IN ('ux_r31_qa_owned_source_sha','ux_r31_qa_legacy_source_sha'))::text")"
[[ "$before" == "$after" && "$schema_before" == "$schema_after" ]] || {
  echo 'STOP=QA_ROLLBACK_SCHEMA_OR_FINANCIAL_PARITY_FAILED'; exit 1;
}
printf '%s\n' 'DB_R31_OWNER_SCOPED_DUPLICATE_QA=PASS' \
  'DB_R31_UNOWNED_NEW_PAYMENT_BLOCK_QA=PASS' \
  'DB_R31_TWO_OWNER_SOURCE_SUMMARY_QA=PASS' \
  'DB_R31_INVALID_SOURCE_EVIDENCE_QA=PASS' \
  'DB_R31_RAW_SOL_AND_NOT_CALCULATED_QA=PASS' \
  'DB_R31_QA_OWNER_SCOPE_TRANSACTION=PASS_ROLLED_BACK' \
  'DB_R31_QA_FINANCIAL_ROWS_AND_SCHEMA_UNCHANGED=PASS' \
  'DB_R31_GLOBAL_SHA_UNIQUE=STILL_PRESENT_AFTER_ROLLBACK' \
  'DB_R31_PRODUCTION_DATABASE_WRITES=NONE_BY_TEST' \
  'DB_R31_RELEASE_STATUS=ISOLATED_OWNER_SCOPE_QA_ONLY'
