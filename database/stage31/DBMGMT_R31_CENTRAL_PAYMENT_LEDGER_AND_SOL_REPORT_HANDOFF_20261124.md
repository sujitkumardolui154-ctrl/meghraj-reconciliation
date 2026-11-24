# DB Management handoff — R31 payment receipt ingestion into existing central PostgreSQL

**Owner request:** 24 November 2026 (IST)  
**Workstream:** SBI Database Management → Stage 31 / FT-04 / upcoming Stage 32  
**Status:** REQUIREMENTS HANDOFF ONLY — NO DATABASE MIGRATION, ROLE GRANT, FINANCIAL ALLOCATION OR LIVE DEPLOYMENT

## 1. Binding architecture decision

**Use the existing AWS Lightsail central PostgreSQL database `sbi_reconciliation_main` as the authoritative payment/business-data store.** Do NOT create a second business PostgreSQL database or promote the R31 SQLite payment ledger as the primary source of payment records.

The existing private, immutable upload-file/SQLite receipt and FT-04 outbox may remain as evidence and reliable-delivery infrastructure; they must NOT become an independently mutable, conflicting business ledger.

Reference sources (inspect code/schema before implementation):
- Database branch `sbi-central-postgresql-main-20261121`: `database/stage31/README.md`, `STAGE31_4_INTEGRATION_README.md`, `STAGE31_4B_REAL_AUTH_PREFLIGHT.md`, `stage31_2_schema_design.py`, `payment_evidence_contract.py`.
- FT-04 draft staging bridge, PR #186: `integrations/sbi_pg_payment_bridge/sbi_payment_pg_bridge.py`, `sbi_pg_outbox.py`, `outbox_worker.py`. This bridge targets only `sbi_ft04g_clean_0e858f93` and uses `sbi_ft04q_ingest` — **DO NOT repoint this QA implementation at the production DB by editing constants**.
- R31 merged application work, PR #188 (development branch `feature/sbi-payment-reconciliation-readiness-gate-20261120`): `staging/aws_login_v150/payment_received_ledger.py`, `payment_received_reports.py`, `prepare_private_sol_master.py`, and `dashboard_source/index.html`. Adapt its UI/report requirements to central PostgreSQL; the R31 SQLite payment rows are **non-authoritative** after central ingestion is integrated.
- Full Master v2.51 / Matrix v2.39 reconciliation engine and verified result writer are NOT claimed to be connected to R31/FT-04; do not invent results.

The source may already contain real tables, roles, relationships, indexes and RLS/views. **First inspect the actual live catalog read-only** and make an additive migration only where fields/constraints are demonstrably absent. Proposed column names below are contracts, not claims that those columns currently exist.

## 2. Owner-approved payment upload UX/source contract

Existing Database Update tab → Payment Reconciliation → **Upload New Payment Evidence**, fixed header order (unchanged):

| Excel ordinal | Header EXACTLY | Requirement |
| --- | --- | --- |
| A | `Description` | Original bank narration text, preserved verbatim as evidence |
| B | `SOL ID` | Excel TEXT containing digits; preserve literal leading zeros and SOL `1` / SBISA semantics |
| C | `Credit Amount` | Positive INR amount; finite, maximum two fractional decimals; calculate in integer paise |

An upload is **payment evidence received into the system**, not proof of bank settlement and not a reconciliation match. Maintain original filename, raw-file SHA-256, receipt ID, original worksheet, source Excel row, raw original values and parse/review flags. No source-row deletion or silent correction. Historical `PAYMNENT` original A–L is protected (original Credit = **I**); the three-column template is a different ingestion contract and contains no verified UTR/transaction date. On fresh invoice uploads, the reconciliation engine must obtain eligible stored payments through a controlled read adapter, not browser-injected summaries.

## 3. Map onto EXISTING `sbi` PostgreSQL records

FT-04 currently stages into these related relations; verify actual production catalog before binding:

```text
sbi.import_batches
      id, source_system, source_kind, original_file_name, source_sha256, ...
                   |
                   v
sbi.payment_source_rows
      id, batch_id, source_row_number, original_values, row_sha256, ...
                   |
                   v
sbi.payments
      id, source_row_id, description, sol_id, credit_paise, ...
                   |
                   +-- approved SOL branch identity (lookup/view)
                   +-- independently verified reconciliation allocation (future Stage 32)
```

**Required database-team additions, ONLY if missing after catalog verification:**

1. **Owner-scoped immutable receipt/source identity**: enforce unique submitted file/receipt within owner or tenant scope, and source row uniqueness `(batch_id, source_row_number)`. Preserve `source_sha256` and `row_sha256`, reference exact original byte content held in private immutable evidence store. Clarify whether `import_batches` already records owner UID; if not, add a safe owner/tenant linkage. Do not assume globally identical SHA is duplicate across different owners.
2. **Source-row review status and reasons**: attach or associate `PENDING_RECONCILIATION`, `HOLD_SOL_MASTER`, `HOLD_DUPLICATE_CANDIDATE`, `EXCLUDED_INVALID_SOURCE`, plus machine-readable reason codes, source parser version, verification timestamp and user/source attribution. Preserve every invalid row's evidence even when it does not create an eligible `sbi.payments` record.
3. **Amount semantics**: use exact integer `credit_paise` with raw original amount text retained. Source credit is not an allocated amount. Null/invalid/zero/negative/nonfinite amounts must not enter eligible payment candidates.
4. **SOL identity**: preserve `sol_id` literal string and a separately derived canonical lookup key (leading zeros stripped ONLY for matching). Link to a verified branch master identity and master version/digest, rather than guessing an official name or rewriting the original SOL. A source `99922` mapping or alias changes must reflect the latest owner-approved master. Ambiguous/unknown/unapproved SOLs are kept for review, not silently assigned.
5. **Auditable duplicate/event policy**: same description/SOL/amount can be a legitimate separate payment. Use exact receipt/file/row lineage for ingestion idempotency; mark possible repeated cross-file evidence for review until a genuine bank event identity is verified. Do not delete or overwrite past events to force a tally.
6. **Read-only reporting projection**: create or adapt a versioned, access-controlled SQL view/query for SOL-wise payment source status, mapped branch, amount totals and later independently verified match status; do not grant the existing reporting role table writes.
7. **Future engine result tables**: use existing engine/allocation records if already designed, otherwise draft an additive relational link of `payment_id` ↔ `invoice_id` ↔ `reconciliation_run_id` with allocated paise, method/rule version, evidence refs, idempotency and audit history. **Do not insert fake matched/settled rows while the real v2.51/v2.39 engine is disconnected.** Approval of a reporting view alone does not authorize settlement.

No wholesale replacement of existing tables and no duplicate `payment_received_evidence_v1` business ledger in a separate SQLite file.

## 4. Upload persistence and reliable delivery

- Keep the original Firebase-authenticated Flask endpoint, Origin/CSRF checks, owner/tenant access and approved three-column parser. Never trust an arbitrary client-supplied owner UID, branch name, allocation or bank status.
- Persist the original immutable file + durable receipt/outbox; deliver each eligible row to central PostgreSQL using a narrowly scoped **INSERT-only source-ingestion role**. Preserve separate `sbi_pr129_report_login` / reporting and engine roles; do not grant finance DELETE, UPDATE, settlement or schema-owner permissions to the upload app.
- Use FT-04's staged transactional `import_batches` → `payment_source_rows` → `payments` pattern as a starting point, with atomic PostgreSQL commit/rollback, unique constraints and retriable outbox acknowledgement **only after DB commit**. A crash after the file receipt but before PostgreSQL delivery must recover safely and idempotently.
- **Owner-approved row-level elimination:** incorrect/invalid payment rows are individually rejected from calculation; valid independent rows are still recorded/processed. Ensure source accepted+review counts and exact accepted-credit-paise totals match the original parser. If the overall file/transaction is unsafe or fails integrity verification, stop that ingestion attempt instead of guessing.
- Repeated upload of identical file/receipt should return an idempotent result and not insert a second financial source event; a pending outbox may retry without duplicate payments.
- The production reader must never infer date/UTR from a three-column upload, force `payment_status=OK`, use an unapproved fuzzy SOL/name match, or overwrite protected prior allocations.
- Do **not** convert staging FT-04's hard-coded QA host/database/user to production by a string replacement. Require a reviewed production-specific least-privilege migration, host secret handling and real authenticated isolated staging test.

## 5. Automatic branch name from approved SOL master

Automatic branch name must be resolved **server-side** at upload/read time from the user's approved SBI SOL branch master:
- Original `SOL ID` remains TEXT (including `001505`) and is not automatically rewritten.
- Canonical SOL lookup key is used only to find an **unambiguous approved** official branch identity; preserve master version/SHA, official branch label and a review reason for conflict or missing mapping.
- Aliases must follow approved master corrections, including CAC location rules, RBO aliases and special SBISA SOL `1`; never treat nonunique/partial aliases as definitive.
- The four SOLs previously flagged for private master review (`3970`, `6884`, `6928`, `99922`) must be verified against the CURRENT approved master; this list is a work queue, **not a permanent prohibition**. In particular, source-approved `99922` mapping must not be discarded merely because an older converter held it.
- The official branch name can be stored as a versioned resolved snapshot/foreign key for audit, but the immutable raw bank narration, raw SOL and credit remain unchanged. Changing a master entry must not silently rewrite the original transaction or retroactively change a booked allocation.

## 6. Future fresh invoices + calculation engine handoff

Data consumed by the full reconciliation engine must identify **exact** source payment rows and validated invoice rows, with owner scope and versioned master/method evidence:
- Payment input: `payment_id`, `batch_id`, original source row and SHA, raw SOL, canonical SOL, verified branch, credit paise, eligible/review status, verified event identity if present.
- Invoice input: exact `Invoice No`, approved SOL/client name, service Month (source period, not automatically invoice date), gross/taxable/CGST/SGST in exact paise, source SHA/row and prior paid/protected status.
- Reconciliation methods: actual v2.51 / Matrix v2.39 implementation (including full/partial waterfall, multimonth period, TDS/GST, same SOL, SBISA, exact MXP, DNM review, duplicates/cross-SOL and source-protected previous allocations) must run before any row is marked matched.
- Failed/ambiguous rows are individually excluded/HOLD with reason codes; unrelated eligible candidates continue. `Invoice Details.` original S nonblank is protected from fresh allocation.
- A database **upload receipt** MUST NOT be treated as successful reconciliation. The current source-only report is valid before engine connection, but `MATCHED` requires a saved, independently verified allocation/evidence record.

## 7. New Reports tab — SOL-wise Payment Reconciliation Tally

R31 dashboard contract (reconnect to central PostgreSQL rather than duplicate SQLite):
- SOL ID; official branch name; uploaded payment row count; sum of received credit evidence; payment records **matched** to invoices (verified engine results only); **not calculated**; **excluded invalid**; **held** for SOL/duplicate/method review; total matched/allocated paise and remaining/unallocated paise when real engine runs.
- Distinguish `NOT_CALCULATED` (engine did not run) from `UNMATCHED_AFTER_RUN` (engine ran but found no eligible invoice) and `PARTIALLY_MATCHED`. Do not display unprocessed payments as unmatched or assume `matched=0` proves they failed matching.
- Count distinct payment source rows per SOL, not joined allocation rows; sum per-payment amounts once. A partially allocated payment may link to multiple invoices without multiplying its credit. Report allocation amount separately from payment count.
- Owner-scoped, authenticated read-only API with bounded pagination, a SOL summary and **individual payment details CSV** (description, source row, original receipt, raw SOL, mapped branch, credit, status, exception reason and verified invoice refs where present).
- Enforce no cross-tenant data leakage, least-privilege SQL, parameterized queries, CSV formula-injection escaping, exact paise arithmetic and unchanged financial reporting permissions.
- Existing report endpoints `/api/payment-received/sol-report`, `/api/payment-received/sol-report.csv` and `/api/payment-received/payment-details.csv` may be adapted after inspecting current Flask route/auth registration. Do not expose unprotected routes.

## 8. Database work packages & acceptance tests

| Work package | Database Management implementation | Objective pass evidence |
| --- | --- | --- |
| DB-R31.1 Catalog + crosswalk | Read-only inspect current `sbi` tables, views, constraints, indexes, owner/role privileges, per-user scope and existing reconciliation tables | Exact live schema diff, approved source-to-target field crosswalk, no secret/data dumps |
| DB-R31.2 Additive schema | If needed, versioned owner-scoped source identity, receipt/row flags, approved SOL branch mapping snapshot/version, missing FK/unique constraints | Reversible SQL migration, backup and rollback on isolated DB, no existing financial row changes |
| DB-R31.3 FT-04 central integration candidate | Combine source-preserving R31 with FT-04 outbox and typed row eligibility on isolated PostgreSQL; no duplicate business ledger | Fresh upload persists accepted source rows, invalid rows retained with reasons, replay idempotent, crash/retry recovery |
| DB-R31.4 Real auth and report parity | True Firebase owner + CSRF upload in private staging, dedicated ingest and report roles, map SOL to branch and query payment reports | Unauthorized 401/403, valid owner result, multi-user isolation, summary=detail amounts, historical report parity |
| DB-R31.5 Fresh invoice handoff | Private read adapter to full Master v2.51 / Matrix v2.39 runnable engine and separately verified allocation table | Same-SOL/partial/multimonth/duplicate/credit-note/protected previous allocation regression; no fictitious matched counts |
| DB-R31.6 Controlled activation | Plan additive release, independent backups/restore, data migration if any, before/after count+hash parity, rollback, monitor pending outbox | Signed-off operator deployment receipt, exact code SHA, database/role status, explicit source-data write scope approval |

Mandatory negative tests: wrong source header; Excel numeric SOL with lost zeros; empty/negative/excess-decimal credit; malformed or formula cells; unknown/duplicate SOL; duplicate workbook SHA and repeated cross-file candidate; mixed valid/invalid rows; app crash between receipt and PG; two simultaneous uploads; unauthorized owner; report-only role attempting INSERT; bank source date/UTR absent; repeat run with protected allocations; partial paid invoice; two payments for same SOL; one payment to multiple invoices; report joins without double counting; unsafe CSV leading `=`, `+`, `-`, `@`; failure/rollback and unchanged prior financial rows.

No separate formal Finance *certification* is required for deploying calculation and reporting software, per owner directive R28. This does **not** authorize turning on actual central financial table writes before technical validation and the owner's explicit release decision for the write scope.

## 9. Handoff output requested from Database Management

Please return, through the Database Management development workstream:
1. **`DB_R31_SCHEMA_DIFF_AND_TABLE_MAP`** — live catalog vs proposed additions, exact column names, indexes, FK, views, role matrix and branch-master integration;
2. **`DB_R31_APPROVED_SCHEMA_MIGRATION`** — reversible SQL and isolated QA evidence; explicit `NO_NEW_PRIMARY_DB`;
3. **`DB_R31_INGEST_OUTBOX_PARITY`** — source accepted/excluded totals, idempotency, commit/rollback, owner scope, error recovery;
4. **`DB_R31_SOL_BRANCH_MAPPING`** — approved SOL master version and unresolved identity list;
5. **`DB_R31_SOL_TALLY_REPORT_PARITY`** — source rows vs SOL groups vs detail, no false matched classifications;
6. **`DB_R31_RELEASE_STATUS`** — `DESIGNED | ISOLATED_QA_PASS | AUTHENTICATED_STAGING_PASS | PRODUCTION_WRITE_SCOPE_APPROVED | DEPLOYED`, with exact commit SHA and independent AWS runtime evidence.

**Current handoff status:** `REQUIREMENTS_PUBLISHED`. This document makes **no** claim that Stage31.5, FT-04 production DB writes, the complete allocation engine, AWS staging host authentication or live deployment has passed.
