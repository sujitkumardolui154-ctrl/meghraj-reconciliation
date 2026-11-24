#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
# Read-only central DB metadata inspection for Database Management Issue #190.
# No financial/payment/invoice rows are read. No DDL or data writes.
DB='sbi_reconciliation_main'
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
[[ -s "$HERE/db_r31_catalog_probe.sql" ]] || { echo 'STOP=CATALOG_SQL_MISSING'; exit 1; }
command -v psql >/dev/null || { echo 'STOP=HOST_POSTGRESQL_CLIENT_MISSING'; exit 1; }
TARGET="$(sudo -n -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -d "$DB" -c 'SELECT current_database();')"
[[ "$TARGET" == "$DB" ]] || { echo 'STOP=WRONG_DATABASE'; exit 1; }
OUTDIR='/home/ubuntu/sbi-db-management/db-r31-central-catalog'
mkdir -p "$OUTDIR"
chmod 700 "$OUTDIR"
OUT="$OUTDIR/DB_R31_SCHEMA_DIFF_AND_TABLE_MAP.txt"
sudo -n -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -d "$DB" -f "$HERE/db_r31_catalog_probe.sql" > "$OUT"
chmod 600 "$OUT"
grep -qx 'DB_R31_CATALOG_END|READ_ONLY' "$OUT" || { echo 'STOP=READ_ONLY_CATALOG_INCOMPLETE'; exit 1; }
echo 'DB_R31_READ_ONLY_CATALOG=PASS'
echo "DB_R31_EVIDENCE_FILE=$OUT"
for category in SCHEMA COLUMN CONSTRAINT INDEX REPORT_ROLE OWNER_FIELD; do
 echo "DB_R31_${category}_LINES=$(grep -c "^${category}|" "$OUT" || true)"
done
grep '^OWNER_FIELD|' "$OUT" || true
grep '^GLOBAL_FILE_SHA_UNIQUE|' "$OUT" || true
grep '^REPORT_ROLE|' "$OUT" || true
if [[ -f "$HERE/db_r31_catalog_contract.py" ]]; then
 python3 "$HERE/db_r31_catalog_contract.py" "$OUT" --output "$OUTDIR/DB_R31_SCHEMA_DIFF_AND_TABLE_MAP.json"
 echo "DB_R31_FORMAL_MAP=$OUTDIR/DB_R31_SCHEMA_DIFF_AND_TABLE_MAP.json"
fi
echo 'DB_R31_PRODUCTION_FINANCIAL_WRITES=NONE'
echo 'DB_R31_SCHEMA_MIGRATION=NOT_EXECUTED'
echo 'DB_R31_RELEASE_STATUS=DESIGNED_CATALOG_COLLECTED'
