# DB-R31 next implementation: owner-scoped payment source and SOL report adapters

**Source:** Owner's AWS terminal, 25 November 2026: six R31 owner-scope tests PASS, including cross-owner identical SHA, same-owner duplicate rejection, invalid source evidence and SQL totals. The SQL transaction **rolled back** every temporary change and preserved old financial rows and the legacy unique constraint. This is **not** a persistent database migration or production activation.

## Implemented on this development branch

- `db_r31_owner_source_adapter.py` builds a source-evidence plan from the existing fixed-header payment parser's **exact source row numbers and accepted/rejected decisions**. Source-eligible rows have exact integer credit paise; invalid rows retain an original JSON row and `EXCLUDED_INVALID_SOURCE` review code without creating a `payments` event. A row with no independently approved current SOL master is `HOLD_SOL_MASTER`, not guessed. Repeated evidence inside a workbook is `HOLD_DUPLICATE_CANDIDATE`, not automatically settled.
- `persist_qa_source` uses `import_batches` → `payment_source_rows` → `payments` and versioned `payment_source_status_v1` in **one PostgreSQL transaction**. It checks exact original row hashes, owner, file SHA and source amounts on same-owner replay and returns `ALREADY_RECORDED` without changing the old immutable evidence. It does not insert any `MATCHED` or allocation records.
- The adapter **refuses** to run unless connected to the physically isolated QA database as the expected QA ingestion role, with table SELECT/INSERT but no financial UPDATE/DELETE, owner SHA split indexes installed and the original global SHA constraint removed. **These requirements are currently unmet after DB-R31.3 rollback, so the writer is deliberately inactive.** It cannot be made to write to main by changing env vars.
- `db_r31_owner_report_adapter.py` provides server-authenticated owner-filtered read-only SQL/CSV using the already drafted `db_r31_source_report_contract.py`. It requires the QA read-only role and a read-only transaction; no public Flask endpoint has been registered and no report grants changed.

## Remaining required integration, not silently assumed

1. A **persistent, isolated QA** owner-schema migration with separate QA writer role privileges and current FT-04 staging worker compatibility plan. Do not drop the global constraint in the live QA instance while a legacy worker is still writing; either isolate a new disposable QA clone or deliberately stop/migrate the worker first. This QA migration must not be applied to `sbi_reconciliation_main`.
2. Real **Firebase-authenticated** owner+CSRF payment upload that passes source file and receipt IDs **from the server**, plus private original-file archive and outbox acknowledgement after DB commit.
3. Verified, SHA-pinned current SBI SOL branch master lookup, including reviewed SOL `99922`, `3970`, `6884`, `6928` and aliases; do not bind to guessed master.
4. Cross-file similar narration/SOL/amount event identities still need a read-time **owner-scoped duplicate candidate** check. Same wording/amount across files may represent distinct bank events; no automatic deduplication or settlement.
5. Dedicated authorized report-role SELECT on carefully reviewed source-only view, plus true owner isolation policy (possibly RLS/security-invoker) and authenticated SOL summary/details parity; report SQL alone does not provide multitenant database isolation.
6. Full Master v2.51/Matrix v2.39 engine remains disconnected; no upload can assert matched, partially matched, settled, UTR or bank date. Original `Invoice Details.` S nonblank stays protected.

**Release:** `DB_R31_RELEASE_STATUS=SOURCE_ADAPTER_DRAFT`, **not** authenticated staging pass, central production schema approval or production source financial writes. Central `sbi_reconciliation_main` remains the only authoritative business ledger.

## Local tests

`cd database/stage31 && python3 -m unittest -q test_db_r31_owner_source_adapter test_db_r31_owner_report_adapter`

These are offline contract tests. For a PostgreSQL integration result, a later single QA run must exercise the actual owner-scoped schema and both separate roles with no main DB presence.
