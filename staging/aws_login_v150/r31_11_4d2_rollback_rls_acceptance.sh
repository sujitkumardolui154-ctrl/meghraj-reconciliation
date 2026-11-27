#!/usr/bin/env bash
# R31.11.4D2: private QA only; read-only pre/post checks; SQL never commits.
set -euo pipefail
PG=sbi-r3114-private-postgres
NET=sbi-r3114-private-isolated
DB=sbi_r31_11_4_auth_qa_20261126
SQL=$(dirname -- "$(readlink -f -- "$0")")/r31_11_4d2_rollback_rls_acceptance.sql
fail() { printf 'STOP=DB_R31_11_4D2_%s\n' "$1"; exit 2; }
[ -f "$SQL" ] && [ ! -L "$SQL" ] || fail SQL_SOURCE_INVALID
if grep -Eq '^[[:space:]]*COMMIT[[:space:]]*;' "$SQL"; then
  fail SQL_CONTAINS_COMMIT
fi
[ "$(sudo -n docker network inspect "$NET" --format '{{.Internal}}')" = true ] || fail NETWORK_NOT_INTERNAL
[ "$(sudo -n docker network inspect "$NET" --format '{{.Attachable}}')" = false ] || fail NETWORK_ATTACHABLE
[ "$(sudo -n docker inspect "$PG" --format '{{.State.Running}}')" = true ] || fail PG_NOT_RUNNING
[ "$(sudo -n docker inspect "$PG" --format '{{json .HostConfig.PortBindings}}')" = '{}' ] || fail PG_PUBLIC_PORTS
[ "$(sudo -n docker inspect "$PG" --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}')" = "$NET" ] || fail UNEXPECTED_PG_NETWORK
readonly_empty() {
 sudo -n docker exec "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$DB" -c "
BEGIN READ ONLY;
SELECT CASE WHEN current_database()='$DB'
 AND (SELECT count(*) FROM sbi.import_batches)=0
 AND (SELECT count(*) FROM sbi.payment_source_rows)=0
 AND (SELECT count(*) FROM sbi.payments)=0
 AND (SELECT count(*) FROM sbi.payment_source_status_v1)=0
 AND (SELECT count(*) FROM r311_auth.role_owner_map)=2
 THEN 'PASS' ELSE 'FAIL' END;
COMMIT;"
}
BEFORE=$(readonly_empty) || fail PRECHECK_READ_ERROR
[ "$BEFORE" = PASS ] || fail PRECHECK_EXISTING_DATA
echo DB_R31_11_4D2_BEFORE_DATA_EMPTY=PASS
RC=0
sudo -n docker exec -i "$PG" psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$DB" -f - < "$SQL" || RC=$?
# Reconnect independently on every SQL outcome. Transaction rollback is
# automatic on disconnect even if the SQL failed before explicit ROLLBACK.
AFTER=$(readonly_empty) || fail POSTCHECK_UNAVAILABLE_REVIEW
[ "$AFTER" = PASS ] || fail POSTCHECK_RESIDUAL_DATA_REVIEW
echo DB_R31_11_4D2_AFTER_DATA_EMPTY=PASS
[ "$RC" -eq 0 ] || fail IN_TRANSACTION_ASSERTION_FAILED
echo DB_R31_11_4D2_RELEASE=QA_ISOLATION_ONLY_PRODUCTION_BLOCKED
echo DB_R31_11_4D2_RUNTIME_ADAPTER=NOT_DEPLOYED_BY_TEST
echo DB_R31_11_4D2_FINANCIAL_APPLY=LOCKED
echo DB_R31_11_4D2_R3112=QUARANTINED
