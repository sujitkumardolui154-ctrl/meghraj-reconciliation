# DB-R31.11 — Existing Clone Read-Only Resume (Do Not Recreate)

## Why this exists

The original R31.11 combined runner stopped with:
\`STOP=DB_R31_11_CLONE_ALREADY_EXISTS_REVIEW_REQUIRED\`.

That is a correct protective response. It means only that the dedicated clone
name is already present; it does **not** establish that it is empty, migrated,
synthetic, healthy or safe to overwrite. Do not drop, truncate or recreate it.

This extension adds \`r31_11_existing_clone_readonly_audit.py\` for **inspection
only**. It cannot install an RLS migration, insert synthetic fixtures, grant
roles or alter a database, and does not connect the running application to RLS.

## Safety and scope

- Requires original R31 private isolation preflight, pinned stage image and
  internal synthetic PostgreSQL network.
- Checks the **existing** clone named exactly
  \`sbi_r31_11_tenant_clone_20261125\`.
- Never modifies \`sbi_r31_owner_qa_20261125\` or creates a new database.
- Catalog queries use PostgreSQL \`BEGIN READ ONLY\`.
- All fixture checks are aggregated; bank rows, Firebase user identifiers,
  passwords, tokens and PostgreSQL errors are **not** printed.
- If the exact expected synthetic fixture already exists, test two
  PostgreSQL tenant sessions with SELECT queries only.
- Does not validate real two-account Firebase E2E or external HTTPS;
  no credential prompts and no Caddy change.
- R31.12 invoice/GST/reconciliation integration remains **quarantined**.

## Safe outcomes

1. \`DB_R31_11_CLONE_RESUME=MISSING_OR_AMBIGUOUS_NO_CREATION\`: clone cannot
   be found; stop, no creation.
2. \`DB_R31_11_CLONE_RESUME=INCOMPLETE_SCHEMA_REVIEW_REQUIRED\`: schema
   partial or unexpected; inspect independently.
3. \`DB_R31_11_CLONE_RESUME=SCHEMA_PRESENT_RLS_NOT_CERTIFIED\`: tables exist,
   but required restricted roles, four RLS policies, forced flags,
   security-invoker view or shared role restriction do not match; no migration
   is applied.
4. \`DB_R31_11_CLONE_RESUME=RLS_MIGRATED_EMPTY_NO_ISOLATION_FIXTURE\`: catalog
   matches but no 2-owner fixture; role-data isolation not retested.
5. \`DB_R31_11_CLONE_RESUME=UNKNOWN_ROWS_NO_TEST_EXECUTION\`: unexplained data
   or partial fixture; refuse all further activity.
6. \`DB_R31_11_CLONE_ROLE_READS=PASS_BIDIRECTIONAL_READONLY\`: catalog,
   **exact synthetic** fixture and two read-only role sessions confirmed.
   This remains **security QA only**, not production sign-off.

All unrecognized database errors surface only as
\`STOP=DB_R31_11_READONLY_CLONE_AUDIT_UNAVAILABLE\`, with no raw DB output.

## AWS operator command

Run directly in Ubuntu terminal from a **fresh SHA-pinned checkout** of this
reviewed branch:

\`\`\`bash
python3 -u /home/ubuntu/sbi-r31-11-resume/source/staging/aws_login_v150/r31_11_existing_clone_readonly_audit.py
\`\`\`

The command is noninteractive. No source workbook, payment file or Firebase
credentials are needed. It deliberately does not run the earlier clone
creation path.

## After the audit

If the catalog is partial or clone contents unexpected, stop and design an
explicit **separate** repair/migration review. Do not use the original R31.11
runner to force a rerun. No production or persistent QA finance migration is
authorized by this receipt.

If read-only role tests pass, the next engineering question is how to bind
genuine, separately authenticated Firebase users to restricted **database
login roles**, because R31.11's existing test roles are \`NOLOGIN\`.
The second Firebase user is still unavailable and an approved protected
external HTTPS route still does not exist. Existing R31 financial role and
original app adapter are intentionally unchanged.

**Production financial writes: LOCKED.**
