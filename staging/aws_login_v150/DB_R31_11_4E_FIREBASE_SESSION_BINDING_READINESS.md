# DB-R31.11.4E — Private Firebase session -> PostgreSQL RLS acceptance

**STATUS: SOURCE / MOCK-CONTRACT QA + AWS READ-ONLY READINESS ONLY.**

Prerequisites already supported by operator-provided QA outputs:

- R31.11.4C: exactly two real, approved Firebase test users, one-to-one
  PostgreSQL `r3113_login_a/b` mapping, file modes 0600 and UID 10001.
- R31.11.4D: both password-authenticated PostgreSQL 16 private TCP logins PASS.
- R31.11.4D-2: synthetic cross-tenant SELECT and protected mapping/write denial
  PASS using transaction-local fixtures; rollback and post-test emptiness PASS.
- Private Postgres: `sbi-r3114-private-postgres`, database
  `sbi_r31_11_4_auth_qa_20261126`, internal non-attachable network
  `sbi-r3114-private-isolated`, zero published ports.
- **Production financial Apply is LOCKED, R31.12 is QUARANTINED.**

## What this proposed 4E increment actually verifies

The new source-only test contract exercises the actual Flask
`install_sessions()` middleware and the R31.11.4 private route with
**MOCKED Firebase session verification** and **MOCKED database reads**. It
demonstrates that the session-returned user, rather than HTTP tenant headers
or query arguments, is supplied to the adapter; revoked/invalid-session
paths, disabled users and missing dashboard claims fail before database
access; read-only financial response fields remain false.

The `r31_11_4e_session_binding_readiness.py` operator audit checks:

1. Existing dedicated PostgreSQL 16 isolation/network and no Caddy QA route.
2. Exactly two restricted role memberships and two owner UID mappings.
3. Four forced-RLS tables, a security-invoker view, denied mapping read/write
   privileges and zero payment evidence rows.
4. Two real approved Firebase test records reverified through Firebase Admin
   SDK, via local restricted approval receipt.
5. Secret ownership **metadata only** (never reads secret contents).
6. No expected private API candidate container running; checks source-only
   flag, read-only database options, and non-root candidate Dockerfile.

The readiness audit performs only SELECT / metadata / Firebase Admin
get_user() calls. It creates no Docker containers, cloud resources, account
permissions, secrets, database roles, fixtures, routes or token files.
It never enables the private runtime.

## Run only the pinned source-revision read-only audit

From AWS Ubuntu, after separately checking the exact tested GitHub commit:

```bash
SRC=/home/ubuntu/sbi-r31-11-4e/source
EXPECTED=<tested-github-commit-sha>
test "$(git -C "$SRC" rev-parse HEAD)" = "$EXPECTED"
test -z "$(git -C "$SRC" status --porcelain)"
/home/ubuntu/sbi-r3114c-firebase-venv/bin/python -u \
  "$SRC/staging/aws_login_v150/r31_11_4e_session_binding_readiness.py"
```

Expected on a verified environment:

```text
DB_R31_11_4E_PRIVATE_PG16_RLS=PASS_READONLY
DB_R31_11_4E_TWO_REAL_FIREBASE_USERS=PASS_ADMIN_READONLY
DB_R31_11_4E_SECRET_METADATA=PASS_UID10001_MODE0600
DB_R31_11_4E_RUNTIME=UNDEPLOYED_APPROVAL_REQUIRED
DB_R31_11_4E_MODE=SOURCE_AND_QA_READINESS_ONLY
DB_R31_11_4E_REAL_SESSION_E2E=NOT_TESTED
DB_R31_11_4E_EXTERNAL_MTLS_HTTPS=PENDING
DB_R31_11_4E_FINANCIAL_APPLY=LOCKED
DB_R31_11_4E_R3112=QUARANTINED
DB_R31_11_4E_RELEASE=PRODUCTION_BLOCKED
```

On STOP, do not rerun any R31.11.4A/B/C `--apply` or modify mapped
secrets. Diagnose read-only and request a separate review.

## NOT proved by 4E source/CI or read-only AWS readiness

- A genuine Firebase Test A session cookie was accepted by the **actual**
  private deployed runtime.
- A genuine Firebase Test B session cookie was independently accepted.
- Replayed/revoked/expired **real** Firebase sessions were denied end-to-end.
- Browser-to-private-runtime access through approved **external mTLS HTTPS**.
- Actual HTTP requests with two different real authenticated browser sessions
  returned distinct RLS-scoped records.
- Production readiness, financial writes, or R31.12 financial/GST/invoice
  integration.

## Next gated phase: real-session private acceptance

Requires a new, explicit security approval and a reviewed operational design
for ephemeral/private candidate execution (without public routing). Must
include two genuinely signed-in **test** accounts, real Firebase Admin
cookie verification with `check_revoked=True`, UID and email_verified /
dashboard claim checks, strict UID -> restricted PG role mapping, private
network isolation, forbidden header/owner forgery and session replay tests.
Never paste Firebase passwords, ID/session tokens, API secrets or owner UIDs
into ChatGPT/GitHub/CI logs. Workload IAM credentials must be reviewed
separately. No production application/Caddy/financial changes.

**All work remains QA-only.** The runtime adapter is not deployed.
External mTLS HTTPS remains PENDING. Financial Apply LOCKED.
R31.12 QUARANTINED.
