# DB-R31.11 — Combined tenant-security implementation candidate

**Status:** Review-only staging candidate; financial production blocked.

## Delivered: all three streams

### 1. PostgreSQL RLS implementation in a *new schema-only* QA clone

The host runner \`r31_11_combined_tenant_security.py\` refuses the wrong image/database/network; it first reuses the R31.7 private isolation preflight. It checks that the PostgreSQL container is running only on the internal synthetic network and has no published port. It also refuses to proceed if \`sbi_reconciliation_main\` is present in that isolated instance.

Only if the specifically named database \`sbi_r31_11_tenant_clone_20261125\` is absent, it creates that database on the already isolated Postgres container, dumps **schema only** (\`pg_dump --schema-only --schema=sbi\`) from \`sbi_r31_owner_qa_20261125\`, and installs that empty schema in the new database. Existing R31.7/R31.10 rows and the production database are not read into the clone.

\`r31_11_clone_rls_up.sql\` applies **FORCE RLS** to the clone's \`sbi.import_batches\`, \`sbi.payment_source_rows\`, \`sbi.payments\`, \`sbi.payment_source_status_v1\`. The four SELECT policies trace ownership to \`import_batches.owner_uid\`. A protected \`r311_auth.role_owner_map\` maps restricted database login identities to verified owner UIDs. A \`SECURITY DEFINER\` function uses \`session_user\` (the database login role), never request owner headers, owner query parameters or ordinary user-settable PostgreSQL custom settings. The source view is changed to **\`security_invoker=true\`**. Previous shared report-role access to that view is revoked **only in this clone**.

\`r31_11_clone_rls_verify.sql\` inserts synthetic A/B source rows into the clone and uses separate impersonated database-role sessions to ensure each sees exactly one owner's source rows, credits and status, never the other's. It verifies that changing \`app.owner_uid\` does not affect RLS; unauthorized financial INSERT is blocked; and the legacy shared report role cannot read the invoker view.

**Critical limitation:** The two synthetic roles are \`NOLOGIN\`; they prove policy semantics, not a live Firebase-to-Postgres tenant credential path. The production-staging application still uses its existing shared report role and cannot be promoted. Before a new app adapter can connect, the owner must approve real per-tenant database login-role provisioning, private credentials, and server-enforced Firebase UID binding. Existing ingest writes must also be adapted safely; the RLS candidate currently provides tenant reads, not an approved ingest path.

The clone is persistent for inspection. A rerun refuses to overwrite it (\`CLONE_ALREADY_EXISTS_REVIEW_REQUIRED\`). **Never** drop or reset existing QA databases, original receipts or production financial source tables while troubleshooting.

### 2. Distinct Firebase test identity preflight

\`r31_11_second_firebase_preflight.py\` asks whether a separate test account exists, then securely prompts for its email and performs a read-only Firebase Admin lookup in the existing isolated app container. The email travels only through Docker stdin. It never reaches arguments, logs, output, ChatGPT or GitHub; it is not stored.

The result distinguishes missing user, same-as-master UID, disabled user, missing \`dil_dashboard\` claim, unnecessary \`dil_admin\` privilege, and valid second test identity. It does **not** create accounts or change claims.

Only when preflight passes does the combined runner offer R31.10's actual **two separate Firebase ID-token sign-ins** and bidirectional synthetic foreign-receipt access test. A valid second user is still required; a new email typed at the prompt is not automatically a Firebase account.

### 3. Restricted HTTPS design, not a deployment

\`Caddyfile.r31_11_review_only.template\` is deliberately addressed to \`qa-r311.example.invalid\` and is **not imported or loaded** into Caddy. It shows a QA-only mTLS design using Caddy \`client_auth { mode require_and_verify; trust_pool file ... }\`, a short API route allowlist, and a default 404 handler.

Actual external HTTPS E2E still requires explicit approval for a separate QA hostname and TLS certificate, issuance/rotation of a dedicated client CA, trusted transport, appropriate network ACLs, exact allowed Origins in the isolated Flask app, tested CSRF and secure-cookie forwarding, and a rollback. The current original Caddy routing remains untouched, and the QA container is **not** made public automatically.

## Operator instructions (after GitHub CI PASS)

In an existing Ubuntu checkout of the repository:

1. Fetch \`feature/sbi-r31-11-tenant-enforcement-firebase-https-20261125\`, pin the reviewed full SHA, and create a fresh detached worktree. Do not update dirty R31.10 worktrees.
2. Run **directly in a TTY**, not inside \`bash <<'BASH'\`:

   \`python3 -u /home/ubuntu/sbi-r31-11-security/source/staging/aws_login_v150/r31_11_combined_tenant_security.py\`

3. If the second account does not exist, answer \`N\`. The clone RLS and Caddy guards still run; two-real-user E2E remains \`NOT_TESTED\`. Do not enter fabricated credentials or paste passwords into any chat.
4. Collect only \`DB_R31_11_...\` statuses; no UIDs, email addresses, passwords, tokens or complete bank rows.
5. The runner intentionally returns **exit code 2** and a production-blocked receipt, even if the isolated clone RLS test passes, since the original running application and external HTTPS checks remain unapproved.

## Production release gates remain mandatory

- Review and verify permanent tenant auth/credential architecture, owner mapping lifecycle, tenant-role privilege revocation and all original table policies; independently test direct raw SQL access as two genuine role logins (not superuser impersonation).
- Bind real Firebase user identity to the appropriate restricted DB login inside the backend and remove reliance on shared report grants. Apply writer paths only after source preservation, replay/idempotency, and rollback are approved.
- Verify two different real Firebase accounts with \`dil_dashboard\` in the intended project.
- Approve restricted HTTPS route and secure same-origin cookies, TLS client-auth, source report access and CSRF negatives end to end.
- Keep v2.51 reconciliation calculations, invoice staging, and production financial writes locked until their separate financial QA gates are approved.

**Never run \`r31_11_clone_rls_up.sql\` against \`sbi_r31_owner_qa_20261125\` or any database except the exact clone.**
