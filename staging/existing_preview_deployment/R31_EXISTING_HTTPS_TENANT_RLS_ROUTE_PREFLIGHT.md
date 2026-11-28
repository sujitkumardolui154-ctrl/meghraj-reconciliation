# R31 — Existing HTTPS Tenant RLS Route Read-Only Preflight

**Required unchanged user URL:** https://sbi-preview.13-232-241-221.sslip.io/login.

## Completed and reused evidence
- Two real non-admin Firebase accounts signed in over trusted HTTPS, CSRF/origin accepted.
- Two one-to-one Firebase UID→protected QA PG role mappings correspond to the operator-identified accounts.
- Dedicated QA PostgreSQL 16 catalog confirms forced RLS, restricted read-only roles, zero payment evidence rows.
- Real HTTPS A→B / B→A denial is **NOT TESTED**.

## The blocker to confirm
The tracked `staging/aws_login_v150/app.py` says the existing AWS login workspace is initially a login/UI shell; `/healthz` identifies financial data and reporting connections as false in its source. The R31.11.4 tenant RLS route is only registered when BOTH **private QA flags** match exact approved values, and the R31.11.4 runtime adapter was designed for an isolated private one-shot QA candidate. Its source existence is **not evidence it was enabled in the active login container**.

Do **not** deploy an alternative platform, alter the existing Caddy, enable flags, copy protected role passwords into the login image, add an unapproved exposed route or bypass financial locks.

## New targeted evidence
`verify_existing_rls_route_metadata_readonly.py` checks only:
- Exact SHA-pinned clean Git worktree and existing `sslip.io/login` policy.
- Existing running `sbi-login-workspace` container identity and whether its Docker **configuration** has the exact private QA flags (reports only status, never raw environment values).
- Presence of the R31.11.4 QA blueprint file inside the running app image.
- Anonymous HTTPS GET status for the exact candidate route (no cookies or user login).
- The unauthenticated response, including HTTP 401, **does not prove the route is registered**: authentication middleware may intercept any `/api/*` path before route matching.

The script does not query the database, use Firebase tokens, repeat login tests, change a container, write files, issue network configuration actions, read customer rows or print secrets. Only the new targeted offline route-check tests need running.

## After the result
- If flags/modules are unavailable, the actual HTTPS RLS acceptance remains blocked until an **independently authorized in-place integration design** is reviewed for the existing application URL and security posture. Do not flip the live flags to make the test pass.
- If flags and modules appear present, still require an independently reviewed test of real sessions A/B, restricted role selection, positive own-row evidence, negative cross-tenant evidence, spoofed headers, read-only methods and post-test rollback (none are proven here).
- Preserve historical private in-process R31.11.4F security evidence without incorrectly promoting it to external HTTPS acceptance.
- Existing external mTLS design cases 0/22 executed are not silently waived by use of the existing domain.

`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
