# R31.7 — combined FT-04 / owner-scoped source persistence / SOL reporting QA

**Development target:** `sbi-central-postgresql-main-20261121`; **scope:** synthetic isolated QA, NOT production.  
**Date:** 25 November 2026 IST

## Confirmed basis

The owner’s AWS terminal reported `DB_R31_ISOLATED_NETWORK_SAFETY=PASS`, `DB_R31_OWNER_SCOPED_DUPLICATE_QA=PASS`, `DB_R31_QA_OWNER_SCOPE_TRANSACTION=PASS_ROLLED_BACK`, and unchanged financial source/schema. The global SHA constraint remained present after rollback.

Existing merged DB development:
- R31.3 / FT-04 source ingest, source row/SHA evidence and duplicate candidate review (PR #193).
- R31.4 normalized SOL read-only PostgreSQL owner-scoped source reports (PR #195).
- R31.4B private Firebase report WSGI overlay, **not** real authenticated browser AWS acceptance (PR #196).
- R31.5 strict cross-receipt source replay (PR #197).
- R31.6 persistent owner SHA additive migration **only in disposable CI** (PR #199).
- Owner-specific source/QA runner, isolated owner DB, separate ingest/read roles (PR #194, merged after the disposable migration CI).

## Newly executed milestone

GitHub Actions: `SBI R31.7 Combined Persistent Owner Payment Source QA (Isolated Only)`.

[Exact CI run](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45468830618) — **PASS**.

The new workflow:
1. Pins the original R31 login/payment parser image to source commit `ec5f175aad8c3d7897333e48374b00ba0f174328`, and builds an overlay with the PostgreSQL driver.
2. Creates a **fresh internal-only** synthetic FT-04 PostgreSQL 16 instance and source-only R31.2 schema; no production database is present and no ports are published.
3. Runs existing `db_r31_owner_qa_combined.py` from the merged Database Management branch, cloning only the QA schema into `sbi_r31_owner_qa_20261125`, creating least-privilege ingest/report accounts, and using ephemeral server-side credentials.
4. Processes a synthetic approved-header workbook through the actual R31 payment parser. For each of **two synthetic owners with the same file SHA**, stores two source rows: one positive credit for ₹118.00 and one rejected zero-credit row; preserves original `SOL ID=001505`, exact 11800 paise, receipt lineage and `NOT_CALCULATED` status.
5. Verifies a second import for each owner is `ALREADY_RECORDED` (no additional rows), one real `sbi.payments` row per owner, and source-only report SQL and CSV parity under a distinct read-only role.
6. Checks the original FT-04 QA database’s source row counts did not change, then destroys every test container/network and private credential directory.

**Observed markers:**

```text
DB_R31_7_OWNER_STAGE_SCOPE_AUDIT=PASS
DB_R31_7_FT04_QA_ISOLATED_SCHEMA=PASS
DB_R31_OWNER_QA_SCHEMA_PERSISTED|PASS
DB_R31_TWO_OWNER_SAME_SHA_PERSISTENT_QA=PASS
DB_R31_DUPLICATE_REPLAY_NO_NEW_WRITES=PASS
DB_R31_INVALID_SOURCE_ROWS_AND_STATUS=PASS
DB_R31_OWNER_FILTERED_SQL_AND_CSV_PARITY=PASS
DB_R31_NO_UNVERIFIED_RECONCILIATION=PASS
DB_R31_FT04_QA_EXISTING_ROW_COUNTS_UNCHANGED=PASS
DB_R31_7_OWNER_FT04_POSTGRES_SOURCE_REPORT_INTEGRATION=PASS
DB_R31_7_EPHEMERAL_QA_DESTROYED=YES
```

Unit/contract suite: **22 / 22 passed**. This validates the merged owner-specific QA runner in a clean disposable PostgreSQL instance and catches conflicts that separate unit tests could miss.

## Next authorized operational stage (on the owner's AWS Lightsail server)

**Read before running:** `database/stage31/DB_R31_OWNER_PERSISTENT_QA_RUNBOOK_20261125.md`. Follow the runner’s exact container/network allowlist. It **refuses** a production database or unsafe volume/network. This is not the real AWS financial database migration.

From a *separate, verified source checkout* pinned to the reviewed commit:

```bash
git fetch origin sbi-central-postgresql-main-20261121
git checkout --detach <reviewed_R31.7_merge_sha>
python3 -m unittest discover -s database/stage31 -p 'test_db_r31_owner_source_adapter.py' -v
python3 -m unittest discover -s database/stage31 -p 'test_db_r31_owner_report_adapter.py' -v
python3 -m unittest discover -s database/stage31 -p 'test_db_r31_owner_persistent_qa.py' -v
python3 database/stage31/db_r31_owner_qa_combined.py
```

Do not execute against existing financial PostgreSQL, modify production IAM, copy private customer workbooks into GitHub, enable financial APPLY, repoint the QA database constants, or change live Caddy. The runner installs **a separate nonproduction schema-only QA clone**, not `sbi_reconciliation_main`. If it prints `STOP=` or `REVIEW_REQUIRED`, capture the code-only failure and preserve the existing environment for review.

**The owner’s production-write approval remains separate.** No standalone Finance certificate is needed merely for software calculation/report deployment; however actual authenticated owner staging, least-privilege production DB mapping, safe backup/restore and explicit write scope are still required before production activation.

## Still unresolved

- Running the above exact owner-isolated combined procedure against the user's AWS Lightsail synthetic network (GitHub CI success is not an AWS host result).
- Full real Firebase-authenticated browser + CSRF + receipt write and PostgreSQL reporting in *private staging* (parallel PR #198 is a separate staging proposal).
- Current private SHA-pinned official SBI SOL master installation and review of unresolved names.
- Central database production-specific owner/legacy SHA migration, RLS/report role/backup/restore and actual source-write authorization.
- Full Master v2.51 / Matrix v2.39 reconciliation allocations and v2.18 output Excel writer; **no payment is marked MATCHED** by the source-only R31.7 test.

**Release:** `DB_R31_7_DISPOSABLE_COMBINED_SOURCE_REPORT_QA_PASS`. **AWS_STAGING=NOT_VERIFIED**, **PRODUCTION_WRITE=NOT_PERFORMED**.
