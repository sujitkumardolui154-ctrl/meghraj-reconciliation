# DB-R31.11.3 — Firebase-to-Postgres Runtime RLS Adapter (PRIVATE QA)

Status: **CODE CANDIDATE ONLY — NOT DEPLOYED — FINANCIAL APPLY LOCKED**.

## Contract and trust boundary

This stage answers the observed R31.11.2 status:
\`DB_R31_11_2_RUNTIME_TENANT_RLS=NOT_CONNECTED_TO_FIREBASE\`.

The existing R31.11 clone has verified, **NOLOGIN** test group roles:
\`r311_qa_tenant_a\`, \`r311_qa_tenant_b\`. It is not safe to treat
\`SET SESSION AUTHORIZATION\` performed as PostgreSQL superuser as a
production-style application connection. The new runtime adapter must connect
under the **real password-authenticated restricted PostgreSQL LOGIN role**.
An approved Firebase test UID is used only after the backend has verified
a signed session cookie using \`install_sessions(app)\` and checked
\`dil_dashboard\`.

The HTTP handler never receives an owner UID, database role or credential
from user-controlled body/header/query. The backend reads UID from
\`g.dil_user\`, looks it up in a root-protected private mapping file
(\`/run/secrets/r3113-tenant-bindings.json\`, file mode 0600, container
runtime UID-owned), then opens a per-role private password file. That
login role MUST have a single independently approved mapping in
\`r311_auth.role_owner_map\`, where the database's protected
\`SECURITY DEFINER\` function binds **\`session_user\`** to owner_uid.
The adapter explicitly refuses any mismatch between that DB owner UID and
the independently verified Firebase session UID. No \`SET ROLE\` or
\`SET SESSION AUTHORIZATION\` is used in the backend.

Inside a PostgreSQL **read-only transaction** the adapter checks database
identity, \`session_user=current_user=expected_login\`, exact mapped owner,
LOGIN enabled, no superuser, BYPASSRLS, CREATEDB or CREATEROLE, RLS
active for all four source tables, and no INSERT/UPDATE/DELETE privileges.
The report is queried without an application owner filter to ensure that
the DB's RLS policy—not a convenient WHERE clause—is enforcing isolation.
Every returned \`owner_uid\` is also checked against the Firebase UID.
No invoice reconciliation, allocation, bank write or GST operation exists in
this stage.

## Strict private staging packaging

- \`r31_11_3_runtime_rls_adapter.py\`: restricted owner-session read adapter.
- \`r31_11_3_runtime_rls_blueprint.py\`: GET
  \`/api/r31-private-qa/tenant-rls-source\` only.
- \`app.py\`: registers only when **both** original
  \`SBI_R31_PRIVATE_STAGING_ENABLED=isolated-ownerqa-firebase-csrf-v1\`
  and new \`SBI_R31_11_3_RUNTIME_ENABLED=private-firebase-rls-readonly-v1\`.
- \`Dockerfile.r31_11_3_private_candidate\`: separate QA candidate image,
  not the existing public Dockerfile or currently running private image.
- No Caddy config, AWS runtime service, production DB or Firebase account
  has been modified. Original R31.11 cloned rows and roles stay untouched.

## Private prerequisites — NOT YET MET

An authorized DBA/security owner must separately approve all before any
staging deployment or positive real Firebase test:

1. A **new, disposable QA clone** for real-user login integration that does
   not overwrite \`sbi_r31_11_tenant_clone_20261125\` or the original
   \`sbi_r31_owner_qa_20261125\`; backup/revert point and isolated
   network/port proof.
2. Two approved **distinct Firebase test users**, with distinct real UIDs
   and minimal \`dil_dashboard\` claim (avoid unnecessary \`dil_admin\`).
   The unavailable second account must not be invented or bypassed.
3. On that isolated *new* QA clone, one **restricted LOGIN** role per real
   Firebase UID (e.g. \`r3113_login_a\`, \`r3113_login_b\`). Each can inherit
   **only** its corresponding NOLOGIN tenant-role read privileges;
   membership must grant \`INHERIT TRUE\`, \`SET FALSE\`, \`ADMIN FALSE\`.
   No role gets SUPERUSER, BYPASSRLS, CREATEROLE, CREATEDB or financial DML.
   Protect \`r311_auth.role_owner_map\` and map each login role to exactly
   one real verified UID. Do not repurpose or edit existing R31.11 synthetic
   owner mappings or reuse their synthetic UIDs.
4. Non-reusable randomly generated per-role PostgreSQL login passwords
   supplied to mounted container files \`/run/secrets/r3113-*.env\`;
   \`/run/secrets/r3113-tenant-bindings.json\` must contain only approved UID,
   PG login role and private file path mappings. Both files must be mode 0600
   and owned by the container's unprivileged runtime UID. **Never** paste
   values into ChatGPT, GitHub, command history or CI logs. The CI SQL
   contains intentionally public DISPOSABLE passwords and MUST NOT be
   reused anywhere else.
5. Review real Firebase-to-database positive and cross-owner negative QA,
   anonymous 401, rejected owner query/header injection, CSRF/cookies for
   any mutating API, schema/view/permission checks, rollback and client
   certificate approval before any external HTTPS test.
6. Finance and security sign-off and separate full reconciliation release
   evidence before production. This stage never unlocks financial writes.

## Private config shape (placeholders, NOT values to commit)

Mappings, in a private file:

\`\`\`json
{"version":1,
 "database":"sbi_r31_11_tenant_clone_20261125",
 "bindings":[
   {"firebase_uid":"REPLACE_WITH_VERIFIED_TEST_UID_A",
    "pg_login_role":"r3113_login_a",
    "secret_path":"/run/secrets/r3113-owner-a.env"}
 ]}
\`\`\`

Restricted role secret file, also private and never committed:

\`\`\`text
PGHOST=sbi-synthetic-postgres-38-31
PGPORT=5432
PGDATABASE=sbi_r31_11_tenant_clone_20261125
PGUSER=r3113_login_a
PGPASSWORD=REPLACE_WITH_PRIVATE_STRONG_PASSWORD
\`\`\`

**Note:** The examples show contract shape only; the target DB name is
hard-pinned to the original R31.11 clone and must not be repurposed for a new
physical clone without a separately reviewed adapter/config update.
Do not run the adapter against a different DB by overriding env vars.
Until a separately approved migration/credential and synthetic fixture
plan exists, the new endpoint must remain disabled.

## Combined essential QA (GitHub only)

The R31.11.3 CI tests use a disposable PostgreSQL 16 instance that has
no production database and no real bank data. They apply the existing
R31.11 candidate, seed two fake test owners, add two independent **LOGIN**
roles with CI-only passwords, check inherited RLS read permissions and test
the actual adapter using password login. Additional offline regression
exercises private files, feature flags, owner identity, no write permissions,
wrong DB/role/UID and forbidden cross-owner rows.

The AWS runtime has **not** been modified or tested for R31.11.3.
\`R31.12\` invoice/GST/reconciliation integration remains **quarantined**.
