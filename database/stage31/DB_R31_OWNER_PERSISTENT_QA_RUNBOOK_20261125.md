# DB-R31.5 isolated persistent owner source + report combined QA

The owner's previous DB-R31.3 AWS test PASSED: old FT-04 QA row counts and schema were unchanged, after an unconditional PostgreSQL transaction rollback. The new development on draft PR #194 is designed to test **actual persistent** owner-scoped source ingestion without mutating the running FT-04 QA instance.

## Operator command

Run only from a pinned Git commit:

```bash
cd /home/ubuntu/sbi-db-management/db-r31-central-catalog/source
git fetch origin feature/sbi-db-r31-owner-source-adapter-20261125
git checkout --detach FETCH_HEAD
cd database/stage31
python3 -m unittest -q test_db_r31_owner_source_adapter test_db_r31_owner_report_adapter test_db_r31_owner_persistent_qa
python3 db_r31_owner_qa_combined.py
```

## Isolation and automatic stop conditions

- Uses the **same synthetic Docker PostgreSQL container** `sbi-synthetic-postgres-38-31` and internal network `sbi-synthetic-isolated-38-31`. Refuses any production DB visible inside that container, public ports or host production PostgreSQL socket mounts.
- Creates a new **nonproduction schema-only QA clone** `sbi_r31_owner_qa_20261125` from isolated `sbi_ft04g_clean_0e858f93`; no data is cloned. It cannot write to `sbi_reconciliation_main` because that DB does not exist in the synthetic container.
- New QA database only: split owner/nonowner source-SHA unique indexes; reject new ownerless payment uploads; preserve existing immutable invoice/source tables; do not infer bank UTR/date, approved branch or settlement.
- Installs two new restricted QA logins: `sbi_r31_ownerqa_ingest` (source SELECT/INSERT, no UPDATE/DELETE) and `sbi_r31_ownerqa_report` (source-only reporting view SELECT). Passwords are generated server-side into local private permission-0600 env files, not GitHub/chat.
- Uses the exact running application Docker image **without starting its web server**, a read-only ephemeral Python container, no host socket/secrets and no published port.
- Generates a synthetic, fixed-header XLSX with 1 accepted credit (`118.00` rupees) and 1 invalid zero-credit row. Validates the original `payment_evidence_upload._parse` decisions and exact 11800 paise. Creates source evidence for two **synthetic** owners using the **same file SHA** but different receipt IDs. Each owner should have two original source rows, one payment and one excluded-invalid source status.
- Second import for each owner must return `ALREADY_RECORDED`, with no additional payments.
- Reads the resulting original SOL (`001505`), review states and 11800 paise per owner through a separate read-only report account. Verified matched/allocated stay NULL, source-only reconciliation status `NOT_CALCULATED`.

## Limitations — no misleading release labels

This test does **not** wire a production Flask route, authenticate a real Firebase user, perform CSRF/browser upload, update an official SHA-pinned SBI SOL master, or run Master v2.51/Matrix v2.39 allocations. The QA reporting view's SELECT grant is confined to a private synthetic database and **is not production-grade tenant RLS**. The main `sbi_reconciliation_main` remains the only authoritative production ledger. Any future central migration requires approved owner/tenant authorization and audited production-specific migrations; never change the hard-coded QA database name or role into a production target.

The clone retains synthetic rows for idempotency and immutable-evidence review; the runner does not delete or overwrite that evidence. Prior FT-04 QA remains unchanged. A failed step prints `DB_R31_COMBINED_OWNER_QA=REVIEW_REQUIRED` and a bounded `STOP=` diagnosis instead of granting production access.

**Acceptance:** `DB_R31_TWO_OWNER_SAME_SHA_PERSISTENT_QA=PASS`, `DB_R31_DUPLICATE_REPLAY_NO_NEW_WRITES=PASS`, `DB_R31_INVALID_SOURCE_ROWS_AND_STATUS=PASS`, `DB_R31_OWNER_FILTERED_SQL_AND_CSV_PARITY=PASS` and `DB_R31_RELEASE_STATUS=ISOLATED_PERSISTENT_SOURCE_QA_ONLY`.

**Release status at source publication:** GitHub offline CI PASS, AWS isolated execution not yet performed.
