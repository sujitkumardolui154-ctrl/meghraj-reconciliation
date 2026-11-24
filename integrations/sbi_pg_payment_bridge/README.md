# SBI staging payment evidence → PostgreSQL integration (24 November 2026)

**Scope:** separate QA image only. This is not a production deployment. The live AWS app, Caddy routes and PostgreSQL production database remain unchanged.

`install_aws_staging.sh` clones the feature branch, builds an overlay from the live AWS Docker image, imports the original Flask app and replaces only its **registered** `POST /api/payment-evidence/upload` view with a wrapper. This preserves original session, owner identity, same-origin CSRF, 8-MiB XLSX parsing, SQLite receipt and original duplicate-check implementation. After a successful SQLite receipt, it writes the evidence into the isolated PostgreSQL database via an insert-only role. On an already-staged SQLite receipt, a duplicate POST can repair an interrupted PostgreSQL delivery while preserving HTTP 409.

Safety conditions are hard-coded: `PGHOST=sbi-synthetic-postgres-38-31`, `PGDATABASE=sbi_ft04g_clean_0e858f93`, `PGUSER=sbi_ft04q_ingest`, `SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only`. The adapter also checks its database identity and no UPDATE/DELETE privileges. It cannot be enabled against the production database. No financial allocations or reconciliation run.

The adapter reads *all* source rows from the original XLSX, verifies the existing parser's accepted row count, keeps original source row numbers, hashes raw file and individual JSON source-row representations, converts payments to exact paise and commits linked `import_batches` → `payment_source_rows` → `payments` records in one transaction. Unique constraints and immutability are retained. Existing identical batches are verified against every original source row and returned as `ALREADY_RECORDED`. A conflicting batch fails closed.

For the current staging candidate **any parser-review rows stop PostgreSQL ingestion**, leaving the original SQLite receipt for review; this prevents guessing which rows the original parser accepted. The requested production behavior of excluding *only invalid rows* needs an exact row-level parser status contract before enabling actual uploads. This is an explicit gap, not a release-ready partial-acceptance implementation.

Because SQLite and PostgreSQL have separate transactions, an error after a successful SQLite receipt yields `503 PG_STAGE_SYNC_PENDING`. Re-upload of the same authenticated file reaches the original SQLite 409 and can retry the PostgreSQL write. A durable outbox/monitor for non-retried receipts is still required before production.

The temporary staging app is isolated on a Docker internal network without published host ports, mounts no production socket or production secrets, and uses temporary SQLite receipt storage. It does not prove Firebase login or live report API behavior. See `install_aws_staging.sh` for the staging-only build and import command.

## Local verification

The file `test_bridge.py` exercises basic XLSX cells, shared strings, formula rejection, zero amount and decimal precision. These are not a replacement for AWS integration tests.

## Release blockers (do not bypass)

1. Exact staging Firebase authenticated Flask route test with persistent, non-production SQLite storage.
2. Existing PostgreSQL reporting route parity using the dedicated report role.
3. Row-level invalid-only exclusion contract, durable outbox/recovery for mismatched SQLite and PostgreSQL transactions, and production-specific database permissions, followed by explicit cutover approval.
