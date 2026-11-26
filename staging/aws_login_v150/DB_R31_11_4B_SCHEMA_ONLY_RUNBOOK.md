# DB-R31.11.4B — Dedicated QA RLS Schema-Only Installation

**Release scope:** private PostgreSQL tenant RLS schema only. **Not** bank payment
reconciliation, payment allocation, GST, invoicing or financial Apply. R31.12
financial integration remains **QUARANTINED**.

## Latest AWS evidence (operator supplied)

R31.11.4A provisioning is complete:
- Existing R31 private isolation preflight: PASS
- Separate Docker container: \`sbi-r3114-private-postgres\`
- Separate internal network: \`sbi-r3114-private-isolated\`
- Dedicated database: \`sbi_r31_11_4_auth_qa_20261126\`
- R31.11.4 read-only audit: new QA database FOUND; RLS schema
  \`NOT_PROVISIONED_DBA_APPROVAL_REQUIRED\`
- Existing synthetic QA clone unchanged; no public Caddy route
- Two approved genuine Firebase user identities absent, mTLS HTTPS not
  approved, financial Apply locked.

## Implementation

Files:
- \`r31_11_4b_schema_only_up.sql\` — atomic PostgreSQL 16 migration
- \`r31_11_4b_schema_only_runner.py\` — plan-only by default, explicit
  operator-approved QA-only mutation
- \`test_r31_11_4b_schema_only_runner.py\` — focused offline fail-closed tests
- \`.github/workflows/sbi-r31-11-4b-schema-only-qa.yml\` — *disposable* real
  PostgreSQL 16 schema / deny-by-default / repeat-apply rejection integration

This derives only the verified R31.11 **source-evidence** shape and tenant
RLS architecture (four tables, invoker view, schema mapping function).
The table layout is **minimal**; it is NOT certified against the future
complete financial engine / existing production reporting schema.
A real v2.51 financial release is out of scope.

Post-migration QA state:
- Four new, empty \`sbi\` source-evidence tables
- Four forced-RLS \`SELECT\` policies
- \`security_invoker=true\` received-source view
- Protected \`r311_auth.role_owner_map\` table **EMPTY**
- Two \`r311_qa_tenant_a/b\` roles **NOLOGIN** / NOINHERIT / NOBYPASSRLS
- \`r311_auth.current_tenant_uid()\` returns no UID for unmapped logins
- **No** \`r3113_login_a/b\`, passwords, Firebase UID mappings, source rows or
  grants for INSERT/UPDATE/DELETE to tenant roles
- Shared report role has no inherited access; there is no fallback
- Original R31.11 synthetic clone, original QA, main PostgreSQL, Caddy,
  Firebase, mTLS and application deployment are unchanged.

### Operator procedure

1. Review the [R31.11.4B draft PR](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pulls)
   and verified GitHub CI before applying any database schema.
2. Fetch the reviewed branch and create a **fresh detached SHA-pinned worktree**.
   Do not reuse the prior R31.11.4A creation script, whose resource names
   are now expected to exist.
3. Run the 4B runner **without options** first:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4b/source/staging/aws_login_v150/r31_11_4b_schema_only_runner.py
\`\`\`

Expected preflight:
\`\`\`text
DB_R31_11_4B_PRIVATE_ISOLATION=PASS
DB_R31_11_4B_NEW_DATABASE=EMPTY_NO_LOGIN_ROLES
DB_R31_11_4B_MODE=READONLY_PLAN_ONLY_NO_CHANGES
DB_R31_11_4B_FINANCIAL_APPLY=LOCKED
DB_R31_11_4B_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING
\`\`\`

4. Only with a deliberate DBA/security approval for **persistent creation of
   the above structures in the dedicated private QA database**, execute once:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4b/source/staging/aws_login_v150/r31_11_4b_schema_only_runner.py \
  --apply --approve R3114B_SCHEMA_ONLY_PRIVATE_QA
\`\`\`

If any schema, policies or roles already exist, this is **NOT** a repair
utility: it stops and refuses to overwrite. Do not rerun or manually drop
roles/objects after a partial failure; inspect with the read-only auditors.

Successful apply requires:
\`\`\`text
DB_R31_11_4B_FORCED_RLS_FOUR_TABLES=PASS
DB_R31_11_4B_SECURITY_INVOKER_VIEW=PASS
DB_R31_11_4B_ROLE_OWNER_MAPPING=EMPTY_NO_REAL_USERS
DB_R31_11_4B_LOGIN_ROLES=NONE_PROVISIONED
DB_R31_11_4B_SCHEMA_ONLY=PASS_PRIVATE_QA
DB_R31_11_4B_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING
\`\`\`

Next, run the same existing R31.11.4 read-only readiness audit. It should
distinguish \`DB_R31_11_4_RLS_SCHEMA=PASS_SCHEMA_ONLY_NO_LOGIN_ROLES\`
from \`DB_R31_11_4_RESTRICTED_LOGIN_ROLE_CATALOG=NOT_PROVISIONED_YET\`.

### Do not assume

GitHub synthetic PostgreSQL CI cannot verify a genuine signed Firebase session,
a second approved Firebase account, live HTTPS/mTLS, live application startup
or AWS DBA authorization. Even if the schema succeeds, production remains
blocked until approved two-user authentication and runtime privilege gates are
demonstrated. No scheduling, automatic rollout or production writes authorized.

**Do not execute** older CI-only scripts containing synthetic fixed passwords.
