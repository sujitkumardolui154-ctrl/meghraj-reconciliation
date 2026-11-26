# DB-R31.11.4 — Private Runtime Provisioning & Authenticated Acceptance

**Status:** REVIEW-ONLY CANDIDATE. No AWS provisioning, deployment, Firebase
account creation, certificate issuance, DNS change, or production financial
write is authorized by these files.

## 1. Why an independent runtime is required

R31.11/R31.11.2 have already passed their dedicated read-only synthetic
PostgreSQL tenant RLS tests. They use
\`sbi-synthetic-postgres-38-31\` and database
\`sbi_r31_11_tenant_clone_20261125\`, with two **NOLOGIN**
synthetic test roles. Do not install real account login roles, owner mappings
or credential files in that validated synthetic clone.

R31.11.3 demonstrated, using a **disposable GitHub Actions PostgreSQL 16**
instance, that a separate restricted LOGIN role per owner can read through
database-enforced RLS. Its first adapter is intentionally pinned to the old
synthetic QA target and is **not an AWS real-user deploy candidate**.

R31.11.4 introduces a separately pinned target instead:

| Resource | R31.11.4 exact proposed identity |
| --- | --- |
| Private PostgreSQL Docker service | \`sbi-r3114-private-postgres\` |
| Private internal-only Docker network | \`sbi-r3114-private-isolated\` |
| Dedicated acceptance database | \`sbi_r31_11_4_auth_qa_20261126\` |
| Backend candidate Dockerfile | \`Dockerfile.r31_11_4_private_candidate\` |
| Protected binding file (private mount) | \`/run/secrets/r3114-tenant-bindings.json\` |
| Per-login password files | \`/run/secrets/r3114-*.env\` |
| Database login roles | \`r3113_login_a\`, \`r3113_login_b\` |
| Backend feature flag | \`SBI_R31_11_4_RUNTIME_ENABLED=private-firebase-rls-auth-acceptance-v1\` |
| Private source endpoint | \`GET /api/r31-private-qa/tenant-rls-source-r3114\` |

These are **future isolated infrastructure names**, not a statement they
already exist or are running.

## 2. Implemented code / no-write readiness audit

- \`r31_11_4_private_runtime_readiness.py\` calls the original private
  isolation preflight and checks the existing R31.11.3 adapter still targets
  the synthetic clone. It refuses direct Caddy references to the private QA
  services, never uses public networking, and does not create anything.
- If no distinct new PostgreSQL service exists, it reports
  \`SEPARATE_AUTH_POSTGRES=NOT_PROVISIONED\`; no retry or migration.
- If the service exists, the auditor checks: running; private internal
  non-attachable network only; no host-published ports; no privileged
  Docker access; no Docker/PostgreSQL socket mount; and no production,
  main staging or pre-existing QA databases inside it.
- If the expected new database exists, a read-only catalog query verifies
  two restricted LOGIN roles, each with one non-administrative/no-SET
  membership to a distinct NOLOGIN group role, **four FORCE RLS tables**,
  \`security_invoker\` view, exactly two different non-synthetic owner
  mappings and no direct access to the role-owner mapping table or INSERT,
  UPDATE or DELETE privileges on source/financial evidence.
- This does not prove the Firebase account identities or live secrets. It
  never displays UIDs, passwords, tokens, invoice/payment rows or raw
  PostgreSQL errors.
- The auditor **always ends with production release blocked** and a
  nonzero exit code, regardless of the catalog status.

The separate \`r31_11_4_runtime_rls_adapter.py\` and
\`r31_11_4_runtime_rls_blueprint.py\` target **only** the new proposed
service/database; they check database and session role equality, the trusted
Firebase UID from \`g.dil_user\`, active RLS on each table, no financial DML,
a transaction-level read-only mode, and every owner identity returned.
They reject mismatches and never fall back to the former shared report role.

The new endpoint is registered only in the isolated candidate image after
both \`SBI_R31_PRIVATE_STAGING_ENABLED=isolated-ownerqa-firebase-csrf-v1\`
and the separate R31.11.4 feature flag are present. Neither is activated
by this commit. The public image and Caddy routing are unchanged.

## 3. Required external private provisioning approvals (still pending)

Do **not** apply any role SQL or deploy the new image yet. An authorized DBA
and security owner first need to review and approve:

1. **Two distinct existing Firebase TEST accounts** in the correct project,
   both with \`dil_dashboard=true\` but without unnecessary administrator
   claims; record privately that their UIDs differ. The second test account
   was previously unavailable. Do not invent one, reuse one UID twice or
   paste identities/credentials into GitHub or ChatGPT.
2. A completely separate PostgreSQL 16 QA container on an internal-only
   network, with dedicated backed-up/test-restored volume, documented
   teardown and no shared production or older R31 clone mounts.
3. Reviewed RLS-only schema installation and minimal restricted login-role
   provisioning in that separate QA instance. Use separate password-auth
   roles for the two users, each mapped to one distinct verified Firebase UID.
   No SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE, ADMIN membership or
   \`SET ROLE\` escalation; no access to another role's group or raw mapping.
4. Randomly generated per-role secrets, provisioned outside repository and
   shell history to mode-0600 files owned by the unprivileged API process;
   bind only the intended role/database/host. Rotate and delete on teardown.
5. A separate isolated API candidate container on the approved private QA
   network; read-only root filesystem where supported, no published ports,
   no Docker socket or production PostgreSQL credentials. Keep feature
   flags disabled until review.
6. Explicitly approved QA hostname/Origin, dedicated mTLS trust, client
   certificates, access controls, expiry/revocation, and rollback before
   any external HTTPS E2E. **No public route may be exposed automatically.**

Do not treat source CI PASS or a provisioning script's exit code as real
approval of steps 1–6.

## 4. Essential authenticated acceptance (when prerequisites exist)

One controlled, approved QA run should test:

- Actual two distinct, independently authenticated Firebase test sessions;
  revocation, disabled user and missing \`dil_dashboard\` denied.
- Separate password-authenticated PostgreSQL LOGIN roles, each with its
  exact protected owner mapping; owner A sees only A and owner B only B.
- Anonymous request denied 401; forged owner/header/URL query cannot
  change the tenant; cross-owner direct SQL denied; ordinary user cannot
  access protected role-owner map or financial source mutations.
- New read-only endpoint returns only source evidence marked
  \`NOT_CALCULATED\`; financial Apply and invoice/GST routes stay disabled.
- Secure session-cookie/CSRF behavior on the approved protected HTTPS path
  and network isolation/rollback with no financial writes.
- Record independently approved artifacts and hashes privately, without
  publishing customer data, account IDs, JWTs, passwords or test results
  containing PII.

The current GitHub CI uses **mocked Firebase users/cookies**, not real users.
The prior R31.11.3 PostgreSQL role test used ephemeral fake data. Neither
substitutes for these authenticated AWS acceptance checks.

## 5. Operator: safe readiness check only

From a SHA-pinned, fresh detached checkout of this branch:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4/source/staging/aws_login_v150/r31_11_4_private_runtime_readiness.py
\`\`\`

This command does NOT create the planned private database or ask for a
second Firebase account. It does not connect to a real-user database login.
Its expected incomplete-environment status is:

\`\`\`text
DB_R31_11_4_R3113_TARGET=EXISTING_SYNTHETIC_CLONE_NOT_APPROVED_FOR_REAL_USERS
DB_R31_11_4_SEPARATE_AUTH_POSTGRES=NOT_PROVISIONED
DB_R31_11_4_FIREBASE_TWO_USERS=PENDING_SECOND_APPROVED_ACCOUNT
DB_R31_11_4_FIREBASE_TO_DB_ACCEPTANCE=NOT_EXECUTED
DB_R31_11_4_EXTERNAL_MTLS_HTTPS=NOT_APPROVED
DB_R31_11_4_FINANCIAL_APPLY=LOCKED
DB_R31_11_4_RELEASE=PRODUCTION_BLOCKED_PRIVATE_ACCEPTANCE_PENDING
\`\`\`

Stop and review if any unexpected container/database already exists;
do not delete or overwrite it. This is **not** a request to provision new
services immediately.

## Excluded / quarantined

**R31.12 Invoice + GST + Reconciliation integration stays QUARANTINED.**
The reconciliation engine's original v2.51/Matrix v2.39 real financial
certification and production financial writes remain separately locked.
