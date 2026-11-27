# DB-R31.11.4I — Combined Authentication Evidence + External mTLS Preparation

**Status:** Github source/CI candidate. AWS execution requires operator action.
**Production financial Apply:** LOCKED.
**R31.12:** ACTIVE_QA_DESIGN_RELEASE_GATED (not production-authorized).
**External mTLS HTTPS:** NOT TESTED.

## Goal

One combined security workflow, using the current validated R31.11.4H
read-only stack, with two modes:

- **Default \`--mode audit\`**: All 4H read-only security checks, QA PG16 RLS,
  two existing approved Firebase Admin user records, UID10001 file metadata,
  zero payment evidence rows, two owner maps, original Caddy config fingerprint
  and 4F resource cleanup; plus read-only Caddy v2 version check and mTLS
  **design-only** file verification. No user password prompt, no Docker
  resource creation, no network change, no local receipt write.
- **Optional \`--mode private-auth\`**: The same full audit, then a separately
  operator-approved, interactive **new** execution of the already-reviewed
  R31.11.4F QA one-shot runner. Uses *only two existing approved test accounts*
  and the dedicated isolated PostgreSQL QA database. Firebase test passwords
  are entered with hidden AWS getpass, no passwords or tokens reach logs,
  shell args, ChatGPT or GitHub. Rechecks the 4H integrity/mTLS design,
  then saves only fixed nonidentifying PASS receipt labels in a **new**
  mode-0600 owner-only local QA file. Does not replace original 4F evidence.
  This mode creates a temporary Docker QA container/egress network and a
  protected temporary ADC copy through the existing 4F operator, then
  verifies their cleanup. It is NOT a read-only-on-host operation.

**Do not invoke \`--mode private-auth\` if private AWS acceptance was already
successful and its original terminal receipts are available.** The prior
R31.11.4F cleanup logs supplied in chat demonstrate only cleanup; they
cannot establish whether real session-to-PG binding passed.

The old R31.11.4F runner may still report the historically accurate
\`DB_R31_11_4F_R3112=QUARANTINED\` status, whereas the current task tracker
[Issue #216](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/216)
supersedes *planning* with R31.12 ACTIVE_QA_DESIGN. In both cases
**production financial Apply is locked, production release blocked**.

## Operator prerequisites

Previously supplied read-only R31.11.4H PASS for commit
\`3e525a965d44f546b4eb1b379b2046ced5890cb2\`.
Stable expected Caddy configuration SHA-256:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

Two actual Firebase-approved test account UIDs must remain one-to-one in
\`r311_auth.role_owner_map\`; private PostgreSQL network must be isolated
and all four evidence tables empty; no 4F temporary container/network/ADC
can remain. Do not reset SQL logins or recreate databases.

An outbound Firebase HTTPS connection is needed **only** in private-auth mode.
Only the operator can enter the two existing test-account passwords locally.
No external mTLS hostname, trusted client CA, server certificate, DNS record,
Caddy ingress route or firewall opening is provisioned by this phase.

## Phase A — exact source pin

Run on AWS Ubuntu:

\`\`\`bash
(
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4h-fixed/source
TARGET=/home/ubuntu/sbi-r31-11-4i/source
BRANCH=feature/sbi-r31-11-4i-combined-auth-mtls-readiness-20261127
SHA=<EXACT_FINAL_40_CHAR_CI_VERIFIED_SHA>
test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4i
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4I_SOURCE=PASS_PINNED"
)
\`\`\`

## Phase B — entire read-only combined audit (recommended first)

\`\`\`bash
SHA=<EXACT_FINAL_40_CHAR_CI_VERIFIED_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4i/source/staging/aws_login_v150/r31_11_4i_combined_auth_mtls.py
"$PY" -B -u "$SCRIPT" --source-sha "$SHA" --mode audit
\`\`\`

Expected on a fully unchanged QA environment:
\`\`\`text
DB_R31_11_4H_COMBINED_READONLY_SECURITY=PASS
DB_R31_11_4I_MTLS_CADDY_VERSION=PASS_V2_READONLY
DB_R31_11_4I_MTLS_REFERENCE=PASS_INVALID_HOSTNAME_DESIGN_ONLY
DB_R31_11_4I_MTLS_EXTERNAL_PREREQUISITES=FQDN_CA_CERTS_APPROVAL_PENDING
DB_R31_11_4I_PRIOR_4F_SESSION_RECEIPT=NOT_PROVIDED
DB_R31_11_4I_COMBINED_READONLY=PASS
DB_R31_11_4I_MODE=AUDIT_ONLY_NO_LOGIN_OR_DOCKER_CHANGES
DB_R31_11_4I_NEW_REAL_SESSIONS=NOT_TESTED_IN_AUDIT_MODE
DB_R31_11_4I_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4I_REAL_EXPIRED_REVOKED_SESSION=NOT_TESTED
DB_R31_11_4I_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4I_FINANCIAL_APPLY=LOCKED
DB_R31_11_4I_PRODUCTION_RELEASE=BLOCKED
\`\`\`

A read-only PASS does NOT imply authentication E2E PASS or mTLS acceptance.

## Phase C — optional real-session combined acceptance

Only after Phase B passes, and if a new private authentication run is
approved and appropriate:

\`\`\`bash
"$PY" -B -u "$SCRIPT" --source-sha "$SHA" --mode private-auth \
  --approve R3114I_TWO_REAL_FIREBASE_TEST_USERS_QA_ONLY
\`\`\`

This explicitly allows R31.11.4F one-shot temporary QA execution, not
production changes. It prompts twice for **existing approved test-account
passwords** (hidden) in the interactive AWS terminal. Never paste passwords,
UIDs, tokens, session cookies, API keys or ADC into this chat.

For a successful new 4I private authentication run:
\`\`\`text
DB_R31_11_4F_TEST_A_PASSWORD_SIGNIN=PASS_REAL_FIREBASE
DB_R31_11_4F_TEST_B_PASSWORD_SIGNIN=PASS_REAL_FIREBASE
DB_R31_11_4F_TENANT_A_FIREBASE_SESSION_TO_PG=PASS_READONLY
DB_R31_11_4F_TENANT_B_FIREBASE_SESSION_TO_PG=PASS_READONLY
DB_R31_11_4F_REAL_SESSIONS=PASS_TWO_FIREBASE_UID_BOUND_TO_PG
DB_R31_11_4F_EPHEMERAL_RESOURCES=REMOVED
DB_R31_11_4F_AFTER_DB_ROWS=ZERO_OWNER_MAPS_TWO
DB_R31_11_4H_COMBINED_READONLY_SECURITY=PASS
DB_R31_11_4I_NEW_AUTH_RECEIPT=PASS_LOCAL_MODE0600_NO_SECRETS
DB_R31_11_4I_NEW_REAL_SESSIONS=PASS_TWO_OWNERS_PRIVATE_PG_ONLY
DB_R31_11_4I_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4I_FINANCIAL_APPLY=LOCKED
DB_R31_11_4I_PRODUCTION_RELEASE=BLOCKED
\`\`\`

The new local receipt is located at
\`/home/ubuntu/sbi-r3114i-private-evidence/r3114i-auth-acceptance.json\`
under owner-only 0700 directory + 0600 file, created with exclusive
O_EXCL and O_NOFOLLOW. It stores ONLY fixed test names, SHA, timing and
status; no Firebase email, UID, password, token, API key or credential.
It is a **local operator execution report**, NOT an independently signed
or externally verified attestation.

It refuses to overwrite an existing file; do not delete a previous
receipt just to repeat tests.

## Fail-closed behavior

Any \`STOP=DB_R31_11_4I_COMBINED_QA_REVIEW_REQUIRED\` is a hard stop.
Do not repeat credentials or database provisioning, modify Caddy, lower
file permissions or open firewall rules. A failed 4F live QA run may
need owner-only inspection of temporary resource **metadata** to verify
cleanup; do not manually delete resources with unverified ownership.

## External mTLS test remains a distinct release gate

**No external mTLS HTTPS service has been launched or tested here.**
Before live end-to-end mTLS tests, separately record and approve:
- A dedicated QA-only hostname and DNS; IP/port exposure and access scope.
- A trusted QA client CA, test-only client/server certificates, renewals and
  revocation controls; never put PEM private keys in GitHub.
- Reviewed Caddy v2 config, Origin allowlist, app/network route and
  explicit rollback. Existing Caddy production route must remain protected.
- Negative TLS cases: no client certificate, wrong CA, expired/revoked cert,
  intercepted/forged session, unauthorized request and per-tenant isolation.
- Production financial Apply LOCKED throughout; R31.12 may only do active QA
  design and synthetic/offline development.
