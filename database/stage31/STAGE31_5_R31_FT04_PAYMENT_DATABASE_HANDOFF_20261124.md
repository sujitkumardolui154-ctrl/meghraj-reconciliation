# Database Management Handoff — Stage 31.5 / R31 / FT-04

**Date:** 24 November 2026 (IST)  
**Requested by:** SBI Reconciliation Workspace owner  
**Receiving workstream:** Central Database Management — `sbi-central-postgresql-main-20261121`  
**Status:** REQUIREMENTS FOR IMPLEMENTATION AND STAGING QA; **no SQL migration, credential grant, financial posting or AWS deployment is authorized by this document**.  
**Source of truth:** Existing central AWS Lightsail PostgreSQL database `sbi_reconciliation_main`; **do not create a second authoritative database**.

## 0. Decisions and existing evidence

Owner has requested the following application behavior:

- **Database Update:** Upload a fresh payment-evidence Excel in the approved format, store each individual payment so future fresh invoices can be reconciled against saved payments, and automatically show the official branch name for the payment SOL ID.
- **Reports:** Show SOL-wise / branch-wise payment totals, the **number of payments actually matched** after reconciliation, and the **number not calculated**, with individual payment drill-down and exception reasons.
- **Reconciliation:** When an invoice, payment, or proposed pair fails an applicable rule, exclude/HOLD only that affected row/pair. **Do not globally stop valid calculations**. Preserve original source rows.
- **Deployment policy:** A *separate formal Finance certificate* is **not** a prerequisite for deploying valid calculation/report application code; this does **not** bypass authenticated database writes, source integrity, or a separate owner decision before central production payment-write activation.

Read and reconcile these existing sources **before implementing anything**:

1. [Central PostgreSQL Stage 31 README](README.md) — explicitly requires **one central** `sbi_reconciliation_main` database, separate ingest/report/engine roles and Stage 31.5 production-write authorization.
2. [Stage 31.4 integration requirements](STAGE31_4_INTEGRATION_README.md) and [31.4B real-session preflight](STAGE31_4B_REAL_AUTH_PREFLIGHT.md) — private Firebase, CSRF and schema mapping remain separate deployment checks.
3. [Stage 31.2 mapping candidate](stage31_2_schema_design.py) and [three-column payment contract](payment_evidence_contract.py) — source header ordinals and payment contract are already defined.
4. [FT-04 PostgreSQL bridge PR #186](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/186), head `feature/sbi-ft04-payment-postgres-staging-20261124`, especially `integrations/sbi_pg_payment_bridge/{sbi_payment_pg_bridge.py,sbi_pg_outbox.py,outbox_worker.py,README.md}`. It has separate synthetic PostgreSQL QA, transaction-safe rows and durable outbox. Its target is hardcoded to `sbi_ft04g_clean_0e858f93`; **it cannot write `sbi_reconciliation_main` and must not be repointed just by changing an environment variable**.
5. [R31 UI/source ledger PR #188](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/188), merged development commit `ec5f175aad8c3d7897333e48374b00ba0f174328`. See `staging/aws_login_v150/payment_received_ledger.py`, `payment_received_reports.py`, `payment_evidence_upload.py`, `prepare_private_sol_master.py`, `dashboard_source/index.html`, and `docs/SBI_R31_PAYMENT_RECEIVED_SOL_AUTO_MAPPING_AND_REPORTS_20261124.md`. R31 presently persists row-level data to private **SQLite** and reports from it; this is **not the proposed final business-payment source of truth**.
6. [R28 individual exclusion policy PR #183](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/183) — failed source rows or pairs are isolated rather than stopping unrelated candidates; real financial allocations remain separate.

**Branch reconciliation:** Stage 31 central work, FT-04 bridge, and R31 UI changes live on **different branches**. Bring them together in a new review branch based on the central PostgreSQL workstream. Do not simply merge whole unrelated release branches or copy a staging-only SQL target into live configuration.

## 1. Database architecture — mandatory

**One authoritative permanent financial payment store:** the existing `sbi_reconciliation_main` with actual `sbi` schema tables, after independently inspecting live catalog definitions, constraints and privileges.

- Reuse/extend the existing FT-04 relational pattern: `sbi.import_batches` (upload receipt and source SHA-256), `sbi.payment_source_rows` (original Excel row and immutable values), and `sbi.payments` (accepted individual credit event/candidate). **Verify these objects and their actual columns in the central schema before any migration**. They are observed in the FT-04 **QA implementation**, not proof that central production columns have identical types/constraints.
- Treat the original XLSX file and its upload/receipt metadata as immutable source evidence. Existing private SQLite receipt/outbox may remain as a **transport queue / failure-recovery mechanism**, but must **not** be a second source of financial payment truth or a separately tallied live payment ledger.
- Do **not** copy old R31 `payment_received_evidence_v1` and FT-04 `sbi.payments` together and count each payment twice. Develop an **idempotent one-time adoption/migration plan** using authenticated owner, receipt ID, file SHA, worksheet and original row; compare all counts/sums before retiring any shadow rows. Existing read-only reporting and invoice storage must remain unchanged.
- Create versioned, reversible migration scripts **only if the live PostgreSQL schema requires them**; first provide a catalog-driven SQL diff, migration QA in a disposable DB, backup/restore/rollback plan and an explicit release receipt.
- Separate DB roles: an ingest-only role for permitted source-record INSERTs, a read-only reporting role (production `sbi_pr129_report_login` retains no financial INSERT/UPDATE/DELETE), and a separately controlled future engine role for allocations. No common superuser or broad web-app writer grant.

## 2. Input contract and immutable row identity

New standalone payment Excel format is exactly:

| Excel column | Approved header | Required interpretation |
|---|---|---|
| A | `Description` | Original bank narration / service-period evidence |
| B | `SOL ID` | **Excel TEXT** numeric digits; preserve leading zeros in original source |
| C | `Credit Amount` | Positive exact-decimal rupees, at most 2 fractional places; convert to integer **paise** for DB/calculations |

Keep the current authenticated single-`.xlsx` upload and exact header validation. Preserve original **file SHA-256, owner identity, upload receipt, sheet name, original Excel row number, full original values, row digest, source timestamp and validation rule version**. The source row remains recorded even when excluded or held; invalid financial values must **not** be inserted into the eligible financial payments table.

**A three-field workbook does not identify a unique bank transaction.** No bank UTR, value date, bank ledger ID or proof of actual settlement can be invented. File SHA + row prevents same-source replay, but a matching narration/SOL/amount in different files may be either a genuine separate payment or a duplicate. Keep it as a **duplicate candidate for evidence review**, never silently drop two legitimate payments or auto-settle them.

For the *historical* source sheet `PAYMNENT`, original Column I is **Credit** and Column H is **Debit**; original A–L must not be edited. A separate source-header verification/conversion is required before mixing this with the standalone three-column format. Invoice source `Invoice Details.` has approved 34/35/53-column variations; Column S nonblank rows are protected against new allocations.

## 3. Proposed additions to central DB (catalog-dependent; not yet authorized SQL)

Implement the concepts below by reusing existing columns where possible. Do not create duplicate physical tables when existing objects satisfy the contract.

| Logical record | Minimum needed fields / behavior |
|---|---|
| Batch/receipt | Owner/tenant scope, stable receipt ID, original filename (restricted access), file SHA, source format/version, import state, uploaded UTC, accepted/review/excluded row counts, exact original & accepted credit paise |
| Original row evidence | Batch foreign key, worksheet name, Excel row number, exact original `Description`, original SOL text, original credit text, row SHA, parser version, immutable raw values, validation reasons |
| Valid payment source | Source-row FK, description, original SOL text, normalized SOL lookup key, credit paise, source state, matched/remaining allocation derived **from verified ledger only** |
| SOL master relationship | Official branch identity, normalized SOL text key, source master version/SHA, approval state, effective mapping and conflict/alias audit |
| Exclusion/hold evidence | Stable source-row or proposed-match ID, reason code, rule version, reviewer/evidence when available; retained even if another row in same batch passes |
| Verified match/allocation ledger (future Stage 32) | Unique allocation ID, payment source ID, invoice ID, matching method/rule version, allocated paise, original proof reference, run ID, operator identity, UTC, reversal/void tracking; **never generated by payment intake alone** |
| Retry/outbox | Receipt/file SHA + tenant identity, delivery state, attempts, retry timestamps, error code, lease/lock, delivery acknowledgment, replay protection; no raw credentials in log |

**Keys and constraints to review:** unique original row per `(owner scope, source-file SHA, sheet, source-row)`; idempotent batch receipt per owner/source SHA; FK payment→source row; positive finite credit paise; no duplicate allocation ledger entry; indexed (tenant, normalized SOL, status, source row) and (payment ID, allocation run). Source exclusion records must be preserved, not deleted.

**No speculative DDL**: present the real catalog diff and permissions before choosing exact table names, data types, indexes, foreign keys or whether source batches are tenant-scoped in the production database. Maintain invoice source/row uniqueness independently.

## 4. Automatic official branch name from SOL

- Use the existing approved SBI branch master (`SBI_SOL_Branch_Master_FINAL.xlsx`) as an **operator-managed private versioned source**, not something committed publicly to GitHub. The R31 project has a private JSON generator, SHA-pinned loader and existing legacy aliases.
- Exact SOL text must survive ingestion (e.g. `001505`). Normalize `001505` → `1505` **only in the lookup key**; never rewrite or trim the raw uploaded SOL field.
- Resolve branch name automatically only when the approved master gives **one unambiguous, active official branch** for that normalized SOL and correct client context. Store/return master version/SHA and the applied mapping, so old reports can be reproduced after later corrections.
- Unknown, blank, incomplete or conflicting SOL → `HOLD_SOL_MASTER` with original payment preserved and an explicit reason. **Do not guess with fuzzy/surname aliases** or silently use the wrong office.
- Existing reviewed exceptions requiring source-master verification include SOLs `3970`, `6884`, `6928`, `99922`; use the current owner's approved master after rechecking, not a blanket permanent disapproval of these codes.
- SOL `1` / SBISA eligibility and bank customer/client names require the approved rulebook; merely seeing SOL 1 does not prove a reconciled bank transaction.

## 5. Row-level exclusions and independent calculation

**Import is not financial matching.** For each source row independently:

- `SOURCE_ACCEPTED_PENDING_RECONCILIATION`: structurally valid and official SOL resolved, eligible for a **future** engine run.
- `SOURCE_HOLD_MASTER`: official branch unresolved/ambiguous.
- `SOURCE_HOLD_DUPLICATE_CANDIDATE`: plausible replay, pending bank-event identity.
- `SOURCE_EXCLUDED_INVALID`: invalid source cells, impossible or negative/zero credit, unsupported formula/missing required data.
- `SOURCE_SYNC_PENDING` / `SOURCE_SYNC_FAILED`: evidence accepted but PostgreSQL delivery still pending; must not appear as a settled or fully imported payment.

Status names above are a **logical contract**; map them to existing Stage 31/R31/FT-04 enums instead of duplicating columns. Preserve original rejection reasons and row numbers.

**Partial batch policy:** one malformed row must not stop unrelated valid rows being screened or imported, unless the **whole file is structurally unreadable/forged**, the parser's row totals disagree with original evidence, the database transaction cannot guarantee integrity or an authorization gate fails. Record rejected rows and still commit accepted rows/receipt atomically when safe; never alter original XLSX. FT-04 v2's row-isolation reparse and total/count checks are a candidate foundation, not yet evidence of full original-source parity.

A future fresh-invoice run should read only accepted, fully persisted payments from a **read-only engine input adapter** keyed by stable source IDs, join approved invoice/SOL master records and apply Master v2.51/Matrix v2.39. Preserve partial/full payments, service-period matching, GST/TDS, narration and duplicate protections. Do not match a payment based on SOL and amount alone if contradictory narration or protected invoice allocation exists. Reconciliation writer remains a separately implemented, tested scope.

## 6. New SQL-backed SOL-wise / individual payment report

Create an **authenticated, read-only, tenant/role-scoped** report interface consumed by R31 Reports tab (or replace the R31 SQLite query backing it). Required summary dimensions: `normalized SOL ID`, `official branch name`, `payment rows`, `total uploaded credit (paise/rupees)`, `source accepted`, `source held`, `source excluded`, `matched payment count`, `partial-match count`, `not-calculated count`, `calculated-but-unmatched count`, `reconciled/allocated paise` and `unallocated paise`. Provide row-level drill-down by receipt/source row with exception reason and verified matched invoice(s).

**Counting definitions:**

- **Uploaded / Received evidence:** any durable payment source row; not proof of payment matched.
- **Matched:** a payment with an independently **verified** engine match/allocation ledger entry, not merely a source parser PASS or a flagged invoice "OK".
- **Partially matched:** some but not all eligible credit allocated under verified ledger, not counted as fully matched.
- **Not calculated:** no actual engine run has evaluated this persisted payment; source holds may be separately shown within this category (avoid double-counting by presenting a clear mutually exclusive tally plus supplementary held status).
- **Unmatched after calculation:** engine run completed and recorded no valid allocation; not interchangeable with "not calculated".
- **Excluded:** source deemed ineligible by explicit rule; source preserved.
- **Uploaded total:** exact original credit source amount where valid, never derived from Excel float or a client-supplied report subtotal.

**Invariant:** `payment_rows = fully_matched + partially_matched + calculated_unmatched + not_calculated + source_excluded` using a mutually exclusive primary bucket. `held` is a supplementary drill-down count unless separately partitioned. Unallocated balance must account for partials; never classify as fully matched just because one allocation exists. Report historical source receipts already ingested before new feature without automatically assuming calculated. Prevent tenant data leakage, CSV formula injection and pagination count drift.

The R31 current UI routes are `GET /api/payment-received/sol-report`, `/api/payment-received/sol-report.csv`, and `/api/payment-received/payment-details.csv`. Coordinate response fields with the UI team. Match counts must stay **zero / not available** until genuine engine evidence exists; do not fabricate matching numbers.

## 7. API and R31/FT-04 integration boundaries

Provide a **database workstream deliverable**, not a second independent application database:

1. Review production catalog read-only and propose exact DDL diff + mapping. Reconcile Stage31 source schemas with FT-04's existing `sbi.import_batches`, `sbi.payment_source_rows`, `sbi.payments` tables and the R31 source/preview statuses.
2. Implement an append-only, per-row, idempotent PostgreSQL intake adapter in isolated staging. Preserve Firebase identity + real POST CSRF via original application view and a separate least-privilege insert role.
3. Integrate FT-04's durable outbox with the source receipt into an **exactly-once-effect** PG import (idempotent replay; at-least-once delivery). Verify restart/crash recovery, worker retries and deferred delivery visibility.
4. Offer a **read-only** source-payment feed for the complete future v2.51/v2.39 engine when fresh invoices are uploaded, keyed by original receipt/source row; **do not execute financial Apply in the upload handler**.
5. Provide PostgreSQL report query/view + API specification for R31 UI to use, retaining existing public dashboard/Bulk Report behavior and report-reader role permissions.
6. Produce a migration/adoption plan for any R31 SQLite source ledger already populated; check counts, SHA and total credit to avoid duplicates. Do not immediately remove local immutable evidence/outbox.
7. Test actual isolated AWS Flask/Firebase/CSRF and PostgreSQL role boundary before approving a staged write role. No changes to public Caddy or production main are included in this handoff.

## 8. Required combined QA (deliver proof, not only PASS labels)

- **Schema:** inspect real target catalog columns, indexes, FK, triggers, sequences, views and role privileges; record diff. No ALTER/INSERT/UPDATE/DELETE in production during review.
- **Source contract:** exact headers/order; leading-zero SOL; amount decimal paise; narration/service period; 0/1/many row batches; missing/formula/invalid cells; protected original input.
- **Identity:** approved SOL unique mapping; ambiguous codes held; master tampering/SHA change blocked; per-row exception audit preserved.
- **Idempotency:** same file reuploaded; same row within file; same financial-looking row across distinct files; interrupted source-to-PG handoff; outbox replay after restart; PostgreSQL partial transaction failure and rollback.
- **Security:** authenticated owner Firebase session; invalid/revoked session; Origin + CSRF deny; cross-tenant isolation; least-privilege write role; report role zero DML; no credentials/source customer data in GitHub logs.
- **Business:** one invalid row and two valid rows → 2 eligible, 1 excluded, no global blocking; 1 unresolved SOL → HOLD only that row; repeat bank candidate does not settle. Protect prior allocations.
- **Report:** per SOL/branch exact rupee/paise, count partition, 0 matched before verified engine, full/partial/unmatched-after-run semantics, no cross-tenant leakage; CSV safe against formula injection.
- **Operational:** isolated staging deployment; backup restore test; old production image/Caddy immutable; rollback; post-restart ledger persistence; genuine authenticated staging report parity. Verify exact current container and host outputs.

**Acceptance example (SYNTHETIC only):**

- Five uploaded rows: 2 valid SOL=1505, 1 unknown SOL, 1 invalid amount, 1 possible duplicate from another receipt.
- Expect all 5 source rows retained with receipt/row IDs; only 2 eligible for future engine evaluation; 1 master HOLD; 1 source EXCLUDED; 1 duplicate HOLD.
- New report: uploaded rows=5; source accepted=2; held=2; excluded=1; **matched=0, not calculated=4** if no engine run; all counts and valid-credit totals reconcile. The held count is supplementary and must not be added to the 5.
- After a separately verified engine run, use controlled synthetic evidence to demonstrate exact matched/partial/unmatched counts and conservation of each payment's paise.

**Release markers to report explicitly:**

`DATABASE_SCHEMA_MAPPED`, `FT04_R31_SOURCE_ROW_PARITY`, `PRIVATE_SOL_MASTER_PARITY`, `POSTGRESQL_ISOLATED_INSERT_AND_ROLLBACK`, `FIREBASE_CSRF_E2E`, `OUTBOX_REPLAY_IDEMPOTENT`, `SOL_REPORT_READONLY_PARITY`, `PRODUCTION_FINANCIAL_WRITES`, `LIVE_AWS_DEPLOYMENT`. Each is PASS / FAIL / NOT_TESTED with a linked evidence artifact. Never turn `NOT_TESTED` into PASS.

## 9. Deliverables requested from Database Management

1. **Schema gap analysis:** current central PG object/column inventory, reusable vs proposed columns, indexes, role grants, reversible SQL migration proposal; no speculative production DDL.
2. **Staging PostgreSQL source-ingest adapter** (prefer existing FT-04 modules, not a competing SQLite truth store) with row-specific exclusion, source receipt and durable outbox replay.
3. **SOL master mapping interface** using approved private source/version and explicit ambiguous SOL review.
4. **Read-only SOL-payment report contract** including matched/unmatched/not-calculated/partial count mathematics, amount conservation and R31 UI integration field mapping.
5. **Fresh-invoice future-engine feed** using stable stored payment IDs and no false settlement states.
6. **Automated QA + host integration evidence** including real private Firebase/CSRF, PG role restrictions, rollback, exact SHA/count parity and no production writes.
7. **Deployment handover:** exact branch/commit, migration/rollback runbook, permitted staging write scope, final gaps and next host commands. **Do not self-deploy or grant production financial write access from this requirements file.**

## 10. Approvals and changes that are NOT part of this handoff

- **No new database engine or extra authoritative payment database.** SQLite is permitted only as existing immutable receipt/transport/outbox, if required.
- **No automatic claim that fresh invoice upload has already reconciled saved payments**; full engine and verified match ledger remain independent milestones.
- **No made-up UTR/transaction date, aliases, matched payments, SOL identities or unverified invoices.**
- **No destructive backfill, original row deletion, silent dedup, invoice S overwrite, original PAYMNENT A:L modification, or previously protected allocation overwrite.**
- **No production SQL/schema/role changes, production invoice/payment financial writes, live Caddy cutover or Firebase privilege escalation** without separately authorized operational change and proof of technical guardrails.
- No separate **formal Finance-certification ceremony** is required to deploy the *calculation/report application code*. Keep actual authenticating, data-integrity and write-authority checks intact.

**Owner-requested action for receiving team:** Pull this exact document from branch `sbi-central-postgresql-main-20261121` and implement through a review PR against that central database branch. Identify unapproved choices in chat/PR, not by guessed schema mappings or arbitrary values. Preserve the central PR129 reporting deployment throughout.
