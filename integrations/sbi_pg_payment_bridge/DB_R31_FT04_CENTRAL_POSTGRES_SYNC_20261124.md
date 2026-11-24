# DB Management R31 ↔ FT-04: binding PostgreSQL integration crosswalk

**Handoff dated:** 2026-11-24 IST. **Authoritative source:** [Issue #190](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/190), [full Stage 31 handoff](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/blob/sbi-central-postgresql-main-20261121/database/stage31/DBMGMT_R31_CENTRAL_PAYMENT_LEDGER_AND_SOL_REPORT_HANDOFF_20261124.md), branch `sbi-central-postgresql-main-20261121`, published commit `31be42e021a983c04c40611fbb9312cfe0cd4d79`. Related R31 UI/report work [PR #188](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/188); staging bridge [PR #186](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/186).

## Binding authority: NO_NEW_PRIMARY_DB

- The **only authoritative production business/payment database** is existing central AWS PostgreSQL `sbi_reconciliation_main`, schema `sbi`. Never create another production payment ledger in SQLite or another PostgreSQL database. R31 SQLite `payment_received_evidence_v1` can be a receipt/source and migration input, **not** a competing business source of truth.
- FT-04 `sbi_ft04g_clean_0e858f93` and `sbi_ft04q_ingest` are **isolated QA**, not alternative primary infrastructure. **Never** repoint the FT-04 hard-coded QA host/database/writer to central production by replacing strings; require reviewed owner-scoped additive migration, production-specific credentials and distinct approval of central source-write scope.
- Original authenticated Flask identity, CSRF/Origin rules, immutable private file and owner-specific receipt are authoritative; private SQLite outbox retries **source ingestion only**. Upload credit is not a bank settlement or reconciliation match; full Master v2.51 / Matrix v2.39 allocation engine is not connected by this bridge.

## Source → central PostgreSQL contracts

| Exact source / state | Staging evidence | Required central DB mapping / gap |
| --- | --- | --- |
| Server-side `g.dil_user.uid` | Private owner-scoped receipt and outbox | Verify/add owner-scoped `import_batches` identity, unique owner+source kind+file SHA and authorized tenant filtering; **global SHA is insufficient** |
| Original fixed XLSX headers | `Description`, `SOL ID`, `Credit Amount` | Preserve original file SHA, filename, receipt ID, source worksheet, original Excel row and exact raw values; historical `PAYMNENT` source A:L / Credit I is a **different** contract |
| Original narration | `sbi.payments.description`, source JSON | Preserve verbatim; do not invent UTR or bank date |
| Original SOL text | `sbi.payments.sol_id`, source JSON | Preserve literal zeros (`001505`), digits-only Excel TEXT; derived canonical SOL only for matching and verified approved SHA-pinned master lookup. SBISA SOL `1` special. Never guess branch names |
| Positive credit | `credit_paise` exact signed integer, raw text in evidence | Max two fractional decimals, no zero/negative/non-finite candidate; credit is **not allocated amount** |
| Source row | `sbi.payment_source_rows` FK to `sbi.import_batches` | Keep immutable `row_sha256`, `source_row_number`, source evidence, original receipt and owner; add/associate invalid/held rows and reasons centrally (not only in outbox) |
| Status / engine run | Existing QA source-only, no allocation | Versioned `PENDING_RECONCILIATION`, `HOLD_SOL_MASTER`, `HOLD_DUPLICATE_CANDIDATE`, `EXCLUDED_INVALID_SOURCE`, parser/master version, actor, timestamps; `MATCHED` only after separately verified engine allocation |
| Duplicate | Same-owner original receipt SHA idempotent | Same narration+SOL+amount **across different files** may be genuine distinct payments: review as duplicate candidate, do not silently delete/conflate |

**Important current limitation:** The verified FT-03 QA schema has global `(source_system,source_kind,source_sha256)` uniqueness without verified owner scope. FT-04 now **fails closed for a second owner per QA installation**, including a different SHA, with serialized SQLite `BEGIN IMMEDIATE`. The test role is deliberately unable to write to central production. This is **not** multitenant readiness.

**SOL master:** inspect the current approved private master and version/SHA; treat `3970`, `6884`, `6928`, `99922` as a review queue, not a permanent prohibition. Include latest approved `99922` mapping, CAC location and RBO aliases. Never change immutable original SOL/description/credit when the master changes.

## Reporting and future engine handoff

- R31 routes `/api/payment-received/sol-report`, `/api/payment-received/sol-report.csv` and `/api/payment-received/payment-details.csv` must eventually read an **authenticated owner-filtered, versioned central PostgreSQL view/query** rather than a SQLite business ledger.
- Count **distinct** source payment rows per SOL, sum each payment's credit exactly **once**; do not inflate credit by joining allocation rows. Report original narration, raw SOL, verified official branch (or hold), receipt/source row, original credit, excluded/held/uncalculated counts, verified allocation amount and remainder only when actual matching evidence exists.
- While the real engine has not run, show `NOT_CALCULATED` not `UNMATCHED_AFTER_RUN`; `MATCHED` and `PARTIALLY_MATCHED` require independent persisted allocation evidence. Report CSV exports must neutralize formulas beginning `=`, `+`, `-`, `@`.
- Fresh-invoice matching can only consume owner-scoped saved payment IDs and verified original invoice rows, protect `Invoice Details.` original S nonblank and version source service Month/tax/GST/credit-note/previous allocations. No fabricated engine completion.

## Mandatory Database Management deliverables — pending, not silently inferred

1. `DB_R31_SCHEMA_DIFF_AND_TABLE_MAP`: **read-only live central catalog** including owner keys, role matrix, existing schema/branch master/index/view/report and allocation relationships. FT-03 QA is not proof of production catalog.
2. `DB_R31_APPROVED_SCHEMA_MIGRATION`: reversible additive SQL only for missing owner/receipt/review/verified SOL fields; isolated migration and rollback; **NO_NEW_PRIMARY_DB**.
3. `DB_R31_INGEST_OUTBOX_PARITY`: accepted+review counts/amounts, invalid source retention, exact owner-scoped SHA, concurrent uploads, crash/retry replay, original immutability.
4. `DB_R31_SOL_BRANCH_MAPPING`: approved master version/SHA, official labels and unresolved/conflicted SOL list.
5. `DB_R31_SOL_TALLY_REPORT_PARITY`: owner-scoped summary/detail CSV and credit/allocated parity, no false matches.
6. `DB_R31_RELEASE_STATUS`: `DESIGNED | ISOLATED_QA_PASS | AUTHENTICATED_STAGING_PASS | PRODUCTION_WRITE_SCOPE_APPROVED | DEPLOYED`, code SHA and operator deployment receipt.

**Status:** Requirements synchronized; local FT-04 regression coverage for strict SOL TEXT and single-owner QA guard. Historical FT-04 synthetic isolated QA passed; **central catalog/migration, multi-tenant authorization, current private SOL master, Firebase authenticated stage, report parity, real v2.51/v2.39 engine and production financial-source writes remain unverified/not authorized**. Do not merge or deploy this draft bridge to production.
