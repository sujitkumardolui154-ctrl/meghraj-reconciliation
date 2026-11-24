# DB-R31 — Owner-scoped SHA uniqueness: transactional QA candidate

**Evidence basis:** the owner's 2026-11-24 AWS central catalog and the successful isolated DB-R31.2 additive schema test. The central database `sbi_reconciliation_main` has **no owner/tenant fields on the three payment tables** and has a unique constraint on `(source_system,source_kind,source_sha256)`. DB-R31.2 added nullable owner and receipt fields to **QA only**, with no payment row changes.

**Do not run this candidate on the central production database.** The QA transaction is explicitly hard-locked to `sbi_ft04g_clean_0e858f93` in a physically isolated PostgreSQL instance with no `sbi_reconciliation_main` database. It **ROLLBACKs all schema changes and synthetic rows**, leaving the existing QA staging upload app and private outbox unaffected.

## Candidate uniqueness strategy

1. Preserve exact original source SHA, filename, source row, raw SOL as TEXT and amount as exact integer paise. Do not derive UTR, bank date, settled amount or reconciliation status from the three-column template.
2. For **new owner-linked source imports**, define partial unique `(owner_uid,source_system,source_kind,source_sha256) WHERE owner_uid IS NOT NULL`. Two independent authorized owners may hold exactly the same raw file SHA, without sharing each other's payment event.
3. For **legacy unowned imports**, retain partial global uniqueness `(source_system,source_kind,source_sha256) WHERE owner_uid IS NULL`, so old unowned batches cannot silently multiply.
4. Require owner, receipt ID, sheet name and parser version for **new payment imports** with a `NOT VALID` check. Existing legacy null-owner rows remain unclassified and are never silently backfilled.
5. Only once split indexes exist and a precisely identified original global unique constraint is verified, drop that constraint **inside the same QA transaction**. One owner duplicate should raise a unique violation. A second owner with the same SHA should succeed.
6. Attach two synthetic payments to owner-scoped batches and one excluded invalid source row to the first owner. Verify source-only report totals, status `HOLD_SOL_MASTER`, `EXCLUDED_INVALID_SOURCE`, original SOL `001505`, and `NOT_CALCULATED` for all. The report query must not cross owner boundaries or double count.
7. Transaction **ROLLBACK**; verify pre/post financial counts, schema constraints and indexes are identical. This avoids disrupting installed QA v2 upload/worker processes.

## Why this is not production-ready

- No central migration or production role grant is requested or executed. This is a **rehearsal**; global SHA uniqueness remains in both central and isolated QA after rollback.
- Existing production `import_batches` has **no owner column**. Deploying an owner-aware writer requires a reviewed additive central migration, controlled legacy backfill/classification, tenant/role policy, authentication and private outbox binding, and a rollback that refuses to erase owner-scoped duplicates.
- The QA-only status table has no independent tenant owner column; the owner is derived from its source-row's import batch. The production read path must authorize the real owner server-side; a parameterized SQL WHERE clause by itself is not a substitute for authenticated RLS/role scoping.
- Reports do not show `MATCHED`, `PARTIALLY_MATCHED` or `UNMATCHED_AFTER_RUN` until the verified engine records allocation evidence. Current source-only status is `NOT_CALCULATED`.
- An approved, SHA-pinned, current SBI SOL master and real Firebase/CSRF staging proof remain pending. Source `99922`, CAC/RBO aliases and SOL `1` must follow current owner-approved identity, not guessed defaults.
- This candidate does **not** update FT-04's staging writer to supply owner-linked batch columns and thus must not be left applied while staging upload/worker services expect the legacy constraints.

## Operator contract

Run only `db_r31_owner_scope_qa.sh` from the pinned development commit after the DB-R31.2 migration has already passed. The wrapper independently checks Docker internal network, unexposed containers, absence of the main database from the QA PostgreSQL instance, and unchanged source financial row counts and uniqueness metadata after the SQL's unconditional ROLLBACK.

**Required receipt:** `DB_R31_QA_OWNER_SCOPE_TRANSACTION=PASS_ROLLED_BACK`, `DB_R31_QA_FINANCIAL_ROWS_AND_SCHEMA_UNCHANGED=PASS`, `DB_R31_RELEASE_STATUS=ISOLATED_OWNER_SCOPE_QA_ONLY`.

**Live SQL execution status:** Not run from this GitHub task; owner must run the combined command in AWS. No production release or financial writes are authorized.
