# SBI staging payment evidence → PostgreSQL integration (24 November 2026)

**Scope:** separate QA image only. This is not a production deployment. The live AWS app, Caddy routes and PostgreSQL production database remain unchanged.

`install_aws_staging.sh` clones the feature branch, builds an overlay from the live AWS Docker image, imports the original Flask app and replaces only its **registered** `POST /api/payment-evidence/upload` view with a wrapper. This preserves original session, owner identity, same-origin CSRF, 8-MiB XLSX parsing, SQLite receipt and original duplicate-check implementation. After a successful SQLite receipt, it writes the evidence into the isolated PostgreSQL database via an insert-only role. On an already-staged SQLite receipt, a duplicate POST can repair an interrupted PostgreSQL delivery while preserving HTTP 409.

Safety conditions are hard-coded: `PGHOST=sbi-synthetic-postgres-38-31`, `PGDATABASE=sbi_ft04g_clean_0e858f93`, `PGUSER=sbi_ft04q_ingest`, `SBI_PG_PAYMENT_BRIDGE_ENABLED=staging-only`. The adapter also checks its database identity and no UPDATE/DELETE privileges. It cannot be enabled against the production database. No financial allocations or reconciliation run.

The adapter reads *all* source rows from the original XLSX, verifies the existing parser's accepted row count, keeps original source row numbers, hashes raw file and individual JSON source-row representations, converts payments to exact paise and commits linked `import_batches` → `payment_source_rows` → `payments` records in one transaction. Unique constraints and immutability are retained. Existing identical batches are verified against every original source row and returned as `ALREADY_RECORDED`. A conflicting batch fails closed.

**Historical v1 behavior:** A parser-review row blocked the whole PostgreSQL import. **Current staging v2 behavior:** Eligible and rejected rows are separately classified and rechecked against the original parser's accepted count, rejected count and exact amount totals. Eligible rows may be persisted, while original rejected-row evidence and reasons remain in the private outbox. Unresolvable classifications fail closed. Central production row-level evidence/status mapping is **not** yet approved.

Because SQLite and PostgreSQL have separate transactions, an error after a successful SQLite receipt yields `503 PG_STAGE_SYNC_PENDING`. The staging v2 **durable SQLite outbox and worker** can retry the delivery and recover a verified source receipt after a crash without a repeat browser upload. Production-grade owner-scoped central delivery, recovery monitoring and alerting remain pending.

The temporary staging app is isolated on a Docker internal network without published host ports, mounts no production socket or production secrets, and uses temporary SQLite receipt storage. It does not prove Firebase login or live report API behavior. See `install_aws_staging.sh` for the staging-only build and import command.

## Local verification

The file `test_bridge.py` exercises basic XLSX cells, shared strings, formula rejection, zero amount and decimal precision. These are not a replacement for AWS integration tests.

## Release blockers (do not bypass)

1. Exact staging Firebase authenticated Flask route test with persistent, non-production SQLite storage.
2. Existing PostgreSQL reporting route parity using the dedicated report role.
3. Reviewed owner-scoped central PostgreSQL schema and idempotency (current QA SHA uniqueness is global), durable invalid-source evidence and versioned SOL mapping, authenticated report parity, production-specific roles and explicit owner approval for central financial-source writes.

## FT04 v2 — partial-row eligibility and durable delivery (staging only)

`classify_payment_rows` uses the **existing application's parser** as the source of accepted amounts and review counts. For workbooks containing review rows, it builds isolated one-row XLSX representations of each candidate and re-runs the same parser, preserving the original row number. The eligible row count, review row count, source row count and eligible credit total must all agree with the original full-workbook parser. A mismatch, unsupported structure, or a file with more than 2,000 rows needing individual review fails closed: no guessed financial rows are inserted. Invalid rows are recorded with their source row number and reason in the private outbox, and eligible rows alone are inserted. This is **staging validation**, not yet proof of full historical row-policy parity.

`sbi_pg_outbox.py` adds a SQLite delivery queue with synchronous FULL durability, pending/retry/review/committed states and idempotent SHA-256 keys. `outbox_worker.py` checks for original SQLite receipts whose corresponding immutable `receipt_uuid.xlsx` source file is present and SHA-matches, repairs a crash between original receipt creation and outbox insertion, and retries PostgreSQL delivery without UPDATE or DELETE financial privileges. Successful queue delivery removes the duplicate outbox payload; the original receipt file and database evidence remain. No financial allocations are performed.

`install_aws_staging_v2.sh` creates a **new QA-only image**, a **dedicated persistent private Docker volume** for original SQLite receipts and the outbox, and separate isolated application and delivery-worker containers. It does not modify the existing staging image/container or live application. Only the internal synthetic PostgreSQL network/database/writer are permitted. The original `/api/payment-evidence/upload` route and its real Firebase session/CSRF protections remain authoritative. This installer does not prove real Firebase-authenticated end-to-end behavior, report endpoint parity, or production readiness.

### Before production release

- Run a **real Firebase-authenticated** upload through the isolated v2 service with persistent staging-only credentials, check duplicate handling and the original SQLite receipt response.
- Verify source row-level decisions for workbooks with valid and invalid rows against the actual original parser's flags; review evidence and statuses must reconcile to the approved policy.
- Authenticate and compare all existing database-backed report endpoints, not just raw SQL totals.
- Monitor pending outbox entries, failed attempts, and unrecoverable receipts. Add alerting and production-specific permission review before any cutover.
- Explicitly authorize production rollout; no stage script changes Caddy or enables production financial writes.

## Database Management handoff #190 supersedes production architecture assumptions

Read [DB_R31_FT04_CENTRAL_POSTGRES_SYNC_20261124.md](DB_R31_FT04_CENTRAL_POSTGRES_SYNC_20261124.md), including the authoritative [Issue #190](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/190). The **single central production ledger** is `sbi_reconciliation_main`. FT-04 isolated QA PostgreSQL is not another production ledger, and R31's SQLite payment row ledger is **not** the authoritative business store. Do not change this staging-only bridge's PostgreSQL connection guards to production.

Until Database Management provides reviewed owner-scoped PostgreSQL source identity and deduplication, FT-04's private QA outbox **fails closed for a second distinct user**, including a different source SHA; worker delivery also stops if it finds pre-existing mixed-owner QA records. This is a **single-owner staging limitation, not multi-tenant production support**. Numeric Excel SOL cells are refused/held (potential lost leading zeros); approved original Excel text SOL remains unchanged. Central SOL/branch mapping, finance-source status and versioned reporting still require the Database Management deliverables and real authenticated QA.
