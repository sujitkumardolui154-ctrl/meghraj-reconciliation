#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
# One combined QA test, no production connection or financial DML.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
UP="$ROOT/db_r31_additive_qa_up.sql"
DOWN="$ROOT/db_r31_additive_qa_down.sql"
PG='sbi-synthetic-postgres-38-31'
NET='sbi-synthetic-isolated-38-31'
QA='sbi_ft04g_clean_0e858f93'
for file in "$UP" "$DOWN"; do
  [[ -s "$file" ]] || { echo "STOP=MISSING_QA_MIGRATION_FILE"; exit 1; }
done

# Verify physically isolated QA container/net and that no central database
# exists in this PostgreSQL instance.
python3 - <<'PY'
import json,subprocess
def get(*args):
    return json.loads(subprocess.check_output(
        ['sudo','-n','docker',*args],text=True
    ))[0]
net=get('network','inspect','sbi-synthetic-isolated-38-31')
pg=get('inspect','sbi-synthetic-postgres-38-31')
allowed={'sbi-synthetic-postgres-38-31',
         'sbi-ft04-payment-staging-overlay','sbi-ft04-payment-staging-v2',
         'sbi-ft04-payment-outbox-v2'}
members={x.get('Name') for x in (net.get('Containers') or {}).values()}
assert net['Internal'] is True and 'sbi-synthetic-postgres-38-31' in members
assert members <= allowed, ('UNEXPECTED_QA_NETWORK_MEMBER',sorted(members))
for name in members:
    c=get('inspect',name)
    assert c['State']['Status']=='running'
    assert not c['HostConfig'].get('PortBindings')
    assert not any(m.get('Destination','').startswith('/var/run/postgresql')
                   for m in c.get('Mounts') or [])
assert set((pg['NetworkSettings'].get('Networks') or {})) == {
    'sbi-synthetic-isolated-38-31'
}
print('DB_R31_QA_NETWORK_SAFETY=PASS')
PY

DBS="$(sudo -n docker exec "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d postgres -c \
"SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database WHERE datname IN ('sbi_reconciliation_main','$QA')")"
[[ "$DBS" == "$QA" ]] || { echo 'STOP=QA_DATABASE_IDENTITY'; exit 1; }
echo 'DB_R31_MAIN_IN_QA_INSTANCE=ABSENT'

sql(){ sudo -n docker exec "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$QA" -c "$1"; }
script(){ sudo -n docker exec -i "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$QA" -f - < "$1"; }
counts(){
 sql "SELECT (SELECT count(*) FROM sbi.import_batches)::text||'|'||
 (SELECT count(*) FROM sbi.payment_source_rows)::text||'|'||
 (SELECT count(*) FROM sbi.payments)::text||'|'||
 (SELECT count(*) FROM sbi.invoices)::text"
}
BEFORE="$(counts)"
echo 'DB_R31_FINANCIAL_ROW_COUNTS_BASELINE_CAPTURED=YES'

# QA-only reversible migration. Both files guard exact QA database identity.
script "$UP" >/dev/null
echo 'DB_R31_QA_ADDITIVE_UP=PASS'

# The view must be strictly 1:1 with the source record, even with payments
# and review status joined. This is not a verified allocation report.
CROSSCHECK="$(sql "SELECT
 (SELECT count(*) FROM sbi.payment_source_rows)::text || '|' ||
 (SELECT count(*) FROM sbi.payment_received_source_v1)::text || '|' ||
 (SELECT count(*) FROM sbi.payment_source_status_v1)::text")"
SRC="${CROSSCHECK%%|*}"
REST="${CROSSCHECK#*|}"
VIEW="${REST%%|*}"
ST="${REST##*|}"
[[ "$SRC" == "$VIEW" && "$ST" == '0' ]] || {
 echo 'STOP=SOURCE_VIEW_COUNT_MISMATCH_OR_EXISTING_REVIEW_ROWS'; exit 1;
}
[[ "$(counts)" == "$BEFORE" ]] || { echo 'STOP=SOURCE_ROW_COUNTS_CHANGED'; exit 1; }
echo 'DB_R31_QA_SOURCE_VIEW_PARITY=PASS'
echo 'DB_R31_QA_SOURCE_STATUS_ROWS=0'

# Exercise the guarded rollback before leaving the approved QA schema in
# place. It must refuse to delete real R31 source status evidence (none yet).
script "$DOWN" >/dev/null
[[ "$(counts)" == "$BEFORE" ]] || { echo 'STOP=ROLLBACK_ROW_COUNTS_CHANGED'; exit 1; }
echo 'DB_R31_QA_REVERSIBLE_DOWN=PASS'

script "$UP" >/dev/null
[[ "$(counts)" == "$BEFORE" ]] || { echo 'STOP=REAPPLY_ROW_COUNTS_CHANGED'; exit 1; }
[[ "$(sql "SELECT count(*) FROM sbi.payment_received_source_v1")" == "$SRC" ]] || {
 echo 'STOP=REAPPLY_VIEW_MISMATCH'; exit 1;
}
echo 'DB_R31_QA_FINAL_SCHEMA_APPLIED=PASS'
echo 'DB_R31_FINANCIAL_ROW_COUNTS_UNCHANGED=PASS'
echo 'DB_R31_MULTI_OWNER_GLOBAL_SHA_BLOCK=STILL_PRESENT'
echo 'DB_R31_PRODUCTION_FINANCIAL_WRITES=NONE_BY_QA_TEST'
echo 'DB_R31_RELEASE_STATUS=ISOLATED_SCHEMA_QA_PASS_ONLY'
echo '=== DB_R31 ISOLATED SCHEMA COMBINED COMPLETE ==='
