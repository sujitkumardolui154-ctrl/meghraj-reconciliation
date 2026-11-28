# R31 — Real Firebase to QA PostgreSQL Owner Binding Correspondence

**Existing application URL:** https://sbi-preview.13-232-241-221.sslip.io/login

**New milestone (identity matching only):** Following operator-reported 2/2 real non-admin HTTPS login success and 6/6 PostgreSQL RLS catalog PASS, determine whether the **same two employee emails** used in HTTPS acceptance correspond to the already-provisioned R31.11.4C Firebase Admin-approved UIDs and `r311_auth.role_owner_map` database role bindings.

## What is reused
- Existing 2-user browser-hostname Firebase HTTPS acceptance receipt; no further login attempts, passwords, ID tokens or cookies.
- Existing restricted PostgreSQL 16 QA container, RLS schema and roles; **no schema reapply, role change, user creation or migrations**.
- Existing 4C security-bound `two-approved-accounts.json` (private 0600) and real Firebase Admin SDK `get_user` revalidation. No account IDs or emails committed.
- Existing catalog audit and read-only topology guards reused only for current-state preflight.

## Exact runtime behavior
1. Require exact clean pinned Git revision and original `sslip.io/login` policy, `FINANCIAL_APPLY=LOCKED` and `PRODUCTION_RELEASE=BLOCKED`.
2. Verify private QA PostgreSQL remains unpublished and catalog restrictions unchanged.
3. Ask the operator at the AWS TTY for the **same two emails used in the successful HTTPS test**, using hidden local prompts. This is an **operator attestation**, because the original saved acceptance receipt intentionally contains no identifiers.
4. Read and revalidate the approved private 4C account records through Firebase Admin SDK, then read only the protected QA database's two owner UID mappings under a `BEGIN READ ONLY` transaction. Compare in local memory, print fixed status labels only.
5. Stop if accounts differ, disabled/unverified user claims fail, QA role map drifts, credentials unavailable, or the environment isn't suitable.

This verifies identity correspondence to the protected approval records, but is **not cryptographic evidence that the same HTTPS sessions reached PostgreSQL**. It is **not** a cross-tenant row-level GET test: QA evidence rows remain empty.

## AWS invocation
Create a fresh, detached SHA-pinned Git worktree under /home/ubuntu. The installed Firebase Admin Python environment from earlier R31.11.4C was `/home/ubuntu/sbi-r3114c-firebase-venv/bin/python`; use it only if it exists and is independently trusted. The script must not be run under sudo or with copied credentials.

Run targeted unit tests `test_firebase_pg_owner_binding_readonly.py` and then `verify_firebase_pg_owner_binding_readonly.py --source-sha <exact_git_sha>`.

If the local Firebase Admin identity or approval file cannot be verified, leave the gate PENDING. Do not use test placeholders, create users, rewrite the mapping, paste secrets or automatically provision another database.

## After a PASS
The **next separate acceptance** is independent, real, read-only HTTPS A/B enforcement using the *existing application URL*. First verify the R31.11.4 route has an explicitly authorized registered GET-only handler and a safe test-data strategy (temporary rollback fixtures, two QA-only owners). Test both own access and cross-owner denial, spoofed owner headers, wrong-method and unauthenticated requests; verify original Caddy, DB and finance writes unchanged. The private R31.11.4F in-process test is distinct evidence and does not automatically count as HTTPS acceptance.

`R31_BINDING_TWO_WAY_RLS_HTTP=NOT_TESTED`
`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
