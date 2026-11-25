# DB-R31.10 — Combined remediation (1–3), isolated staging only

**Scope:** Prepare proof of tenant-isolation architecture, require **two genuinely different authorized Firebase users**, and keep the private QA app unexposed until a separately approved protected HTTPS configuration has been reviewed. No production deployment, financial writes, or changes to existing R31 QA data.

## Gate 1 — PostgreSQL tenant isolation

`r31_10_shadow_rls.sql` runs only as PostgreSQL superuser against `sbi_r31_owner_qa_20261125` inside `sbi-synthetic-postgres-38-31`; it refuses other database identities and requires PostgreSQL 15 or newer. In a **single transaction** it creates disposable shadow tables representing import batches, source rows and payments, two NOLOGIN/NOBYPASSRLS role identities, FORCE RLS owner-role policies, a `security_invoker` view and cross-owner composite foreign keys. It verifies two-sided read denial and foreign owner INSERT denial.

**Everything is explicitly ROLLBACKed**, including roles; the script verifies cleanup afterwards. If a SQL assertion fails, `ON_ERROR_STOP` closes the connection and rolls back. No `sbi.*` table is altered. A shadow test PASS is **not** a real migration of existing source tables. Existing application finance/security must remain blocked until a separately reviewed RLS migration and adapter exist.

**Production design requirement:** Authenticate Firebase identity server-side; bind each identity to a server-controlled PostgreSQL role or equivalent database-enforced unforgeable identity, not a client-controlled owner parameter and not an ordinary user-settable custom GUC. Apply RLS to all original source tables, use security-invoker views, ensure child-row owner consistency, revoke global report-role grants, and verify direct restricted role queries with two separate identities. With the current shared `sbi_r31_ownerqa_report` read-only role, the server's query-level owner filter does not constitute database-enforced cross-tenant isolation.

## Gate 2 — Two actual Firebase sessions

Use an existing *separate* Firebase test account with the `dil_dashboard` claim and a distinct UID, in the same approved Firebase project. The operator supplies each account email/password privately in a real AWS TTY. Tokens travel exclusively by Docker exec stdin and are never logged or stored. R31.9's already-reviewed in-container test checks both signed sessions and bidirectional synthetic foreign-receipt GET/sync denial and report forgery prevention; disposable SQLite rows are cleaned.

If the second test account does not exist, provision and approve it **separately through your authorized Firebase administration procedure**, not by cloning the first account, sharing its password, printing a credential, or granting unnecessary administrator privileges. R31.10 does not create accounts or change claims.

## Gate 3 — HTTPS E2E (must remain fail-closed)

The R31.6 private container has no approved public Caddy QA route. R31.10 checks it stays that way. This is a safety result, **not external TLS E2E**. Required separate approval: a QA-only hostname, TLS certificate validation, client certificate trust / VPN or equally strong access control, trusted proxy network, callback and allowed-origin configuration for the exact test hostname, plus a reviewed rollback.

Only after an authorized protected routing change may an external client complete real HTTPS authentication, cookie Secure/HttpOnly/SameSite checks, legitimate and forged owner access tests, CSRF origin negatives and lack-of-leak checks. Do not enable a general public upstream or use `curl -k` to defeat certificate verification.

## Runbook

Prerequisite: Keep R31.8 pinned private stage `sbi-r31-auth-private-qa` and isolated synthetic Postgres running. Start a fresh Git worktree at the reviewed R31.10 full commit SHA; do not edit original source or dirty checkouts.

Run `python3 -u staging/aws_login_v150/r31_10_combined_remediation.py` directly in AWS Ubuntu interactive terminal; do not use stdin heredocs. The gate performs R31.7 isolation preflight, transactional RLS shadow test, optionally two real Firebase sign-ins, then public-Caddy exposure guard. All output is status-only. A missing distinct account or approved HTTPS route will leave **`STAGING_REMEDIATION_INCOMPLETE_PRODUCTION_BLOCKED`** and exit code 2, intentionally.

**Never run** a migration against `sbi_reconciliation_main`; never apply `ALTER TABLE` or grant production roles as part of this milestone. Master v2.51 allocation and production financial-write approval are independent and still blocked.

## QA acceptance

- `DB_R31_10_SHADOW_RLS_BIDIRECTIONAL=PASS` and `DB_R31_10_SHADOW_RLS_CLEANUP=PASS` prove **only** synthetic shadow RLS under two PostgreSQL role contexts.
- `DB_R31_10_TWO_FIREBASE_OWNERS=PASS_DISTINCT_BIDIRECTIONAL` requires actual two distinct Firebase UIDs and both-direction foreign receipt denial.
- `DB_R31_10_EXTERNAL_HTTPS_E2E=BLOCKED_PENDING_APPROVED_MTLS_ROUTE` remains expected until authorized network/origin work occurs.
- `DB_R31_10_EXISTING_SBI_RLS=MIGRATION_NOT_APPLIED` is explicit evidence that original RLS remains unmodified.
- `DB_R31_10_RELEASE_STATUS=STAGING_REMEDIATION_INCOMPLETE_PRODUCTION_BLOCKED` stays until a subsequent approved implementation and full security gate.
