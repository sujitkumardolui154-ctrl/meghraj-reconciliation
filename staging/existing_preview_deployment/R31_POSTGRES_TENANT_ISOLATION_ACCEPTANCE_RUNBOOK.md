# R31 — PostgreSQL Tenant Isolation Acceptance (existing SBI URL)

**Binding deployment target:** https://sbi-preview.13-232-241-221.sslip.io/login. No new application platform, hostname, domain purchase, public PostgreSQL listener, or automatic migration.

## Reuse old QA only within its recorded scope

- Previous AWS terminal output confirmed two distinct approved *non-admin* Firebase test users signed in over real HTTPS at this existing URL; session cookies and exact Origin/CSRF checks passed. Evidence saved as `R31_REAL_FIREBASE_HTTPS_OPERATOR_RECEIPT_20261128.md`. **Do not repeat login QA** just to recreate a PASS.
- R31.11.4A/B created the separately isolated QA PostgreSQL container/database and PostgreSQL 16 RLS schema. R31.11.4C and D documentation describe guarded genuine Firebase UID mapping and independent restricted role logins; R31.11.4D2 uses rollback-only synthetic fixture data.
- R31.11.4F source describes real Firebase sessions joined to the actual restricted QA PG through an ephemeral *in-process* Flask test client. It is not the same as the existing public HTTPS application. Do not claim its PASS without an operator receipt proving it actually ran.
- R31.11.4H/4I include read-only RLS catalog and Firebase record checks; reuse already approved matching-source SHA receipts. Do not reexecute full historical combined suites to confirm unchanged source.

## New narrow read-only inventory

`verify_postgres_tenant_rls_catalog_readonly.py` is a source-pinned, fail-closed operator script, with only the exact QA database/container and network permitted:

- `sbi-r3114-private-postgres`
- `sbi-r3114-private-isolated`
- `sbi_r31_11_4_auth_qa_20261126`

It reads Docker network/container metadata, then executes a **BEGIN READ ONLY** PostgreSQL catalog aggregation with `psql`. It checks PostgreSQL 16; two non-superuser, non-BYPASSRLS LOGIN roles; exactly two restricted memberships; two one-to-one owner mappings; four forced-RLS evidence tables; four SELECT policies; security-invoker view; no mapping read permission, no financial-source DML privileges, zero QA payment rows, and no public PG port. All output is status codes. **No owner UID, email, data value, password, SQL row or bank information is printed.**

A PASS reports **CATALOG ONLY**. It does not authenticate via the existing web application, execute as restricted PostgreSQL logins, expose another person's records, or prove the two recently authenticated Firebase users match the earlier database mapping. An empty QA database also cannot prove cross-tenant row filtering; prior ephemeral rollback fixture checks may be used only with the exact independently verified test receipt.

## Next acceptance after a PASS

1. Independently correlate the same two recently approved Firebase HTTPS users against the **existing protected** `r311_auth.role_owner_map`, without logging their UIDs or changing that map. The existing PostgreSQL mapping may refer to a different pair of Firebase users; do not assume equality.
2. Verify the genuine restricted role logins using the current 4C-provisioned secret files and approved read-only runtime adapter. No superuser impersonation or UID supplied via HTTP should stand in for the actual DB-enforced RLS policy.
3. Determine whether any authenticated GET-only owner-source route is **actually registered on the existing application**. The R31.11.4 blueprint is *disabled by default* and source-only, so avoid claiming HTTPS tenant acceptance from a Caddy response or in-process Flask test.
4. Only after independent approval for the same existing hostname and read-only test route, verify A->A and B->B own rows, A denied B and B denied A, forged UID/role ignored, anonymous access denied, and write methods forbidden. Use separate disposable fixtures with rollback and post-test zero rows under a DBA-approved procedure.
5. Keep the earlier 22 real external mTLS cases historically 0/22. Accept any replacement network/security plan only after independent sign-off.

## No-release invariants

`FINANCIAL_APPLY=LOCKED`  
`PRODUCTION_RELEASE=BLOCKED`  
`R31_REAL_HTTPS_CROSS_TENANT=NOT_TESTED`  
`R31_POSTGRES_MUTATIONS=NONE`

After each run, share **only** status lines beginning `R31_RLS_` or `STOP=R31_RLS_`. Never post Firebase emails, owner UIDs, database credentials, role secret files, customer rows or tokens.

### Operator invocation

Use a new SHA-pinned detached Git worktree on the existing AWS host. Run only the new targeted offline tests and `--source-sha` script. It does not require Firebase account credentials or repeat authentication.
