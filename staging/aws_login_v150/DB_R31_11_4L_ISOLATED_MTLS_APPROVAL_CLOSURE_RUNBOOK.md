# R31.11.4L — Approval Closure & Isolated QA Deployment DESIGN

**Status:** Design source + offline regression QA. No external deployment,
certificates, DNS, Caddy mutation, ingress/firewall change, new QA HTTP
runtime or financial API is approved or performed.

## What previous operator evidence supports

R31.11.4I AWS screenshot: two real Firebase test users authenticated through
the *Flask in-process* one-shot test and accessed their own restricted
PostgreSQL logins; unauthorized role/owner spoofing was rejected. A local
owner-only source-pinned QA receipt exists.

R31.11.4J AWS screenshot: six synthetic TLS handshake cases passed on
127.0.0.1 and the post-test database and original Caddy fingerprint remained
unchanged.

R31.11.4K AWS screenshot: full read-only preflight PASS, no new public
QA Caddy route and the strict approval packet has **23 unresolved fields**
(16 Boolean declarations + 7 text references). Original Caddy SHA-256:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

None of these stages tested an actual remote HTTPS/mTLS endpoint or a
revoked/expired real Firebase session or revoked production client cert.

## Reference architecture; not deployable

\`\`\`text
[Approved remote test client + approved QA client certificate]
                    |
                    | HTTPS + verified mTLS [NOT APPROVED]
                    v
[Separate QA-only ingress, hostname and independent proxy]
                    |
                    | Exact allowlisted auth and read-only QA requests
                    v
[Dedicated QA HTTP auth adapter — NOT DEPLOYED]
                    |
                    | UID -> restricted, non-privileged PostgreSQL LOGIN role
                    v
[Private PG16: sbi_r31_11_4_auth_qa_20261126]
                    |
                    | Forced RLS SELECT only; 0 evidence rows, 2 owner maps
                    v
           [Read-only responses]

Public Caddy / production app : UNCHANGED — no shared QA route.
PostgreSQL public access     : NONE.
Production financial engines : DISCONNECTED; Apply LOCKED.
\`\`\`

The current accepted 4F/4I in-process Flask \`test_client\` is NOT an
HTTP server and must not be reused as a deployable QA endpoint without
a separately designed nonroot HTTP service, private IAM scope, session
lifecycle checks, rate limiting, CSRF/Origin controls, upstream health
and private networking. A separate service/identity/proxy deployment
needs explicit owner review and approval.

The 4L manifest contains exactly five proposed method/path pairs:
- GET /healthz
- GET /auth/csrf
- POST /auth/session
- GET /auth/me
- GET /api/r31-private-qa/tenant-rls-source-r3114

These are **proposed**, not externally implemented or exposed. Restrict
all other methods and routes to denial. **No wildcard \`/auth/*\` or
\`/api/*\` passthrough**. Do not route uploads, GST, invoice generation,
credit notes, administration, bulk reports, reconciliation, financial
Apply or any write-capable endpoints. Source-level and upstream-level
permissions must independently enforce read-only operation.

## Caddy and certificate considerations

For a separately approved, isolated QA proxy:
- Caddy client_auth \`require_and_verify\` with a reviewed test CA
  \`trust_pool\`, correct certificate EKU, expiry, rotation and trusted
  issuer binding. Do not store cert private keys in source control.
- Check installed Caddy version; assess \`strict_sni_host\` / TLS SNI
  versus HTTP Host matching to prevent domain-fronting bypass. Use the
  documented syntax supported by the exact installed build.
- Ensure the test CA and server-certificate provider are genuinely
  approved before validating certificate chains. No approval yet.
- Client cert revocation must have a concrete enforcement mechanism and
  tested negative case; CA membership and ordinary expiry alone do NOT
  constitute revocation.
- Restricted source CIDRs, firewall audit, rate limits, safe request
  logging without authorization header/cookies/token disclosure, detection
  and alerts. Do not assume a publicly reachable port is safe.
- Strong rollback and incident escalation requirements; do not touch
  existing public Caddy or expose the PG16 bridge.

Official Caddy references:
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/caddyfile/options
- https://caddyserver.com/docs/caddyfile/matchers

## Nonsecret approval closure table (still pending)

The existing 4K packet remains the single source for 23 requirements.
No changes were made to its pending values.

| Group | Required evidence | State |
|---|---|---|
| Change + DNS | change ticket, approved QA FQDN, owner + DNS proof | PENDING |
| Ingress | scoped CIDRs, limited external exposure, firewall reviewer | PENDING |
| Trust | client CA review, client inventory, revocation, server certificate lifecycle | PENDING |
| App | independent QA proxy/service, five-route allowlist, Firebase test Origin | PENDING |
| Finance | no financial API/public paths and no DB write access | PENDING |
| Rollback | rollback ticket, owner, rehearsal, protected public Caddy checksum | PENDING |
| Operations | external test owner, negative testing, monitoring, second reviewer | PENDING |

An approval packet edited to say \`true\` or \`REVIEW_ONLY\` is NOT
self-verifying. Legitimate approvals must be evidenced externally and
separately validated. Never add PEM certificates, private keys, passwords,
Firebase UIDs, personal emails, cookies or API secrets to GitHub or chat.

## External acceptance plan, 22 pending cases

The design manifest enumerates all 22 cases as
\`NOT_TESTED_EXTERNAL\`. These cover a genuinely remote client, real
TLS client certificate and server verification, both real Firebase test
identities to their own restricted PG role, no/wrong/expired/revoked
client cert, wrong host/SNI, TLS downgrade, invalid/revoked/expired
Firebase session, forged tenant/header, cross-tenant denial, financial
write denial, monitoring, Caddy/PG integrity, and rollback execution.

A synthetic localhost PASS does not change any external case status.
No mTLS revocation is claimed here.

## Rollback — review sequence, NOT commands

1. Confirm change ticket, owner and current SHA/QA DB baseline.
2. Verify the approved cutback target and the actual isolated QA resource
   identities. No name-only resource deletion.
3. If a future live QA test was explicitly approved, stop only the
   labeled test ingress; preserve all production Caddy and PG resources.
4. Revoke only approved QA test certificate access as separately authorized.
5. Restore DNS and scoped firewall through approved change procedures.
6. Confirm public Caddy fingerprint matches its prechange baseline.
7. Confirm PG16 read-only RLS, two owner maps, zero evidence rows and
   locked financial Apply.
8. Confirm temporary ADC/candidate/network remnants are absent without
   guessing resource ownership.
9. Record reviewer signoff, monitoring closure and any incident finding.

4L validates this review sequence; it does not execute it.

## Run the complete combined QA (read-only AWS)

Only run the branch SHA that matches a successful GitHub CI run.
The full source pin and runner are:

\`\`\`bash
(
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4k/source
TARGET=/home/ubuntu/sbi-r31-11-4l/source
BRANCH=feature/sbi-r31-11-4l-isolated-mtls-deployment-design-20261127
SHA=<FINAL_VERIFIED_40_CHAR_SHA>
test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4l
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4L_SOURCE=PASS_PINNED"
)
\`\`\`

\`\`\`bash
SHA=<FINAL_VERIFIED_40_CHAR_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4l/source/staging/aws_login_v150/r31_11_4l_combined_design_gate.py
"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

This invokes actual approved QA metadata, no Firebase password login, no
Docker build/start, network create, Caddy file write, upload, SQL mutation
or receipt overwriting.

Expected successful status excerpts:

\`\`\`text
DB_R31_11_4J_DB_NETWORK_CADDY_AND_TEMP_CLEANUP=PASS_READONLY
DB_R31_11_4K_RUNNING_CADDY=PASS_EXISTING_BASELINE_READONLY
DB_R31_11_4L_ISOLATION_GRAPH=PASS_DESIGN_ONLY_NO_DEPLOYMENT
DB_R31_11_4L_METHOD_PATH_ALLOWLIST=PASS_EXACT_FIVE_ROUTES
DB_R31_11_4L_FINANCIAL_ENDPOINTS=BLOCKED_IN_REFERENCE_DESIGN
DB_R31_11_4L_EXTERNAL_ACCEPTANCE_CASES=22_NOT_TESTED
DB_R31_11_4L_ROLLBACK_REVIEW_SEQUENCE=PASS_NINE_STEPS_NOT_EXECUTED
DB_R31_11_4K_APPROVAL_PACKET=INCOMPLETE
DB_R31_11_4L_DEPLOYMENT_APPROVALS=23_OF_23_STILL_PENDING
DB_R31_11_4L_AFTER_COMBINED_CADDY_AND_PG=PASS_READONLY_UNCHANGED
DB_R31_11_4L_DESIGN_REVIEW=PASS_PREPARATION_ONLY
DB_R31_11_4L_EXTERNAL_HTTPS_MTLS=NOT_TESTED
DB_R31_11_4L_FINANCIAL_APPLY=LOCKED
DB_R31_11_4L_PRODUCTION_RELEASE=BLOCKED
\`\`\`

A \`STOP\` means do not repeat database provisioning, change Caddy or
firewall, create certificates or force approval flags. Read-only
diagnostics and independent review only.

## Status criteria

R31.11.4L source CI and AWS read-only audit may become PASS while the
23 separate external security requirements still remain pending.
R31.12 stays ACTIVE_QA_DESIGN_RELEASE_GATED. Production financial Apply
stays LOCKED and release BLOCKED. A separate deployment proposal and
scope-specific authorization are mandatory before even launching a real
external QA HTTPS/mTLS endpoint.
