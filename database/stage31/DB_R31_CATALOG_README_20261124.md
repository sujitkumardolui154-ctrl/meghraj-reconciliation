# DB-R31.1 — Existing central PostgreSQL catalog and source mapping

**Status:** Development source prepared; **AWS central catalog execution pending.** This is the requested next implementation step for [Database Management Issue #190](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/190) and the binding `DBMGMT_R31_CENTRAL_PAYMENT_LEDGER_AND_SOL_REPORT_HANDOFF_20261124.md` on `sbi-central-postgresql-main-20261121`.

## What this delivers

- `db_r31_catalog_probe.sql` — executes all metadata SELECT statements in a single **`BEGIN READ ONLY`** transaction against **existing** `sbi_reconciliation_main`. Reports table/column/constraint/index metadata, owner/tenant scope, existing branches/allocations/report views and read-only reporting role grants. Does not read invoice/payment/branch data rows.
- `db_r31_catalog_run.sh` — short AWS runner using local `sudo -n -u postgres psql`; fails if database identity is not central; emits a private 0600 metadata record under `/home/ubuntu/sbi-db-management/db-r31-central-catalog/`.
- `db_r31_catalog_contract.py` — converts captured metadata into a JSON **`DB_R31_SCHEMA_DIFF_AND_TABLE_MAP`** crosswalk for `Description | SOL ID | Credit Amount`; flags global SHA vs owner-scoped idempotency, any missing lineage fields, report write grant risk, and **never authorizes production writes**.
- `test_db_r31_catalog_contract.py` — synthetic parser checks, including wrong DB, incomplete scan, missing owner, missing amount, and unexpected report write grant.

## Single AWS execution (read-only)

From AWS Ubuntu:

```bash
set -euo pipefail
BRANCH='feature/sbi-db-r31-central-catalog-20261124'
BASE="https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/$BRANCH/database/stage31"
DIR='/home/ubuntu/sbi-db-management/db-r31-central-catalog/source'
mkdir -p "$DIR" && chmod 700 "$DIR"
for name in db_r31_catalog_probe.sql db_r31_catalog_run.sh db_r31_catalog_contract.py test_db_r31_catalog_contract.py; do
 curl -fsSL "$BASE/$name" -o "$DIR/$name"
done
bash -n "$DIR/db_r31_catalog_run.sh"
PYTHONPATH="$DIR" python3 -m unittest -q test_db_r31_catalog_contract
bash "$DIR/db_r31_catalog_run.sh"
```

For a SHA-pinned run, use `git clone --branch ...` plus `git rev-parse HEAD` or the exact release commit before execution, rather than relying on the mutable branch URL. Do not publish credential files, original financial rows, or the private approved SOL master.

The runner prints `DB_R31_READ_ONLY_CATALOG=PASS`, owner-scope and global-SHA findings, report-role grant matrix, output file paths, and `DB_R31_RELEASE_STATUS=DESIGNED_CATALOG_COLLECTED`. The full JSON is private on the AWS host. **Do not paste customer/financial data**, only the metadata status lines.

## Implementation gates after the read-only catalog

1. **DB-R31.2**: Build a reviewed, reversible additive migration **only for genuinely missing central owner/receipt/review lineage**, considering replacement of any global-SHA unique constraint with owner-scoped idempotency. That constraint cannot be safely altered by a blind additive `ALTER TABLE`.
2. **DB-R31.3**: Isolated QA migration and rollback with source immutability, per-row accepted/excluded evidence and concurrent owner replay; keep FT-04 QA hard-coded target guard.
3. **DB-R31.4**: Real Firebase/CSRF owner authenticated private staging, approved versioned SOL branch master and read-only central SOL-wise report/CSV parity.
4. **DB-R31.5/6**: Verified engine/allocation handoff and explicit owner approval for scope of actual central financial source writes.

**NO_NEW_PRIMARY_DB; NO_PRODUCTION_SCHEMA_MIGRATION; NO_FINANCIAL_WRITES; NO_AUTOMATIC_RECONCILIATION.** This branch should target `sbi-central-postgresql-main-20261121`, not production `main`, until reviewed.
