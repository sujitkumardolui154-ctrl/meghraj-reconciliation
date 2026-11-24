# DB-R31.7: real Firebase test-account acceptance within private QA container

**Source milestone:** Operator's AWS command output for DB-R31.6 on 25 Nov 2026 reports `DB_R31_PRIVATE_STAGE_CONTAINER_CREATED=PASS`, `DB_R31_FIREBASE_SESSION_ANONYMOUS_GUARD=PASS`, unchanged Caddy routing, zero production financial writes, and `PRIVATE_QA_STAGED_NOT_PUBLIC`. No real Firebase account had yet been tested.

## Scope

This test uses the exact existing private Docker container `sbi-r31-auth-private-qa`, image `sbi-r31-auth-qa:7a2298d93b6ace5977dc959acea3c7aa7c7ce4f0`, already connected to isolated `sbi_r31_owner_qa_20261125`. **No rebuild, no public route and no staging redeploy.**

The operator runs `r31_real_firebase_qa_acceptance.py` in their AWS terminal. That script securely prompts for an **existing test account** in the same Firebase Auth project as the AWS dashboard. The account must have the approved `dil_dashboard` claim and have password sign-in enabled. If an account cannot sign in or lacks that claim, the script fails closed; **never create/grant test accounts automatically**.

- Password is captured with `getpass`, sent over HTTPS to Google's Identity Toolkit and never supplied to ChatGPT/GitHub.
- The resulting short-lived Firebase ID token is streamed over Docker process **stdin**, not an argv parameter, environment variable, file, GitHub action or log. The receiving Python process executes `app.test_client()` against the real staged Flask application, so real Firebase ID token verification and signed session-cookie creation occur.
- The smoke fetches real same-origin CSRF token, establishes a Firebase session, verifies `/auth/me`, confirms denied cross-origin POST, and tests private isolated database status.
- Generates a synthetic source XLSX with `Description | SOL ID | Credit Amount`, one valid `001505 | 118.00` and one invalid `001505 | 0`; no real customer transactions. The upload and receipt remain in the **separate private staging evidence volume**.
- Calls original `POST /api/payment-evidence/upload`, then `POST /api/r31-private-qa/receipts/<id>/sync` with valid session+CSRF. Checks original source rows, valid/invalid splits, owner-specific PostgreSQL source records and no invented matching.
- Verifies JSON and CSV report amount is **₹118.00** (not ₹11,800), with exact initial-to-final source credit delta `118.00`, original SOL `001505`, status `NOT_CALCULATED`, one held invalid row, and idempotent replay without double credit.
- **No public HTTP/browser path is exercised.** This is in-container Flask test-client acceptance using **real Firebase**. Public Caddy and production remain untouched.

## Operator command (from existing GitHub repository)

Use a separate clean worktree and pin exact branch commit:

```bash
set -euo pipefail
EXISTING="/home/ubuntu/sbi-db-management/db-r31-central-catalog/source"
TARGET="/home/ubuntu/sbi-r31-private-acceptance/source"
BRANCH="feature/sbi-r31-firebase-private-acceptance-20261125"
SHA="<INSERT_VERIFIED_PR_HEAD_SHA>"
git -C "$EXISTING" fetch -q origin "$BRANCH"
test "$(git -C "$EXISTING" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p "$(dirname "$TARGET")"
if [ ! -e "$TARGET" ]; then
  git -C "$EXISTING" worktree add --detach "$TARGET" "$SHA"
fi
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain --untracked-files=all)"
python3 "$TARGET/staging/aws_login_v150/r31_real_firebase_qa_acceptance.py"
```

At the terminal prompts, type the **Firebase dashboard test email and password**. Never paste them into this conversation. If the QA test account is not configured, the code returns an explicit `STOP=DB_R31_...` and keeps production blocked.

## Expected output

```text
DB_R31_PRIVATE_ISOLATION_PREFLIGHT=PASS
DB_R31_FIREBASE_TEST_PASSWORD_LOGIN=PASS
DB_R31_REAL_FIREBASE_SESSION=PASS
DB_R31_AUTHENTICATED_QA_DATABASE_IDENTITY=PASS
DB_R31_REAL_FIREBASE_EXCEL_RECEIPT=PASS
DB_R31_REAL_FIREBASE_CSRF_CROSS_ORIGIN_REJECTED=PASS
DB_R31_REAL_FIREBASE_QA_PG_SOURCE_SYNC=PASS
DB_R31_ORIGINAL_SOL_INVALID_ROW_AND_INR_DETAILS=PASS
DB_R31_REAL_FIREBASE_INR_118_00_REPORT_PARITY=PASS
DB_R31_AUTHENTICATED_REPLAY_NO_DOUBLE_CREDIT=PASS
DB_R31_REAL_FIREBASE_CREDENTIALS_SAVED=NO
DB_R31_PRODUCTION_FINANCIAL_WRITES=NONE_BY_QA
DB_R31_RELEASE_STATUS=PRIVATE_REAL_FIREBASE_QA_PASS_NOT_PUBLIC
```

**Not production approval:** Production-grade multitenant RLS and roles, full verified branch-master SHA, authenticated *browser* exposure with protected private HTTPS origin, further negative wrong-owner account tests and v2.51 payment-to-invoice allocation remain separate approval gates. The private test retains isolated synthetic payment evidence for QA; it is never copied into the central production ledger.

**Test status at publication:** Offline contract CI can pass without any real Firebase account/network; owner must run the AWS terminal test to claim real Firebase acceptance.
