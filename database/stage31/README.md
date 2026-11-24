# SBI Stage 31 — PostgreSQL Database Update Integration

**State:** DEVELOPMENT / QA — NOT PRODUCTION WRITES. One central PostgreSQL database: `sbi_reconciliation_main` on AWS Lightsail. Production read-only reporting remains active. No additional database engine is to be created.

## Evidence and source contracts examined

- `backend_source/invoice_source_schema.py`: exact original `Invoice Details.` 34-column and 35-column layouts (35 includes an additional `Branch Code` at position 9); approved 53-column source layout. The invoice-number field is text at index 9, 10 or 12 respectively, zero based. Preserve the original columns and exact labels, including source misspellings.
- `backend_source/invoice_import_rules.py`: existing invoice IDs, repeat IDs within the uploaded file and missing/invalid invoice keys must be rejected. No deduplication by removing rows or silently overriding values.
- `backend_source/invoice_excel_parser.py`: source workbook validation for .xls/.xlsx, cached Excel formulas, exact headers and a bounded row count; it currently references the older Firestore import workflow. Some source model fields are synthetic and must never be treated as verified payments.
- `backend_source/invoice_import_store.py` and `invoice_import_apply.py`: **Firestore** persistence/transactions. These do not establish a working writer for central AWS PostgreSQL.
- Existing `sbi.invoice_financial_summary` and `sbi.payment_financial_summary` are **read-only** reporting views. The production `sbi_pr129_report_login` must never receive financial table INSERT/UPDATE/DELETE.
- Historical PAYMNENT Excel: original column I = Credit; original A–L fields are protected against edits. This does not yet provide an approved, unique bank transaction identity for duplicate-safe PostgreSQL ingestion.

## Stage 31 gates

| Gate | Work | Write permission |
|---|---|---|
| **31.1** | Read live catalog, constraints, privilege matrix, PostgreSQL counts and production anonymous security gate. Run offline approved invoice layout + payment evidence tests. | None |
| **31.2** | Design exact mapping of 34/35/53 invoice fields and payment-bank source columns to actual PostgreSQL columns, preserving source workbook + row ID + SHA-256. All unmapped or ambiguous fields flagged; no invented SOL IDs. | None |
| **31.3** | Implement isolated PostgreSQL ingestion adapter, transaction-safe and duplicate-safe, with receipt table, idempotency keys, reject audit, commit/rollback parity and full synthetic combined QA. | Disposable isolated database only |
| **31.4** | Authenticated isolated private dashboard upload/preview/apply integration, without exposure on live Caddy routing. Validate invoice row identity, SOL master mapping, amount/date typing and bank source identity. | Private nonproduction only |
| **31.5** | Owner review and **separate explicit approval** before any central production write grant or live upload activation. Financial Engine remains a separate Stage 32. | Blocked until approved |

## Payment intake contract — review only

New fixed minimal staging sheet headers are exactly `Description`, `SOL ID`, `Credit Amount`. Each cell is stored as text; SOL leading zeros are preserved; credit must be a positive finite decimal with at most 2 decimal places. Invalid or repeated evidence is rejected for review, not automatically reconciled. Three fields alone are insufficient for bank-ledger identity: include original source file SHA, source sheet/row and verified bank transaction ID/date before designing a final idempotency key or production writer. Original PAYMNENT 12-column conversion must be separately source-verified; do not silently assume an arbitrary upload's column I represents Credit.

## Mandatory security

- Preserve existing Firebase session authentication and CSRF protections for POST operations.
- Separate `sbi_ingest_runtime` role (non-login) from `sbi_report_reader` and `sbi_engine_runtime`; no superuser, schema owner or engine role in the web app.
- No access to production write credentials from client browser, logs, GitHub or Google Drive.
- No reconciliation allocations, changes to existing invoices, settlement updates or credit note processing in Stage 31.
- No new Caddy routes, Docker deploy, privilege grant, database migration or production write until a later gate and explicit owner approval.
- Stage 31.1 script is introspection only; it intentionally reports the actual live column/constraint metadata to the owner for mapping. It does not output invoice row values.

## Evidence status

Stage 31.1 source code prepared in GitHub. Execution status pending the owner's AWS Lightsail terminal output. Do not label Stage 31 integration PASS or LIVE until all applicable gates above have passed.

## Database Management R31 payment requirements handoff (24 Nov 2026)

Owner's R31 follow-on requirements are now published in [`DBMGMT_R31_CENTRAL_PAYMENT_LEDGER_AND_SOL_REPORT_HANDOFF_20261124.md`](DBMGMT_R31_CENTRAL_PAYMENT_LEDGER_AND_SOL_REPORT_HANDOFF_20261124.md). They instruct this **existing central PostgreSQL** workstream to integrate approved three-column payment uploads, per-row exclusion, SOL-to-official-branch mapping, fresh-invoice engine input and SOL-wise source/matched/not-calculated reports. Reuse Stage 31 / FT-04 relationships; do not promote R31's SQLite payment ledger into a second authoritative business database. This is a requirements handoff only; no database migration, live AWS release or financial writer activation.
