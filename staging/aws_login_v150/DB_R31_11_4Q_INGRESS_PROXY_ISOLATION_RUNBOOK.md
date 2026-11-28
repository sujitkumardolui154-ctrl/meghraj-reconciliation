# DB-R31.11.4Q — Restricted QA Ingress and Reverse Proxy Isolation

**Disposition: READ-ONLY QA DESIGN / NO DEPLOYMENT.** This stage builds on
owner-reported R31.11.4P AWS design-readiness PASS and source-pinned private
QA R31.11.4H through 4O. The private service was tested via a Flask
**in-process** client, not a remotely deployed QA HTTP endpoint.

No real organization-owned QA hostname has been supplied; all 23 external
deployment approvals still need legitimate evidence. The 22 remote external
mTLS/auth acceptance cases are NOT TESTED. Production financial Apply
remains LOCKED; R31.12 is ACTIVE_QA_DESIGN_RELEASE_GATED.

## Source deliverables

- \`r31_11_4q_ingress_isolation_policy.json\`: nondeployable reference
  policy with **14 required ingress/security controls**. All marked
  DESIGN_REQUIRED_NOT_ACCEPTED; none claims actual firewall, Caddy or HTTP
  listener deployment.
- **Exact five method/path proposals** inherited from R31.11.4L:
  \`GET /healthz\`, \`GET /auth/csrf\`, \`POST /auth/session\`,
  \`GET /auth/me\`, \`GET /api/r31-private-qa/tenant-rls-source-r3114\`.
  They are proposals, **not deployed or externally tested routes**.
- Every other request denied in an offline **synthetic** policy model,
  including financial/GST/invoice/uploads, wildcard/prefix/trailing slash,
  wrong HTTP method, missing certificate flag, mismatched SNI/Host flag,
  unapproved source flag, forged identity-header flag, invalid Firebase
  session flag or invalid Origin/CSRF flag. The flags are **not real
  certificate, IP, identity or CSRF verification**.
- **13 relevant 4K ingress/proxy/monitoring/rollback approval fields**
  remain PENDING, within the existing 23; no additional invented
  approvals. Existing 4M register remains 23 PENDING.
- **Nine-step rollback is a design**; it is not executed or approved.
- Restrict audit event design to timestamp, event code, correlation ID,
  HTTP method, route template and decision. Do not log passwords,
  authorization headers, cookies, Firebase UIDs, exact client identity,
  client cert PEM/private keys, raw IPs, or secret data.
- The combined runner rechecks full R31.11.4P→4O→4N→4M→4L→4K→4J→4H
  security, original 4I real Firebase-auth **local operator receipt**,
  forced PG16 RLS, zero financial evidence rows, two owner maps,
  Caddy SHA-256, private QA network and 4F resource absence.
- Extra read-only Caddy metadata assertions: existing Caddy is not
  connected to the dedicated QA Postgres network and has no Docker
  socket mount. These are checks on the existing Caddy service, not
  proof of a separately deployed QA proxy.

Original expected Caddy SHA-256:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

## Proposed later architecture; NO real deployment here

\`\`\`text
[Externally approved test client]
       |
       | restricted ingress CIDR + real trusted mTLS client cert,
       | correct QA SNI/Host, client revocation control [ALL PENDING]
       v
[Dedicated test-only QA HTTPS reverse proxy - NOT DEPLOYED]
       |
       | exact 5 method/path allowlist,
       | remove forged X-Firebase-UID / X-DB-Role / cert identity headers,
       | no trust in arbitrary X-Forwarded-For,
       | approved Origin/CSRF for session exchange [DESIGN ONLY]
       v
[Dedicated, separately reviewed QA HTTP auth adapter - NOT DEPLOYED]
       |
       | genuine signed Firebase session and owner mapping,
       | no write-capable financial API, no privileged PG role
       v
[Private isolated QA PostgreSQL 16 - EXISTING, RLS SELECT ONLY]
       |
       | 0 payment/source evidence rows, 2 owner mappings
       v
[Read-only QA response]

Existing public Caddy and financial endpoints: UNCHANGED, NOT SHARED.
QA proxy directly connected to PostgreSQL: FORBIDDEN.
QA proxy connected to production financial Docker network: FORBIDDEN.
Docker socket mount in a QA proxy: FORBIDDEN.
Public access to PostgreSQL: FORBIDDEN.
\`\`\`

The real auth adapter must later be independently designed, tested and
approved; a Flask \`test_client\` is NOT a deployable HTTPS server.

**Important TLS detail:** A reviewed QA mTLS proxy must use
\`require_and_verify\` with approved trust pool. The Caddy
\`strict_sni_host\` safeguard prevents Host/SNI domain-fronting errors;
verify it on the exact installed version and do not disable it.
A valid CA trust chain is NOT proof of client certificate revocation:
the actual revoke/deny mechanism must be separately implemented and
tested. In addition, no mTLS gate replaces signed Firebase sessions
or PostgreSQL tenant RLS.

Official documentation to review for eventual approved change:
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/caddyfile/options
- https://caddyserver.com/docs/caddyfile/matchers
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy

## AWS source pin and complete read-only combined QA

Only run the branch revision that matches a SUCCESS GitHub Actions run.

### Step 1 — immutable source checkout

\`\`\`bash
(
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4p/source
TARGET=/home/ubuntu/sbi-r31-11-4q/source
BRANCH=feature/sbi-r31-11-4q-ingress-proxy-isolation-20261128
SHA=<EXACT_FINAL_40_CHAR_GREEN_CI_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4q
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4Q_SOURCE=PASS_PINNED"
)
\`\`\`

### Step 2 — complete ingress isolation read-only audit

\`\`\`bash
SHA=<EXACT_FINAL_40_CHAR_GREEN_CI_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4q/source/staging/aws_login_v150/r31_11_4q_combined_ingress_preflight.py
"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

**No AWS mutation or new TLS listener occurs in this script.** Do not
paste passwords, session cookies, Firebase tokens or certificate keys in
AWS command-line arguments or output.

Expected successful excerpt, only after AWS execution verifies it:

\`\`\`text
DB_R31_11_4Q_INGRESS_POLICY=PASS_NONDEPLOYABLE_14_GATES
DB_R31_11_4Q_ROUTE_POLICY=PASS_EXACT_FIVE_METHOD_PATH_PAIRS
DB_R31_11_4Q_AUDIT_LOG_POLICY=PASS_NO_SECRET_FIELDS_DESIGN_ONLY
DB_R31_11_4Q_ROLLBACK=9_STEPS_REVIEW_ONLY_NOT_EXECUTED
DB_R31_11_4Q_INGRESS_RELATED_APPROVALS=13_OF_13_PENDING_WITHIN_23
DB_R31_11_4Q_ALL_EXTERNAL_APPROVALS=23_OF_23_PENDING
DB_R31_11_4Q_SIMULATED_ROUTES=PASS_FIVE_ALLOW_FIFTEEN_DENY
DB_R31_11_4Q_REAL_HTTP_PROXY=NOT_DEPLOYED
DB_R31_11_4P_COMBINED_PKI_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY
DB_R31_11_4Q_4P_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY
DB_R31_11_4Q_EXISTING_CADDY_PROXY_ISOLATION=PASS_READONLY_METADATA
DB_R31_11_4Q_NEW_QA_PROXY=NOT_DEPLOYED_BY_4Q
DB_R31_11_4Q_AFTER_QA_DB_AND_CADDY=PASS_UNCHANGED
DB_R31_11_4Q_COMBINED_INGRESS_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY
DB_R31_11_4Q_INGRESS_CIDR_AND_FIREWALL=NOT_APPROVED_OR_DEPLOYED
DB_R31_11_4Q_REAL_QA_MTLS_ENDPOINT=NOT_DEPLOYED
DB_R31_11_4Q_EXTERNAL_ACCEPTANCE=22_NOT_TESTED
DB_R31_11_4Q_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4Q_FINANCIAL_APPLY=LOCKED
DB_R31_11_4Q_PRODUCTION_RELEASE=BLOCKED
\`\`\`

If a \`STOP=DB_R31_11_4Q_COMBINED_SECURITY_REVIEW_REQUIRED\` appears,
stop and review only the safe \`DB_R31_11_4Q_BLOCK_REASON\`.
Do **not** add Docker network membership, modify Caddy, add route
exceptions, open firewall ports, create certificates, reset SQL roles,
or relax financial restrictions to force a PASS.

## Distinct later gates

The production Caddy URL remains unchanged. A genuine QA hostname,
independent domain/DNS approval, CA trust/revocation and restricted
source CIDRs, an isolated nonroot HTTP adapter, externally tested origin
and session controls, rate limits, monitoring and a reversible approved
change are required BEFORE any real external HTTPS/mTLS acceptance.

The 22 remote cases are still NOT TESTED and all 23 external approval
requirements remain PENDING. R31.12 may continue only as
ACTIVE_QA_DESIGN_RELEASE_GATED. Financial Apply LOCKED; production BLOCKED.
