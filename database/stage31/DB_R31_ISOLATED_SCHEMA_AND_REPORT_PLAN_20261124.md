# DB-R31.2 — Central catalog finding → isolated additive schema and report draft

**Source:** Owner's AWS terminal output, 24 November 2026 IST, running read-only `db_r31_catalog_run.sh` on central `sbi_reconciliation_main`. This file describes **schema design and isolated QA code only**. No production migration has run.

## Verified central catalog findings

- 57 source table columns, 42 constraints, 10 indexes, 4 reporting-role table privilege rows, 3 owner-field reviews.
- Existing relationships `sbi.import_batches` → `sbi.payment_source_rows` → `sbi.payments` mapped without a missing source field (mapping gaps=0).
- **No `owner_uid` or `tenant_id`** observed in `import_batches`, `payment_source_rows`, or `payments`.
- **Global** unique `(source_system,source_kind,source_sha256)` detected on `import_batches`. This is not safe cross-tenant idempotency; the same source SHA from distinct owners cannot be interpreted as the same owned payment.
- `sbi_pr129_report_login` has no INSERT, UPDATE or DELETE on the inspected financial tables; it also has no direct SELECT on those four base tables. Existing reporting views may still allow authorized reads; do not grant base table SELECT by assumption.

## DB-R31.2 QA-only migration scope

- `db_r31_additive_qa_up.sql`: guard exact **physically isolated** DB `sbi_ft04g_clean_0e858f93`, add nullable `owner_uid`, `source_receipt_id`, `source_sheet_name`, `source_parser_version` to existing QA `sbi.import_batches`. Null legacy rows remain legacy; these additions do not pretend existing records are owner-scoped. A partial **unique** `(owner_uid,source_receipt_id)` index protects non-null owner receipts but does not replace the legacy global SHA key.
- `sbi.payment_source_status_v1`: one supplemental versioned status per immutable `payment_source_rows.id`, with owner **derived from the linked import batch**, not duplicated in the status row. Valid statuses `PENDING_RECONCILIATION`, `HOLD_SOL_MASTER`, `HOLD_DUPLICATE_CANDIDATE`, `EXCLUDED_INVALID_SOURCE`, `REVIEW_REQUIRED`; machine-readable reasons, canonical SOL and verified official label/master SHA. This **is not a second payment ledger**. Rejected rows must still be written as source evidence in the existing source row table without a corresponding `sbi.payments` event; bridge integration for this is pending.
- `sbi.payment_received_source_v1`: source-only, one row per `payment_source_rows.id`, with original evidence, optional actual received-credit `payments.credit_paise`, versioned status and **`NOT_CALCULATED`**. No allocation join, no invented MATCHED or UTR/bank date.
- **No grants** to reporting/app/engine roles; the view is not a public API. Parameterized owner-filtered SQL/CSV contract is in `db_r31_source_report_contract.py`. CSV escapes `= + - @` formula prefixes. Report verified allocations remain NULL until actual independent engine evidence exists.
- `db_r31_additive_qa_down.sql`: QA-only rollback; refuses if any R31 status or owner/source receipt metadata exists. Existing QA financial records are retained. `db_r31_isolated_schema_qa.sh` tests up, source/view counts, guarded down, and reapply in one combined execution. Code **not authorized for main**.

## Important remaining blockers

1. The **global file SHA uniqueness is intentionally not dropped** by this additive QA migration. This initial design does not solve multi-owner identical-file ingestion. Production requires a separately reviewed owner-scoped uniqueness change, role/RLS policy and backfill after the live catalog + existing keys are examined. Existing FT-04 outbox fails closed for second owner.
2. A real `g.dil_user.uid` must be bound to `import_batches.owner_uid` by a server-side writer, and the matching receipt/source row integrity must be enforced in a transaction. Never take owner from client JSON.
3. Approved SHA-pinned private SOL branch master must be loaded and mapped server-side; unknown/ambiguous SOL and duplicate candidates must be held, not guessed. Older 3970, 6884, 6928, 99922 review entries are not a permanent prohibition; use current approved master.
4. Real Firebase authorization and CSRF, SQL owner-isolation, mixed valid/invalid input, simultaneous uploads, outbox crash recovery, summary-vs-details parity and negative CSV cases are still required for authenticated staging. The existing 3-column evidence does **not** prove settlement.
5. Central `sbi_reconciliation_main` source writes and all allocation/financial apply remain **NOT APPROVED** until a distinct owner decision and recorded AWS runtime evidence. This QA code must never be executed against central production.

## DB Management deliverables tracker

| Receipt | Current state |
| --- | --- |
| `DB_R31_SCHEMA_DIFF_AND_TABLE_MAP` | **CENTRAL_CATALOG_COLLECTED**; owner/global-SHA review required |
| `DB_R31_APPROVED_SCHEMA_MIGRATION` | **QA_CANDIDATE_PREPARED**; not owner-approved/production-run |
| `DB_R31_INGEST_OUTBOX_PARITY` | FT-04 QA evidence exists; central owner status integration **pending** |
| `DB_R31_SOL_BRANCH_MAPPING` | **PENDING CURRENT MASTER SHA** |
| `DB_R31_SOL_TALLY_REPORT_PARITY` | Owner-parameterized source-only SQL/CSV drafted; authenticated live values **pending** |
| `DB_R31_RELEASE_STATUS` | **DESIGNED**; controlled production writes **not approved** |

No new primary database is proposed.
