# DB-R31.4B — Firebase-guarded PostgreSQL payment report staging overlay

**Status:** Development QA only. No AWS host deployment, no central production financial-write activation and no full reconciliation.

This is a follow-on to the merged source-ingestion PR #193 and read-only SOL query PR #195, both on `sbi-central-postgresql-main-20261121`.

## Problem addressed

The R31 dashboard (PR #188) already has user-facing routes:
- `GET /api/payment-received/sol-report`
- `GET /api/payment-received/sol-report.csv`
- `GET /api/payment-received/payment-details.csv`

Those routes currently calculate from a separate `payment_received_evidence_v1` **SQLite** source ledger, not the agreed PostgreSQL `sbi_reconciliation_main` architecture. They must not be counted as a second authoritative received-payment store.

## Proposed private staging solution

- `db_r31_pg_report_private_wsgi.py` identifies exactly the three existing endpoints, and only on a **separate staged R31 Firebase login app instance** it replaces their VIEW handlers, preserving their existing route paths.
- The original `dashboard_sessions.install_sessions(app)` remains registered as the existing before-request Firebase session cookie verification, account claim check and revocation check. The report additionally requires matching server-verified `g.dil_user.uid` and `g.dil_identity['uid']` and a trusted `sbi_report_viewer` claim or original account master check. No owner UID from request parameters or headers.
- Explicit environmental scope required: `SBI_R31_PG_REPORT_STAGING_ENABLED=true`, `SBI_FINANCIAL_APPLY=LOCKED`, `PGDATABASE=sbi_ft04g_clean_0e858f93`, `PGUSER=sbi_ft04q_report`, and a restricted private connection string. No fallback to SQLite results when staging PostgreSQL is disabled or failing.
- The report adapter enforces PostgreSQL `SET TRANSACTION READ ONLY`, validates the actual connected DB/role, parameterizes UID and pagination, and sends no financial DML.
- The existing R31 dashboard field names remain compatible: `sol_groups` with `sol_id`, `branch_name`, `credit_total`, `matched`, `not_calculated`, `excluded`, `held_for_review` plus totals. **Matched=0 means zero independently verified matches recorded (no engine connected)**, not that a real calculation determined no match. The SQL matched field remains NULL and the API flags `reconciliation_executed=false`.
- CSV detail and SOL summary both escape formula-like text without modifying original bank source values. Page totals are never presented as all-owners/global totals.
- `db_r31_pg_report_staging_wsgi.py`: separate explicit staging-only WSGI entrypoint. Base app remains untouched.
- `Dockerfile.pg-report-private-qa`: builds a private reviewed overlay on a PINNED R31 AWS Login image (not the live container), adding only report code and psycopg3, running non-root.

## Required validation before AWS staging

1. 16 staging Flask route and RBAC unit tests, including disabled stage, production DB refusal, no matched allocations, sensitive DSN failures and CSV formula injection.
2. Isolated Docker build of pinned base and additive overlay; no network at runtime; test that actual original Firebase auth middleware returns **401** for anonymous report requests, and POST financial-run route remains refused.
3. Disposable PostgreSQL QA import from exact original FT-04/R31 parser and dedicated SELECT-only view role; verify owner/group/status/credit/detail parity from source rows.
4. Then on a controlled **real AWS staging** service with the owner-provided staging credentials, verify valid Firebase owner session/claim, revoked session, different tenant, original CSRF/Origin, read-only PG report parity, old Caddy unchanged, backup and rollback. GitHub Actions synthetic tests **do not** replace this real staging owner authentication test.
5. Only then review production-specific central `sbi_reconciliation_main` reporting view/RLS, least privilege and source/owner mapping. The production report role must not receive payment/financial table write permissions.
6. The complete Master v2.51/Matrix v2.39 allocation engine remains **not connected**. Keep `not_calculated` distinct from genuinely `unmatched_after_run`.

## Technical release status

`DB_R31_PG_REPORT_STAGE=CODE_AND_SYNTHETIC_QA_ONLY`  
`FINANCE_CERTIFICATE_REQUIRED_FOR_REPORT_APP_DEPLOY=NO`  
`PRODUCTION_FINANCIAL_SOURCE_WRITES=NOT_AUTHORIZED_HERE`  
`AWS_HOST_DEPLOYMENT=NOT_PERFORMED`  
`POSTGRES_MAIN_SCHEMA_MIGRATION=NOT_PERFORMED`  
`FULL_RECONCILIATION_MATCHING=NOT_CONNECTED`

Use a separately reviewed, exact-source-SHA release candidate. Do not modify the running AWS PR129 service or expose a public Caddy endpoint while testing.
