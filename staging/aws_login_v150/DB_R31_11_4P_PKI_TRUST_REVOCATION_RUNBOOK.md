# R31.11.4P — PKI trust, server/client certificate lifecycle & revocation design

**Status: source planning and offline regression.** This stage makes NO real
certificate, CA trust-store, HTTPS listener, DNS, network, PostgreSQL, Caddy,
Firebase or financial change. It does NOT establish external mTLS acceptance.

## Evidence inherited from R31.11.4O

Operator-supplied AWS terminal output confirmed:
- \`DB_R31_11_4O_4N_THROUGH_4H_COMBINED_QA=PASS_READONLY\`.
- \`DB_R31_11_4O_AFTER_QA_CADDY_PG=PASS_UNCHANGED\`.
- \`DB_R31_11_4O_COMBINED_DOMAIN_PREFLIGHT=PASS_PREPARATION_ONLY\`.
- A real QA domain owner, DNS-zone authority and owner-approved hostname
  have **NOT** been independently verified.
- All **23** external deployment approvals remain PENDING; all **22** real
  external TLS+application acceptance tests are NOT TESTED.
- Finance Apply LOCKED; production BLOCKED; R31.12 ACTIVE_QA_DESIGN.

Public Caddy baseline SHA-256:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

## 4P trust/lifecycle approval evidence — 6 still pending

The source-only \`r31_11_4p_pki_trust_lifecycle_plan.json\` covers these
existing 4K/4M/4N fields, not additional independent approvals:

| Field | Evidence required |
|---|---|
| qa_client_ca_owner_approved | Owner-approved isolated *test* client certificate authority and custody scope |
| qa_client_cert_inventory_approved | Unique client identity, serial, EKU and non-secret inventory/expiry references |
| qa_client_revocation_mechanism_approved | Actual, explicitly implemented and independently tested revoked-client rejection mechanism |
| server_certificate_lifecycle_approved | Real QA hostname SAN, issuer trust, serverAuth EKU, validity, rotation and incident plan |
| server_certificate_provider | Authorized server certificate issuer/provider metadata and documented approval |
| client_ca_metadata_reference | Protected test CA evidence reference; **never CA private key or live PEM** |

The 4P plan has **8 unimplemented lifecycle review steps**, with
issuer/CA ownership, issuance and keys **not selected/issued**.
Never change approval flags simply because a local mock test passes.

## Security design constraints

- Server certificate identity must be validated for the separately
  approved QA FQDN, with correct SAN, validity and serverAuth profile.
- Dedicated client-auth CA must be test-only, independently approved and
  isolated from production trust. Clients need appropriate clientAuth EKU,
  unique inventory, controlled key access and lifecycle/renewal control.
- **Trust chain alone does not enforce client certificate revocation.**
  Do not assume that Caddy server-cert OCSP stapling revokes mTLS client
  certificates. Choose a concrete, supported revocation-control design
  (e.g., a security-reviewed verified client inventory/deny policy or
  appropriate revocation-aware authentication integration), fail-closed
  on stale/unknown status, and test revoked clients against the actual
  external endpoint before acceptance.
- R31.11.4P includes an **offline toy-metadata policy simulation** that
  refuses unlisted clients, wrong issuer, wrong EKU, expired, not-yet-valid
  or revoked identity IDs. It does not use X.509 signatures, trust-chain
  parsing, network checks or real Caddy integration. It cannot count as
  real mTLS or client revocation acceptance.
- Client certificate authentication is only the outer gateway. Separate
  verified Firebase authentication and owner-scoped PostgreSQL RLS are
  mandatory, as already tested privately in 4I.
- Do not include certificate keys/passwords/tokens/UIDs/emails in this
  source repository, CI, ChatGPT screenshots or metadata documents.

Caddy documentation:
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/caddyfile/options

Review exact syntax and feature support for the installed Caddy version
before separately proposing any deployed QA config. This plan deliberately
contains no deployable Caddy snippet or live trust pool.

## One full combined read-only AWS test

Run **only** after GitHub CI succeeds on the exact pinned SHA.

Step 1 — unique, clean detached worktree:

\`\`\`bash
(
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4o/source
TARGET=/home/ubuntu/sbi-r31-11-4p/source
BRANCH=feature/sbi-r31-11-4p-pki-trust-revocation-design-20261128
SHA=<EXACT_40_CHARACTER_CI_PASSED_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4p
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4P_SOURCE=PASS_PINNED"
)
\`\`\`

Step 2 — full 4P → 4O → 4N → 4M → 4L → 4K → 4J → 4H
real **read-only** QA inspection, PLUS source policy simulation:

\`\`\`bash
SHA=<EXACT_40_CHARACTER_CI_PASSED_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4p/source/staging/aws_login_v150/r31_11_4p_combined_pki_preflight.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

Expected success status excerpts (not yet verified on AWS):

\`\`\`text
DB_R31_11_4P_PRIOR_K_M_N_APPROVALS=6_OF_6_PKI_PENDING
DB_R31_11_4P_TRUST_PROFILE=PASS_REFERENCE_DESIGN_ONLY
DB_R31_11_4P_LIFECYCLE_STEPS=8_NOT_IMPLEMENTED
DB_R31_11_4P_REVOCATION_ENFORCEMENT=NOT_SELECTED_OR_TESTED
DB_R31_11_4P_POLICY_SIMULATION=PASS_FAIL_CLOSED_METADATA_ONLY
DB_R31_11_4P_POLICY_SIMULATION_REAL_TLS=NOT_TESTED
DB_R31_11_4O_COMBINED_DOMAIN_PREFLIGHT=PASS_PREPARATION_ONLY
DB_R31_11_4P_4O_THROUGH_4H_COMBINED_QA=PASS_READONLY
DB_R31_11_4P_POST_QA_CADDY_PG=PASS_UNCHANGED
DB_R31_11_4P_COMBINED_PKI_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY
DB_R31_11_4P_CLIENT_CA_AND_SERVER_CERTS=NOT_ISSUED_OR_VERIFIED
DB_R31_11_4P_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED
DB_R31_11_4P_REAL_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4P_22_EXTERNAL_ACCEPTANCE=NOT_TESTED
DB_R31_11_4P_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4P_FINANCIAL_APPLY=LOCKED
DB_R31_11_4P_PRODUCTION_RELEASE=BLOCKED
\`\`\`

On STOP, share only safe status lines. Never run new CA issuance,
Caddy reload, port changes, DNS editing, role provisioning or additional
Firebase password logins to force a green status.

## Real approvals still required after 4P

Organization-controlled QA hostname and verified domain owner;
dedicated test CA custody/issuance; externally trusted server certificate
for the QA hostname; clientAuth profiles/secure storage; enforceable
revocation and rotation; independent security reviewer; restricted
ingress and rollback; actual external tests for both real Firebase
tenants and the complete 22-case matrix.

An offline PASS only establishes preparation integrity, not real
certificate approval or deployment permission.
