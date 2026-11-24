# DB-R31.3 — FT-04 payment row ingest integration, isolated QA acceptance

**Date:** 25 Nov 2026 IST  
**Workstream:** existing `sbi-central-postgresql-main-20261121` Database Management branch / Issue #190.  
**PR:** #193 (development only).  
**Actual release scope:** `sbi_ft04g_clean_0e858f93` isolated QA. **Never** central `sbi_reconciliation_main` production.

## Why this is a separate integration step

The main DB team already collected the central catalog and designed `db_r31_additive_qa_up.sql`, `payment_source_status_v1` and a source-only report view. The FT-04 team implemented a separate QA staging upload/outbox, and R31 implemented a private SQLite upload display. These components require one **authoritative central payment model** and an owner-verified source ingest rather than two business ledgers.

This PR adds:
- `db_r31_ft04_ingest_qa.py` — isolated, transaction-safe DB source insert of `import_batches`, **all original** `payment_source_rows`, individual valid-credit `payments`, one R31 status row per original payment source row. SHA, source row number, owner UID, receipt ID, raw `SOL ID`, exact credit paise and branch/master version are preserved.
- `db_r31_ft04_parser_parity.py` — original R31 workbook parser/FT-04 low-level XLSX reconciliation. It handles a known duplicate trap: FT-04's single-row checks do not see a repeated-row flag unless full-workbook first-seen normalized keys are retained. Full accepted/invalid counts and paise must match the approved parser before ANY insert.
- `db_r31_private_sol_master.py` — versioned private SOL mapping. SHA-pinned, immutable file permissions checked, unique approved official identity only. Unknown/ambiguous mappings held. The historic SOL review list is **not** a permanent exclusion: e.g., approved unique `99922` is permitted after the actual current private master is loaded.
- QA unit tests and `qa_r31_ft04_real_pg_smoke.py` — synthetic mixed valid/rejected/duplicate files, independent successful source rows, same-owner replay, global-SHA cross-owner HOLD, cross-receipt duplicate HOLD, view and exact paise parity.
- `db_r31_ft04_qa_seed.sql` — disposable PostgreSQL baseline matching the FT-04 source table layout. Uses existing **QA-only** `db_r31_additive_qa_up.sql`. No production DDL.

## Database semantics to preserve

| Case | Source record | `sbi.payments` row | Match candidate |
|---|---|---|---|
| Valid positive credit + approved unique SOL | retained | inserted in QA | `PENDING_RECONCILIATION` only |
| Valid credit + missing/ambiguous SOL | retained | inserted, not settled | `HOLD_SOL_MASTER` |
| Invalid or repeated source row rejected by approved parser | retained | **not inserted** | `EXCLUDED_INVALID_SOURCE` |
| First row in a same-file duplicate pair | retained | inserted, held | `HOLD_DUPLICATE_CANDIDATE` |
| Same-looking amount/SOL/narration in another receipt | retained | inserted, held | `HOLD_DUPLICATE_CANDIDATE` |
| Exact identical file replay, same owner + receipt | existing rows verified, no new rows | none new | `QA_ALREADY_RECORDED` |
| Identical file SHA from another owner with legacy global unique key | no new entry | none new | `GLOBAL_SHA_CROSS_OWNER_REVIEW_REQUIRED` |

The duplicate source-row exclusion rule is **not** bank-ledger duplicate proof. Original file/SHA and receipts remain preserved outside PostgreSQL by FT-04's durable delivery outbox. A three-column source does NOT provide unique UTR or bank date. Do not classify anything as `MATCHED`, `PARTIALLY_MATCHED` or `SETTLED` until a separate verified reconciliation engine actually records an allocation.

The QA ingest role requires source `SELECT, INSERT` and status `SELECT, INSERT`, **never `UPDATE` or `DELETE` on financial data**. The code uses transaction-scoped advisory locks and global source SHA uniqueness as a temporary safety guarantee. This does **not** solve cross-owner same-file ingestion. The DB team is separately addressing that in its transaction-rollback owner-scope migration candidate (PR #192).

## Test boundary

The source QA workflow pins:
- FT-04 source branch commit `fdf4b684f524d5acb8470b01c1bec9ec30bf4001`;
- R31 application parser commit `ec5f175aad8c3d7897333e48374b00ba0f174328`;
- a disposable PostgreSQL 16 Docker container with **ONLY** `sbi_ft04g_clean_0e858f93` (no central DB).
- mock/contract tests for positive/negative, and actual isolated postgres integration.

Expected synthetic receipt:
- First 5 rows: 3 parser-valid credit events totalling **₹130.00** (one normal, one SOL hold, one duplicate candidate hold), plus 2 excluded original rows (invalid amount, second repeated row).
- Exact source replay leaves counts unchanged.
- Another owner with identical file SHA is held while legacy global unique key exists.
- Second two-row receipt: one matching-looking prior bank entry is held, independent `₹7.00` stays available as a candidate; total stored valid source credits become **₹237.00** across 7 source rows.
- No financial allocations, no original `PAYMNENT` / invoice source edits, no Caddy or production access.

## Still required for an actual AWS release

1. Database Management complete current central owner+SHA uniqueness and legacy classification/backfill design; reversible migration and role/RLS proof in QA. Do NOT reuse the global-SHA QA implementation for multi-user production.
2. **Real** approved SOL master mounted privately and SHA-pinned, plus known remaining location aliases reviewed against latest signed source.
3. Connect the production Flask upload flow to a production-specific **least-privilege ingestion worker** only after independently approving central column/constraint mapping. Avoid exporting QA credentials or simply replacing QA DB constants in this module.
4. Verify genuine Firebase login, CSRF/Origin and tenant isolation in a private AWS staging service; test crash-recovery/outbox, upload commit/rollback, restart and authenticated read-only SOL report parity.
5. After current R31/FT-04 source persistence is accepted, connect **full executable Master v2.51/Matrix v2.39** and the approved v2.18 Excel writer. Until that verified engine runs, source-wise report remains `NOT_CALCULATED`.
6. Owner must explicitly authorize any activation of real central financial **source WRITE** privileges and the production release cutover. **A separate financial-certification certificate is NOT required merely to deploy calculation/report software** (R28 decision), but software correctness/auth and access scope remain mandatory.

## Stage receipt vocabulary

- `DB_R31_FT04_QA_SOURCE_UNIT=PASS` — offline only.
- `DB_R31_FT04_QA_REAL_PG_MIXED_ROW_PARITY=PASS` — disposable SQL only.
- `DB_R31_FT04_QA_REAL_PG_REPLAY_IDEMPOTENT=PASS`.
- `DB_R31_FT04_QA_GLOBAL_SHA_CROSS_OWNER=HELD_SAFE`.
- `DB_R31_FT04_QA_CROSS_RECEIPT_DUPLICATE_HELD=PASS`.
- `DB_R31_RELEASE_STATUS=ISOLATED_FT04_INGEST_QA_PASS_ONLY` — **does not mean AWS live**.

This source-only handoff intentionally does not alter financial production records, database roles, live Caddy or final payment reconciliation status.
