# DB-R31.4 — Owner-scoped PostgreSQL SOL report reader (development-only handoff)

**Date:** 25 November 2026 IST  
**Scope:** single existing `sbi_reconciliation_main` (not a second business payment ledger).  
**Development branch:** `integration/sbi-db-r31-pg-report-readonly-20261125`  
**Release status:** ISOLATED READ-ONLY QA CANDIDATE. No production API route or AWS deployment.

## Existing progress and sources

Issue [#190](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/190) defines the unified central database target. Database Management's DB-R31.1/31.2 catalog and versioned source-only view are in `sbi-central-postgresql-main-20261121`. DB-R31.3 FT-04 ingest [PR #193](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/193) was merged to that development branch after actual disposable PostgreSQL mixed-input/replay/owner-conflict tests passed.

R31 dashboard [PR #188](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/188) exposes `GET /api/payment-received/sol-report`, `.csv`, and `/api/payment-received/payment-details.csv`, but currently reads a **separate SQLite source ledger**. These endpoints need a server-authenticated PostgreSQL implementation for the final unified architecture. **Do not merely add a second copy and double count payments.**

## New source-only reporting adapter

`database/stage31/db_r31_pg_sol_report_readonly.py`:
- Queries `sbi.payment_received_source_v1` from **one source row per original payment** (existing DB-R31 QA candidate view, not a financial allocation join).
- Requires server-derived authenticated owner UID, never user-supplied ID, and limit/offset bounds.
- Enforces PostgreSQL transaction read-only plus exact role/database identity (`sbi_pr129_report_login` on main or `sbi_ft04q_report` on QA only). A QA role must receive **SELECT on the versioned view only**, not on base financial tables.
- Groups padded and nonpadded SOLs by normalized canonical ID. Original source SOL retains its text value separately for details.
- Official branch is used only where all **valid credit payment** rows in the group have the same nonempty branch and approved SHA; invalid/rejected source rows do not mask valid branch mapping. If unresolved/ambiguous, return `PENDING_SOL_MASTER_REVIEW`.
- Per normalized SOL: uploaded source rows, accepted credit rows, exact integer paise sum, invalid excluded, held for review, other not calculated, future-matching pending, legacy unclassified.
- `matched=NULL` and `verified_allocated_paise=NULL` until the **real** v2.51/v2.39 financial matching engine persists verified allocation evidence. No claim of `UNMATCHED_AFTER_RUN` or bank settlement simply because a file was uploaded.
- Owns CSV serialization with formula-injection neutralization, never mutating stored narration/source text.
- Result totals are explicitly **page totals**, not all-owner or full-database aggregates. Pagination is required for large sources.

The read-only query deliberately avoids financial allocation joins: joining a partially allocated payment to two invoices could inflate both payment count and received credit. A future verified engine allocation report must aggregate allocated paise independently and link by unique payment/source IDs.

## Staging verification

CI checks include:
- 16 source-only tests with role/auth parameter, official SOL mapping, unprocessed status, CSV escaping and schema guards.
- **Real** ephemeral PostgreSQL 16 with exact QA-only `sbi` schema and owner-scoped synthetic upload rows from pinned actual R31/FT-04 parsers.
- Dedicated QA `sbi_ft04q_report` role with only USAGE on `sbi` schema and SELECT on `sbi.payment_received_source_v1`.
- Two SOL groups (1505/99922) and 7 source rows, 5 accepted credits, ₹237 total; case holds and accepted branch must reflect source/master, 0 bank allocations. Detail query for an unrelated owner must return zero rows.
- Main production and source financial row counts never touched, QA database discarded after test.

## Still required for full deployment

1. Review current central `sbi_reconciliation_main` catalog again at proposed release SHA; apply **separately reviewed** additive migration only after owner scope/global source SHA strategy is resolved, including legacy classification and rollback/restore on a physical separate staging DB.
2. Replace R31 Flask SQLite report read at its existing routes with an authenticated **server-scoped** PostgreSQL report adapter. Reuse live Firebase auth and report-viewer authorization; ensure CSRF and Origin protections on any POST, and no client-side owner override. Do not register an unverified production endpoint.
3. Current private SBI SOL master, branch mapping SHA and conflicts independently reviewed; no old frozen four-SOL denylist.
4. Real authenticated Firebase staging upload through FT-04 durable outbox, source-row persistence, report summary/detail parity after restart; verify endpoint owner isolation and database role grants.
5. Complete runnable Master v2.51/Matrix v2.39 and v2.18 writer for actually matched payments; protect invoice original Column S and bank `PAYMNENT` A:L. No fake matched rows.
6. Owner explicitly approve production central **source ingest write** scope and authorized AWS host cutover, with deployment receipt, rollback proof and zero unintended financial settlement writes.

No standalone formal Finance *certificate* is required to deploy valid calculation/report software under owner R28 policy; that does not replace actual security and technical acceptance.
