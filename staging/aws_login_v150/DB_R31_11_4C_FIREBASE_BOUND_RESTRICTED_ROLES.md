# DB-R31.11.4C — Firebase-bound Restricted PostgreSQL Login Roles

**Status: APPROVAL-GATED SECURITY CANDIDATE ONLY.**
R31.11.4B schema has already been installed successfully in AWS, but
two **distinct real, approved Firebase TEST users** are not yet verified.
Until those users are available, **DO NOT apply the role provisioning step**.
Do not rerun R31.11.4A infrastructure or R31.11.4B schema migrations.

## What is done / what is not done

- Prepared a guarded, read-only-by-default R31.11.4C operator program:
  \`r31_11_4c_firebase_bound_login_roles.py\`
- Uses only the exact existing isolated container
  \`sbi-r3114-private-postgres\` and database
  \`sbi_r31_11_4_auth_qa_20261126\`, never the old R31.11 synthetic clone.
- Checks original private isolation and 4B schema/forced-RLS settings,
  empty owner map, no LOGIN roles, zero source/payment rows and unchanged Caddy.
- Supports locally verifying two **existing** Firebase test accounts through
  the Firebase Admin SDK. Does NOT create accounts, passwords, reset claims,
  alter authentication settings, or accept a second account guessed from a
  name. Both accounts must be enabled, email-verified, carry
  \`dil_dashboard=true\`, and **not** carry \`dil_admin=true\`.
- Critical project binding: the current \`dashboard_sessions.py\` uses
  \`PROJECT="meghraj-reconciliation"\`. R31.11.4C deliberately validates
  accounts in this **exact** Firebase project. If AWS staging credentials
  reference a different Firebase project, **STOP**, independently review
  and choose the approved project; do not override in code or silently
  substitute \`sbi-r9-staging\` test credentials.
- A successful Firebase Admin preflight writes a private mode-0600 local
  receipt of the two tested UIDs and emails. It never prints their IDs,
  passwords, tokens or claims. Requires securely configured existing
  Firebase Admin **Application Default Credentials** authorized for the
  correct Firebase project; do not paste service-account JSON, access tokens
  or passwords into ChatGPT or GitHub.
- Only after two-user approval, \`--apply\` can create exactly two LOGIN
  roles \`r3113_login_a/b\` and their one-to-one
  \`r311_auth.role_owner_map\` rows. It uses PostgreSQL 16 role grants
  with \`INHERIT TRUE, SET FALSE, ADMIN FALSE\`, no superuser,
  BYPASSRLS, CREATEDB, CREATEROLE or financial table DML.
- New random login passwords are generated in memory. Only salted
  \`SCRAM-SHA-256\` verifiers go to the Postgres SQL script via stdin.
  Passwords reside only in root-restricted host-created mode-0600 files,
  later chowned to the non-root private application image UID/GID
  \`10001:10001\`. No password in process args, GitHub, Docker config,
  shell history or application code.
- The runtime adapter is **not** deployed. Private HTTPS/mTLS acceptance
  and two independently authenticated session end-to-end tests remain
  separate pending work. The new database is not production.

## Minimal QA security flow

1. Install PostgreSQL RLS schema: **DONE in R31.11.4B AWS**. Never repeat.
2. Read-only 4C preflight: catalog and original QA isolation, two-user
   approval state. No DB writes and no password creation.
3. Once the security owner has **two different existing approved Firebase
   TEST accounts** in \`meghraj-reconciliation\`, and the AWS operator has
   already authorized the correct Firebase Admin read identity, run
   \`--prepare-users\` locally. Emails are requested in a hidden prompt.
   Requires working \`firebase-admin\` Python module and genuine existing
   Application Default Credentials. If those are unavailable, stop.
4. Run read-only 4C preflight again, checking two distinct approved
   Firebase users. This re-verifies both accounts and their current claims.
5. Separately approve the exact QA role-creation action. Execute
   \`--apply --approve R3114C_TWO_VERIFIED_TEST_USERS_QA_ONLY\` **once**.
   It re-verifies Firebase identities before any SQL. If an object/file
   already exists, stop: **no overwrite, cleanup or automatic retry**.
6. Confirm owner-mapping counts, database-role permissions and file mode.
   Do **not** set the runtime feature flag yet. The R31.11.4D protected
   session/HTTPS acceptance remains pending.

## Operator commands (after QA source is reviewed and SHA-pinned)

Read-only preflight (always safe to run, no Firebase write):

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4c/source/staging/aws_login_v150/r31_11_4c_firebase_bound_login_roles.py
\`\`\`

Expected current outcome while only one or no approved test accounts exist:

\`\`\`text
DB_R31_11_4C_RLS_SCHEMA=PASS_4B_READONLY
DB_R31_11_4C_ROLE_MAPPING=EMPTY_NO_LOGINS
DB_R31_11_4C_TWO_APPROVED_FIREBASE_USERS=PENDING_LOCAL_VERIFICATION
DB_R31_11_4C_MODE=READONLY_PLAN_ONLY_NO_CHANGES
DB_R31_11_4C_FINANCIAL_APPLY=LOCKED
DB_R31_11_4C_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING
\`\`\`

Once *both* independently approved, non-admin test identities exist, an
authorized security operator can verify them privately:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4c/source/staging/aws_login_v150/r31_11_4c_firebase_bound_login_roles.py --prepare-users
\`\`\`

The script asks for two existing QA email addresses through hidden terminal
prompts. It makes **Firebase READ calls only** and creates a locally
restricted approval file. Never provide account credentials in chat.

When and only when **the two-account preflight passes** and persistent
two-role creation is explicitly approved for this disposable QA database,
the one-time provisioning command is:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4c/source/staging/aws_login_v150/r31_11_4c_firebase_bound_login_roles.py \
  --apply --approve R3114C_TWO_VERIFIED_TEST_USERS_QA_ONLY
\`\`\`

\`--apply\` will create SQL roles, two mappings and private host files.
This is not a read-only command and **is NOT approved by a green CI check**.
It never deploys application containers or enables a public route. Running
\`--apply\` twice or after partial failure is prohibited: stop for
independent state review.

Expected status **only after successful, approved real two-user application**:

\`\`\`text
DB_R31_11_4C_RESTRICTED_PASSWORD_LOGINS=PASS_TWO_REAL_USERS
DB_R31_11_4C_DB_SESSION_USER_UID_MAPPING=PASS_TWO_DISTINCT
DB_R31_11_4C_APP_SECRETS=MODE0600_UID10001_NOT_DEPLOYED
DB_R31_11_4C_DML_PRIVILEGES=DENIED
DB_R31_11_4C_RUNTIME_ADAPTER=NOT_DEPLOYED
DB_R31_11_4C_EXTERNAL_MTLS_HTTPS=PENDING
DB_R31_11_4C_FINANCIAL_APPLY=LOCKED
\`\`\`

These are illustrative expected lines, not live AWS proof.

## CI scope and important limitations

The dedicated workflow \`sbi-r31-11-4c-firebase-bound-login-qa.yml\`
runs focused unit tests of project/UID/claims checks and uses a disposable
PostgreSQL 16 database with **FAKE** Firebase UID strings and publicly known
CI-only passwords. It exercises authentic PostgreSQL password-based LOGIN
roles, strict owner isolation, blocked write privileges, protected map and
replay denial. Passing CI does **not** prove Firebase users were verified,
AWS credentials work, DB role credentials were deployed, or external HTTPS
authentication passed.

Do not use the CI-only fake identities/passwords in AWS. Do not attach the
new internal-only DB to Caddy or publicly publish port 5432.

**Production Apply: LOCKED. R31.12 invoice/GST/reconciliation: QUARANTINED.**
