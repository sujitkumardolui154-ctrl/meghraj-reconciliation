# R31.11.4S — Real External HTTPS/mTLS End-to-End Security Acceptance

## Disposition and strict boundary

**STARTED: source-level acceptance matrix, no live remote E2E acceptance.**

As of 28 Nov 2026, the owner-reported R31.11.4R AWS read-only
approval-preflight was PASS, **with release explicitly BLOCKED**.
There is still no approved organization-controlled QA hostname,
DNS authority, restricted ingress scope, client CA and server/client
certificates, actual client certificate revocation mechanism, or
deployed isolated QA HTTP adapter.

**All 23 existing external deployment approvals remain PENDING and
all 22 real external security acceptance cases remain NOT_TESTED.**

R31.12 = ACTIVE_QA_DESIGN_RELEASE_GATED.
Financial Apply = LOCKED.
Production release = BLOCKED.

### What this milestone can do now

1. Freeze the **22 exact 4L E2E case identifiers** in
   \`r31_11_4s_external_acceptance_matrix.json\`, with acceptance
   category, expected effect, and required independent evidence.
2. Fail closed when any source file invents a QA hostname, external
   endpoint, reviewer, client trust, executed case, rollback exercise,
   or financial release approval.
3. Execute one **read-only AWS preflight** that reuses accepted
   R31.11.4R→4Q→4P→4O→4N→4M→4L→4K→4J→4H, the
   **local operator-reported** R31.11.4I real-auth evidence receipt,
   existing Caddy fingerprint, PG16 forced-RLS and role grants,
   source-row emptiness and two owner mappings.
4. Produce a correct readiness decision: the preflight can PASS while
   real external E2E is BLOCKED/NOT_TESTED.

**This milestone does not create an external test client or listener,
DNS entry, CA/certificates, Caddy route, Docker network/port, firewall
rule, Firebase session, PostgreSQL change or financial write.**

## Preconditions BEFORE ANY real network call

**Require independent verification and recorded operator approval, not
just JSON \`true\` values or GitHub CI PASS:**

- Real organization-controlled QA hostname, verified DNS zone owner,
  DNS change approval, expected SNI/Host and server SAN.
- Explicitly scoped external QA-only deployment ticket, independent
  reviewer and authorized test owner; no public finance/application
  route, no production Caddy changes.
- Restricted test-client IP/CIDR and firewall acceptance. No worldwide
  exposure; no publicly published PostgreSQL.
- Dedicated reviewed nonroot HTTP QA adapter, source-pinned image,
  exact five HTTP method/path allowlist and end-to-end
  Firebase-to-Postgres restricted SELECT-only identities.
- Genuine server TLS cert, protected test-only client CA, approved
  client cert inventory/expiry and actual enforceable revocation
  behavior. A trusted CA pool alone is not revocation enforcement.
- External test workstation **outside localhost**, verified source
  network/identity, logging and case evidence custody.
- Approved rollback owner, change ticket and independent monitoring
  verification; pre-test Caddy checksum and QA source-row counts.
- Real Firebase A and B authorized test sessions, with independent
  authorization to exercise genuine expired and revoked session cases.
  Never submit sessions, credentials, cookies or tokens in GitHub/chat.

No approved QA domain/certificates presently exist. **Do not run live
network probes until all the above have explicit, independently reviewed
approval**. In particular, do not reuse a Caddy synthetic loopback
certificate as a real external client/server credential.

## The exact 22 external cases and evidence needed

| Case group | Cases | Required proof |
|---|---:|---|
| Real identity-to-PG isolation | 2 | Two different approved real Firebase users reaching only their own PG restricted SELECT roles over actual external mTLS |
| mTLS / TLS negative boundary | 8 | Real remote client absent/wrong-CA/expired/revoked cert, wrong server hostname/CA, Host/SNI mismatch, obsolete TLS denied |
| Firebase session negatives | 4 | Anonymous/tampered/genuinely expired/genuinely revoked session rejected through external endpoint |
| Cross-tenant and spoofing | 3 | Tenant A/B prohibited access and forged UID/PG role rejected without leaking cross-tenant data |
| Financial and admin boundary | 1 | Upload/GST/invoice/write-capable endpoints rejected |
| Rate limits and audit | 1 | Real external rate limits and safe audited allow/deny events without secret logs |
| Post-conditions | 3 | Public Caddy SHA unchanged, isolated QA PG zero rows/two maps, approved rollback executed with independent acceptance |

These counts are the **existing original 4L 22 cases**, not extra tests.
A local synthetic TLS or source policy PASS cannot satisfy any real case.

**Evidence standard per case:** independent timestamped test run ID,
approved external client provenance, exact authorized QA hostname,
observed TLS/HTTP result or independent check, redacted log/correlation
identifier, protected case evidence checksum, independent reviewer
sign-off, and before/after Caddy and private PG security fingerprints.
Do not paste credentials, host certificates with private keys, raw
Firebase sessions, private IP/customer data or personal emails in logs.

The following must be treated as **NOT EXECUTED**, even if already
covered in synthetic tests: real client certificate revocation, real
Firebase expired/revoked session, true two-user external read-only
identity binding, real external rate-limits and approved rollback.

### TLS and authenticated application are separate assertions

- TLS handshake with a verified client certificate is a **gateway**
  check. It is not evidence of a valid Firebase session.
- A Firebase session check is not evidence that SQL queries enforce
  PG16 tenant RLS or that financial API writes are unavailable.
- A **simulated revoked ID** is not evidence that an actual X.509 client
  certificate with a revoked serial is denied by the deployed ingress.
- A failed browser request is not sufficient when the test expected a
  transport-level TLS denial; the tester must distinguish TLS failure,
  HTTP 4xx and application/authorization error.
- Actual rollback acceptance requires a separately authorized rollback
  exercise and before/after environment fingerprints, not just a
  reviewed nine-step design.
- Real tests require a new separately reviewed execution harness and
  access to approved external resources; source-only acceptance
  preparation does not authorize it.

## Full COMBINED AWS source-pinned read-only readiness test

Only use the exact commit that passed GitHub CI; never run an unreviewed
branch HEAD or alter Caddy/Docker to force a green status.

### Step 1 — fetch a clean worktree

\`\`\`bash
(
set -euo pipefail

BASE=/home/ubuntu/sbi-r31-11-4r/source
TARGET=/home/ubuntu/sbi-r31-11-4s/source
BRANCH=feature/sbi-r31-11-4s-external-mtls-acceptance-gate-20261128
SHA=<EXACT_40_CHAR_CI_SUCCESS_COMMIT>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4s
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4S_SOURCE=PASS_PINNED"
)
\`\`\`

### Step 2 — execute exact 22-case readiness & full private QA audit

\`\`\`bash
SHA=<EXACT_40_CHAR_CI_SUCCESS_COMMIT>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4s/source/staging/aws_login_v150/r31_11_4s_combined_external_acceptance.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

Expected successful status excerpts (read-only, not yet executed on AWS):

\`\`\`text
DB_R31_11_4S_EXTERNAL_MATRIX=PASS_22_EXACT_CASES_NOT_TESTED
DB_R31_11_4S_SOURCE_4L_CASE_ORDER=PASS_MATCHED
DB_R31_11_4S_EVIDENCE_RECEIPTS=ZERO_INDEPENDENT_EXTERNAL
DB_R31_11_4S_APPROVED_QA_FQDN=NOT_PROVIDED
DB_R31_11_4S_E2E_GATE=DENIED_MISSING_APPROVALS_AND_ENDPOINT
DB_R31_11_4R_DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS
DB_R31_11_4R_APPROVAL_PREFLIGHT=PASS_READONLY_RELEASE_BLOCKED
DB_R31_11_4S_4R_THROUGH_4H_SECURITY=PASS_READONLY
DB_R31_11_4S_AFTER_QA_CADDY_POSTGRES=PASS_UNCHANGED
DB_R31_11_4S_COMBINED_READINESS=PASS_NO_LIVE_EXTERNAL_TEST
DB_R31_11_4S_ACTUAL_REMOTE_TESTS=0_OF_22_EXECUTED
DB_R31_11_4S_EXTERNAL_HTTPS_MTLS=NOT_TESTED
DB_R31_11_4S_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED
DB_R31_11_4S_REAL_FIREBASE_SESSION_REVOCATION=NOT_TESTED
DB_R31_11_4S_QA_ENDPOINT=NOT_DEPLOYED_BY_THIS_PHASE
DB_R31_11_4S_FINANCIAL_APPLY=LOCKED
DB_R31_11_4S_PRODUCTION_RELEASE=BLOCKED
\`\`\`

If a \`STOP=DB_R31_11_4S_SOURCE_OR_SECURITY_REVIEW_REQUIRED\`
appears, stop. A PASS does not change the live security status and does
not create deployment authorization. Do not loosen source approvals,
Caddy, firewall, Docker, Postgres roles or financial locks.

## Real E2E acceptance decision

- **At present:** \`BLOCKED_NO_APPROVED_ENDPOINT_OR_TEST_CLIENT\`.
- **Read-only readiness PASS:** source matrix is intact, historical
  private QA safety checks still pass, but **0/22 remote tests executed**.
- **Future actual acceptance:** only after verified approvals and
  independently witnessed **22/22** real external cases with no gaps,
  appropriate rollback and after-test integrity, plus separate owner
  sign-off. Do not treat this future condition as satisfied.
- Production financial Apply remains locked until its own separately
  reviewed data integrity and financial execution acceptance.
