# DB-R31.11.4A — New Isolated PostgreSQL 16 Provisioning

**Scope:** Infrastructure only. Original R31.11.2 synthetic RLS PASS remains
authoritative; do not repeat it and do not alter its database. This milestone
does NOT grant real Firebase access, create restricted login roles, apply
invoice/GST or financial rules, enable database writes in production, or
expose Caddy/public HTTPS.

## Latest user evidence

From original DB-R31.11.4 private readiness:
- \`DB_R31_PRIVATE_ISOLATION_PREFLIGHT=PASS\`
- \`DB_R31_11_4_CADDY_PRIVATE_QA_REFERENCE=ABSENT\`
- \`DB_R31_11_4_SEPARATE_AUTH_POSTGRES=NOT_PROVISIONED\`
- \`DB_R31_11_4_LOGIN_ROLE_PROVISIONING=NOT_AUTHORIZED_BY_THIS_AUDIT\`
- Real two-user Firebase acceptance / HTTPS were not tested.
- Financial Apply remains locked; R31.12 remains quarantined.

## New exact-name resources (NOT existing until operator executes --apply)

| Resource | Identifier |
| --- | --- |
| PostgreSQL Docker container | \`sbi-r3114-private-postgres\` |
| Internal Docker bridge | \`sbi-r3114-private-isolated\` |
| New private Docker volume | \`sbi-r3114-authdata-20261126\` |
| New empty PostgreSQL 16 database | \`sbi_r31_11_4_auth_qa_20261126\` |
| Private host-owned 0700 secret directory | \`/home/ubuntu/sbi-r3114a-private\` |
| Generated 0600 password file | \`/home/ubuntu/sbi-r3114a-private/postgres-init-password\` |
| Disposable empty-schema restore probe | \`sbi_r3114_restore_probe_20261126\` |

New PostgreSQL uses the *exact preinstalled local image digest* from
the existing private R31 synthetic PostgreSQL 16 container. The script
requires a standard PostgreSQL entrypoint and PostgreSQL major version 16,
does not pull or build an image, and refuses if any target container,
network, volume, secret directory or secret file already exists.

**Corrected private password-file access:** PostgreSQL's official entrypoint
switches to the non-root \`postgres\` user before reading
\`POSTGRES_PASSWORD_FILE\`. A 0600 file owned only by the AWS operator is
not readable by that user. The corrected provisioner discovers the UID/GID
of \`postgres\` in the pinned image, uses \`sudo -n chown\` on ONLY the newly
created secret file, then verifies mode 0600 and that exact UID/GID.
The password never enters an environment variable, command argument or log.

**Do not use the previous GitHub commit**
\`552e942dd6f77e57a91f8b5bbc7d872fee84418d\` for \`--apply\`.
Fetch the verified new commit before executing. If the earlier checkout is
already mounted, create a separate SHA-pinned worktree instead of modifying it.

The empty-schema restore uses \`pg_restore --clean --if-exists\` **only in
the disposable empty restore-probe database**, preventing a duplicate
\`public\` schema error without touching the new QA main database.

The new Docker network is \`--internal\`, bridge, non-attachable;
PostgreSQL has no host-published ports, no Docker socket or old QA/production
mount. The separate container uses \`--read-only\` root filesystem with
only dedicated database volume, private read-only password-file bind, and
necessary bounded tmpfs, \`no-new-privileges\`, cap restrictions and
resource limits. Database initialization obtains a securely generated random
password from the bind file via \`POSTGRES_PASSWORD_FILE\`; no password is
placed in shell history, GitHub code, application CLI, Docker inspect
environment, chat, or CI logs.

**IMPORTANT:** The new PostgreSQL container does not yet contain RLS tables,
login roles, Firebase UID mappings, payments or invoice data. It is an empty,
isolated infrastructure foundation only.

## Trusted AWS Ubuntu operator sequence

Prerequisite: use the repository checkout from which R31.11.4 has been
verified, with GitHub SHA-pinned worktree. Do not use a public host or run
this against a production database.

### Step 1: Fetch and pin exact source

\`\`\`bash
git -C /home/ubuntu/sbi-db-management/db-r31-central-catalog/source fetch origin feature/sbi-r31-11-4a-isolated-postgres-provision-20261126

mkdir -p /home/ubuntu/sbi-r31-11-4a

git -C /home/ubuntu/sbi-db-management/db-r31-central-catalog/source worktree add --detach /home/ubuntu/sbi-r31-11-4a/source <REPLACE_WITH_VERIFIED_FINAL_SHA>
\`\`\`

### Step 2: Plan / preflight (READ ONLY)

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4a/source/staging/aws_login_v150/r31_11_4a_isolated_postgres_provision.py
\`\`\`

Expected when every required resource name is unused:
\`\`\`text
DB_R31_PRIVATE_ISOLATION_PREFLIGHT=PASS
DB_R31_11_4A_ORIGINAL_PRIVATE_ISOLATION=PASS
DB_R31_11_4A_LOCAL_POSTGRES16_IMAGE=PINNED_FROM_EXISTING_QA
DB_R31_11_4A_RESOURCE_NAMES=ALL_UNUSED
DB_R31_11_4A_CADDY_EXPOSURE=NO_NEW_ROUTE
DB_R31_11_4A_MODE=READONLY_PLAN_ONLY_NO_CHANGES
DB_R31_11_4A_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING
\`\`\`

If the preflight refuses because a name/file already exists, STOP. It is
unsafe to "clean up" or overwrite without independent provenance review.
Never rerun the script in \`--apply\` mode after a partial attempt.

### Step 3: Apply NEW QA infrastructure only (explicit operator authorization)

After reviewing the Step 2 output and scope, the owner/operator can
deliberately run:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-4a/source/staging/aws_login_v150/r31_11_4a_isolated_postgres_provision.py --apply --approve R3114A_PRIVATE_QA_ONLY
\`\`\`

This **writes only to newly created disposable QA resources**, not financial
ledgers. It creates the password file, internal network, Docker volume,
isolated PostgreSQL container and empty dedicated database. It verifies
the exact image/directory/network identity, zero public ports, and checks
the original QA/Caddy again. Finally, it performs an **empty-schema-only**
\`pg_dump\` -> isolated disposable restore-database -> exact-name \`dropdb\`
drill, never a restore over the new main QA database.

Expected key status lines if everything passes:
\`\`\`text
DB_R31_11_4A_NETWORK=CREATED_INTERNAL_ONLY
DB_R31_11_4A_VOLUME=CREATED_NEW_DEDICATED
DB_R31_11_4A_POSTGRES_CONTAINER=CREATED_FROM_PINNED_IMAGE
DB_R31_11_4A_NETWORK_AND_FILESYSTEM=PASS_NO_PUBLIC_PORTS
DB_R31_11_4A_NEW_DATABASE=EXACT_EMPTY_IDENTITY_PASS
DB_R31_11_4A_EMPTY_BASELINE_RESTORE=PASS_DISPOSABLE_PROBE_ONLY
DB_R31_11_4A_ORIGINAL_QA=UNCHANGED_AS_PREFLIGHTED
DB_R31_11_4A_CADDY=UNCHANGED_NO_PUBLIC_QA_ROUTE
DB_R31_11_4A_QA_INFRASTRUCTURE=PASS_PROVISIONED_ISOLATED
DB_R31_11_4A_FINANCIAL_APPLY=LOCKED
DB_R31_11_4A_RELEASE=PRODUCTION_BLOCKED_AUTH_ACCEPTANCE_PENDING
\`\`\`

These are example/expected receipts only; AWS has NOT been executed from
GitHub or ChatGPT. For every STOP, share only the \`DB_R31_11_4A_\` and
\`STOP=...\` status lines. **Never paste the password, secret file contents,
raw Docker inspect/config or private bank/Firebase data.**

## Limits and next gate

The empty-schema restore drill checks the basic backup/restore command path,
not full application backup, state recovery, rollback of tenant mappings, or
durable production disaster recovery. Before any real Firebase acceptance,
security and DBA owners must separately review dedicated QA RLS schema,
privileged bootstrap separation, two actual approved Firebase test owners,
least-privilege login roles, private role mapping, revocation, protected
HTTPS/mTLS, and full rollback evidence.

On later review, the R31.11.4 readiness auditor should recognize this
instance as isolated and report **RLS_SCHEMA=NOT_PROVISIONED...** until its
separate security migration is deliberately approved.

Do not apply the public CI-only fixture
\`r31_11_3_ci_disposable_login_provision.sql\` on AWS. That file contains
fake owner IDs and public disposable passwords solely for GitHub QA.
Do not merge, expose production ports or enable financial Apply.

**R31.12 financial/invoice/GST integration remains quarantined.**
