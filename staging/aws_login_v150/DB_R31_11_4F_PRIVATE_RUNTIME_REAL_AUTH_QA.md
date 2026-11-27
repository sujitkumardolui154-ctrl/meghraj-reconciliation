# DB-R31.11.4F — REAL two-account Firebase session -> PG RLS private in-process QA

**Candidate implementation. Not a production deploy.**
R31.12 invoice/GST/reconciliation integration remains **QUARANTINED**.
Financial Apply remains **LOCKED**. External mTLS HTTPS remains **PENDING**.

## What this stage does

- Default invocation: a **read-only** AWS and Firebase Admin readiness preflight.
- Approved execution: prompt the operator locally in AWS terminal for the two
  approved *existing* test-user passwords, hidden with `getpass`.
  Approved emails and UIDs are read from the existing locally protected
  R31.11.4C Firebase account receipt; passwords/UIDs never print.
- Sign in to the **actual existing Firebase project** via the existing
  `FIREBASE_WEB_API_KEY` currently read from the pinned existing private
  QA stage. Independently verify both real ID tokens and approved Firebase UIDs
  through Google Admin SDK. No account/claim creation, password change or
  token revocation. Fail-closed on project mismatch.
- Build the **minimal, non-root, one-shot** image that copies the exact
  production `dashboard_sessions.install_sessions` middleware,
  `r31_11_4_runtime_rls_adapter`, read-only Flask route, and 4F test probe.
  Nothing else. No application listener, no public port and no financial API.
- Give the one-shot process **two private Docker networks**: an ephemeral
  outbound-only Firebase network (dedicated to this candidate, then removed)
  and the existing internal QA database network. No Caddy proxy change.
  No production database mounted or available as a configured target.
- Mount current, protected UID10001 QA RLS role secrets **read-only**.
  Copy the *existing local AWS gcloud Application Default Credentials* into
  a temporary UID10001-only mode-0600 file solely for this probe; mount it
  read-only and remove the temporary copy in cleanup. The original ADC file
  is not modified. No secret is added to GitHub, command arguments, image,
  environment variables, Docker labels, stdout or permanent QA files.
- Stream both short-lived Firebase ID tokens via process stdin, **not**
  a command argument/environment variable/file. The in-container Flask
  `test_client()` uses real Auth SDK to issue/verify Firebase session cookies
  (`check_revoked=True`) and makes the real RLS adapter connect by password
  as `r3113_login_a` and `r3113_login_b`, respectively.
- Check anonymous + tampered cookie denial, authenticated test A->PG A,
  test B->PG B, forged cross-tenant UID/header ignored, restricted GET-only
  source view empty, unauthorized PUT/POST denied, all financial flags false.
- Verify the QA evidence tables remained empty and the two owner mappings
  remain intact, unchanged Caddy fingerprint and no leftover temporary
  container/network/temporary ADC copy.

## Distinction between real/auth and mock/HTTP

The in-container acceptance uses **real** Google Firebase ID tokens,
session-cookie signing/verification and **real** private PostgreSQL
password-authenticated RLS queries. Its HTTP layer is Flask's **in-process
test client** and not an external network listener; therefore it does NOT
prove HTTP ingress, browser HTTPS/mTLS, old-cookie actual expiry or revoked
real-session end-to-end rejection. No real user refresh tokens are revoked:
doing so would disrupt the approved test accounts. No customer evidence is
inserted by this stage (R31.11.4D-2 already tested synthetic cross-owner rows
with ROLLBACK). CI uses only mocked users and mocked DB.

## Explicit approval guard

`--execute --approve R3114F_TWO_REAL_FIREBASE_TESTS_QA_ONLY` must be
typed by the authorized operator AFTER pinning and reviewing source.
Default mode without `--execute` performs no Docker network, image,
container, file or authentication changes.

## Commands (replace SHA with this branch's final CI-verified HEAD)

```bash
BASE=/home/ubuntu/sbi-r31-11-4e-fix/source
TARGET=/home/ubuntu/sbi-r31-11-4f/source
BRANCH=feature/sbi-r31-11-4f-private-real-firebase-qa-20261127
SHA=<REVIEWED_FULL_40_CHARACTER_GITHUB_COMMIT_SHA>
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
mkdir -p /home/ubuntu/sbi-r31-11-4f
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"

PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
OP="$TARGET/staging/aws_login_v150/r31_11_4f_private_runtime_operator.py"

"$PY" -u "$OP" --source-sha "$SHA"

# Only after the previous read-only preflight reports PASS and the explicit
# QA-only execution approval is confirmed:
"$PY" -u "$OP" --source-sha "$SHA" --execute \
  --approve R3114F_TWO_REAL_FIREBASE_TESTS_QA_ONLY
```

Requires: AWS terminal TTY, `sudo -n docker`, existing `sbi-r31-auth-private-qa`
with matching approved pinned image + Firebase web API key, existing
`~/.config/gcloud/application_default_credentials.json` (owner-only),
Firebase Admin SDK + receipt, existing UID10001 protected QA secret bundle,
and dedicated PG16 container `sbi-r3114-private-postgres`. No automatic
modification if prerequisites are not met.

**Do not paste user emails, Firebase passwords, ID/session cookies, Google ADC
or OAuth secrets into this chat or GitHub.** Only share `DB_R31_11_4F_*`
status lines.

## Expected read-only preflight receipts

```text
DB_R31_11_4E_PRIVATE_PG16_RLS=PASS_READONLY
DB_R31_11_4E_TWO_REAL_FIREBASE_USERS=PASS_ADMIN_READONLY
DB_R31_11_4E_SECRET_METADATA=PASS_UID10001_MODE0600
DB_R31_11_4E_RUNTIME=UNDEPLOYED_APPROVAL_REQUIRED
DB_R31_11_4F_READONLY_PREFLIGHT=PASS
DB_R31_11_4F_MODE=READONLY_PLAN_NO_DOCKER_CHANGES
DB_R31_11_4F_FINANCIAL_APPLY=LOCKED
DB_R31_11_4F_R3112=QUARANTINED
DB_R31_11_4F_RELEASE=PRODUCTION_BLOCKED
```

## Required post-execution receipts (if successful)

```text
DB_R31_11_4F_TEST_A_PASSWORD_SIGNIN=PASS_REAL_FIREBASE
DB_R31_11_4F_TEST_B_PASSWORD_SIGNIN=PASS_REAL_FIREBASE
DB_R31_11_4F_PRIVATE_CANDIDATE=PASS_NO_PUBLIC_PORTS
DB_R31_11_4F_REAL_FIREBASE_TWO_TOKEN_IDENTITIES=PASS_VERIFIED
DB_R31_11_4F_ANONYMOUS_AND_INVALID_COOKIE=DENIED_PASS
DB_R31_11_4F_TENANT_A_FIREBASE_SESSION_TO_PG=PASS_READONLY
DB_R31_11_4F_TENANT_B_FIREBASE_SESSION_TO_PG=PASS_READONLY
DB_R31_11_4F_FORGED_UID_AND_PG_ROLE=IGNORED_PASS
DB_R31_11_4F_FINANCIAL_WRITE_ENDPOINT=DENIED_PASS
DB_R31_11_4F_REAL_SESSIONS=PASS_TWO_FIREBASE_UID_BOUND_TO_PG
DB_R31_11_4F_EPHEMERAL_RESOURCES=REMOVED
DB_R31_11_4F_AFTER_DB_ROWS=ZERO_OWNER_MAPS_TWO
DB_R31_11_4F_MODE=APPROVED_EPHEMERAL_QA_COMPLETED
DB_R31_11_4F_EXTERNAL_MTLS_HTTPS=PENDING
DB_R31_11_4F_FINANCIAL_APPLY=LOCKED
DB_R31_11_4F_R3112=QUARANTINED
DB_R31_11_4F_RELEASE=PRODUCTION_BLOCKED
```

On STOP: do not rerun 4A/4B/4C or modify secrets. The operator attempts
cleanup even on failed probes; if a temporary resource remains or cleanup
requires manual review, **STOP** and inspect **metadata only** before
repeating execution. Do not recreate either QA PostgreSQL database, the
Firebase users, the original credential bundle or the private network.

## Separately gated later stages

- Real old-session expiry/revocation (requires controlled non-disruptive test
  design; cannot be inferred from tampered-cookie rejection).
- Approved private HTTP listener/access path and external mTLS HTTPS,
  including actual two-session browser HTTP, method, origin, TLS and
  certificate negative tests.
- Production safety approval and R31.12 (QUARANTINED until approved).
