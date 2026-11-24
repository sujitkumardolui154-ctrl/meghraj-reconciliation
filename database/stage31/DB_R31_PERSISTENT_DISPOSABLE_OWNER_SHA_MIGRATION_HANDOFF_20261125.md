# DB-R31.6 — persistent owner-SHA migration test in a disposable CI PostgreSQL instance

**Source evidence:** Owner AWS command on 25 Nov 2026 reported all rollback-only owner-scope QA markers PASS; original global source SHA unique remained after ROLLBACK. No live DB migration occurred.

**Purpose:** test an ADDITIVE migration protocol and its rollback semantics under PostgreSQL commit/restart-like persistence, without exposing any network port or changing the running FT-04 QA service.

## Files

- `db_r31_owner_persistent_ci_up.sql` — owner/legacy split unique indexes, drop old global SHA unique, NOT VALID guard to prevent **new unowned payment uploads**, commit only on disposable CI database.
- `db_r31_owner_persistent_ci_test.sql` — committed **synthetic only** two distinct owners uploading the same source SHA, denial of same-owner duplicate, denial of missing owner.
- `db_r31_owner_persistent_ci_down.sql` — refuse to reinstate the old global SHA uniqueness while any owner-split duplicates exist. Refuses destructive rollback; does not delete a single source row.
- `db_r31_owner_persistent_ci_cleanup.sql` — removes **only two explicitly identified synthetic rows** from the disposable CI database to permit a clean QA rollback. Must never be used as a business data cleanup procedure.
- `.github/workflows/sbi-db-r31-persistent-owner-ci-20261125.yml` — launches a throwaway PostgreSQL 16 container with **no networking or published ports**, requires the correct test database identity and an explicit CI-only PostgreSQL session value, seeds the FT-04 schema, applies the original R31 additive QA migration, commits the owner-scope test migration, runs the QA cases and confirms eventual return to the global-SHA schema. Destroys the entire container after the run.

## Real observed CI acceptance

[GitHub Actions run 45466822117](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45466822117)

- `DB_R31_DISPOSABLE_QA_SCOPE_AUDIT=PASS`
- `DB_R31_DISPOSABLE_NO_NETWORK_NO_PORTS=PASS`
- `DB_R31_PRODUCTION_DB_IN_CI=ABSENT`
- `DB_R31_OWNER_PERSISTENT_SCHEMA_QA=PASS`
- `DB_R31_PERSISTENT_SAME_SHA_TWO_OWNER_QA=PASS`
- `DB_R31_PERSISTENT_DUPLICATE_AND_UNOWNED_DENIAL_QA=PASS`
- `DB_R31_OWNER_SCOPED_TWO_OWNER_EVIDENCE_PERSISTED=PASS`
- `DB_R31_ROLLBACK_WITH_OWNER_COLLISION=CORRECTLY_REFUSED`
- `DB_R31_OWNER_QA_ROLLBACK_SCHEMA_AND_ROWS=PASS`
- `DB_R31_DISPOSABLE_POSTGRES_DESTROYED=YES`

**Explicitly NOT accomplished by this test:**

- Not a persistent migration on the owner's AWS staging PostgreSQL container.
- Not a production migration against `sbi_reconciliation_main`.
- Not a validated plan for pre-existing multi-owner legacy rows, RLS, exact release roles, or live FT-04 worker behavior.
- Not the private owner-approved SBI SOL master installation.
- Not the complete Master v2.51/Matrix v2.39 matching engine or financial posting.
- Not proof of real Firebase authenticated owner upload or a live PostgreSQL report connection.

## Database Management next actions

Reconcile this source-only schema procedure with **open PR #194** (`sbi_r31_owner_qa_20261125` QA DB and role), which is currently an independent implementation proposal. Do not merge competing QA database identity constants blindly. The real implementation must explicitly decide *which new physically isolated QA instance* is used and what ingestion workers are stopped/migrated. Required release work: compare exact live database catalog; backup/restore dry-run; agree owner/legacy collision policy and low-privilege roles; stage verified Firebase+CSRF owner upload and report view; preserve original payment Excel source rows; operator approval for any central financial source table writes; separately integrate the real reconciliation engine.

**Release state:** `DB_R31_OWNER_PERSISTENT_DISPOSABLE_CI_QA_PASS`. **AWS staging and production releases remain pending.** A standalone Finance certificate is not required for calculation/report application deployment, but this does not authorize an unreviewed financial-data write.
