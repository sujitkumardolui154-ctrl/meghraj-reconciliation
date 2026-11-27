# DB-R31.11.4K — External HTTPS/mTLS Deployment Preparation and Approval

**Scope:** Source-only approval packet and guarded **read-only** AWS inventory,
not deployment. No Caddy public route edits, DNS/SSL purchases, private key
generation or import, port/firewall modifications, Firebase users, PostgreSQL
changes, or financial reconciliation writes are authorized by this milestone.

## Previously accepted QA and outstanding gates

- 4I: owner-supplied AWS screenshot confirmed two genuine Firebase test-account
  sign-ins and distinct Firebase-to-Postgres restricted LOGIN role binding,
  read-only RLS, header and method denial, and a local source-pinned
  operator QA receipt.
- 4J: owner-supplied screenshot confirmed six **synthetic loopback-only**
  TLS accept/deny tests, ephemeral certificate cleanup and unchanged
  Caddy/Postgres.
- **External HTTPS/mTLS is NOT TESTED**. Real expired/revoked Firebase session
  and real client certificate revocation remain NOT TESTED.
- Original Caddy baseline SHA-256:
  \`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.
- R31.12 = ACTIVE_QA_DESIGN_RELEASE_GATED. Financial Apply LOCKED.
  Production release BLOCKED.

## Architecture recommended for separately approved live QA

Do not modify or import new snippets into the production Caddyfile as part
of R31.11.4K. Prefer a dedicated, isolated QA reverse proxy and QA-only
hostname, behind narrowly scoped ingress rules and a separate QA service;
never expose the private PostgreSQL network, reuse public finance routes or
mount the Docker socket. Real implementation requires design review, owner
authorization, two-person security review and documented rollback.

Review-only file:
\`Caddyfile.r31_11_4k_NOT_FOR_DEPLOYMENT.template\`

It deliberately contains:
- An unresolvable \`.invalid\` hostname;
- An unapproved CA file path;
- TLS \`client_auth { mode require_and_verify; trust_pool file ... }\`;
- **HTTP 503 only**, with no reverse proxy or financial endpoints.

**Never copy this template into running Caddy or attempt DNS resolution of
its invalid hostname.** Validate exact Caddy version/config syntax and
certificate lifecycle against official Caddy docs before an actual change.

## Approval packet fields — NO SECRETS

\`r31_11_4k_external_mtls_approval_packet.json\` contains only
non-secret review metadata and Boolean approvals. All of these begin
**PENDING** or **false**:

1. Change ticket and approved QA FQDN, DNS control and domain owner approval.
2. Restricted CIDR network access scope and explicit external access approval.
3. Test-only client CA owner and inventory; revocation enforcement,
   rotation, expiration and incident-response plan.
4. Server certificate provider and safe non-secret validity/renewal plan.
5. Dedicated QA proxy / backend isolation; no payment upload, invoice,
   GST, production reconciliation or financial Apply endpoints.
6. Approved exact QA Origin, headers and test-account mapping.
7. Reviewed revert/rollback ticket, cutback verification and response owner.
8. Approved monitoring/alerting, negative-case external test runbook, and
   independent security reviewer.

Do **not** put PEM, private keys, Firebase UIDs, emails, API secrets,
session cookies, passwords or credential values in this JSON or GitHub.
The validator refuses common secret-like text. Never mark a Boolean
\`true\` merely to satisfy the script; each value must have real approval
evidence recorded outside this non-secret manifest. The script does not
verify DNS/CA issuance remotely and never independently approves any value.

When all fields are legitimately reviewed, the output remains
\`DECLARED_COMPLETE_REVIEW_ONLY\` and
\`NO_DEPLOYMENT_AUTHORIZATION\`. That does **not** allow production change.

## AWS QA commands — pinned source, no mutation

Use the exact SHA of the latest CI-passed commit:

\`\`\`bash
(
set -euo pipefail

BASE=/home/ubuntu/sbi-r31-11-4j/source
TARGET=/home/ubuntu/sbi-r31-11-4k/source
BRANCH=feature/sbi-r31-11-4k-external-mtls-deployment-readiness-20261127
SHA=<40_CHARACTER_GITHUB_VERIFIED_COMMIT_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4k
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4K_SOURCE=PASS_PINNED"
)
\`\`\`

\`\`\`bash
SHA=<40_CHARACTER_GITHUB_VERIFIED_COMMIT_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4k/source/staging/aws_login_v150/r31_11_4k_external_mtls_readiness.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA" --mode audit
\`\`\`

This is read-only. It combines 4J's private IAM/Firebase user metadata,
RLS/PG, authentic-4I local receipt, Caddy SHA, isolation and no-temp-residue
checks. It verifies the safe 503 template and the all-pending packet,
then rechecks Caddy and QA data integrity.

Expected successful preflight result excerpts:

\`\`\`text
DB_R31_11_4J_DB_NETWORK_CADDY_AND_TEMP_CLEANUP=PASS_READONLY
DB_R31_11_4K_INACTIVE_CADDY_CANDIDATE=PASS_503_NO_UPSTREAM
DB_R31_11_4K_RUNNING_CADDY=PASS_EXISTING_BASELINE_READONLY
DB_R31_11_4K_EXTERNAL_INGRESS=NOT_DEPLOYED_BY_THIS_PHASE
DB_R31_11_4K_APPROVAL_PACKET_SCHEMA=PASS_STRICT_NO_SECRETS
DB_R31_11_4K_APPROVAL_PACKET=INCOMPLETE
DB_R31_11_4K_PENDING_FIELD_COUNT=23
DB_R31_11_4K_POST_AUDIT_DB_CADDY=PASS_UNCHANGED
DB_R31_11_4K_RELEASE_REVIEW=NO_DEPLOYMENT_AUTHORIZATION
DB_R31_11_4K_READINESS_AUDIT=PASS_PREPARATION_ONLY
DB_R31_11_4K_CERT_AND_DNS_APPROVAL=NOT_ESTABLISHED_BY_SCRIPT
DB_R31_11_4K_EXTERNAL_HTTPS_MTLS=NOT_TESTED
DB_R31_11_4K_FINANCIAL_APPLY=LOCKED
DB_R31_11_4K_PRODUCTION_RELEASE=BLOCKED
\`\`\`

The pending count is the exact number of required entries in the packet
that are still unapproved; do not edit this output manually.

The \`--mode packet-review --packet <local_nonsecret_review_packet.json>\`
path is only a **read-only** operator-declaration validation, never a deploy.
Do not copy real secrets into the packet or paste them into ChatGPT.

If the AWS audit prints \`STOP\`, do not repeat provisioning, change Caddy,
update DNS or open firewall ports. Stop and review the source and the safely
reported status; use read-only diagnostics only.

## Separate, explicit later change needed for real external acceptance

Actual external HTTPS/mTLS requires:
- A named QA-only hostname with owner-approved DNS and safe exposure policy.
- Approved server certificate, trusted test-client CA, real client identities
  and verified revocation/rotation behavior.
- A reviewed isolated QA reverse proxy, listener, Origin/CORS, TLS SNI/Host
  enforcement, and rollback plan, kept separate from public app routes.
- A remote test workstation not on localhost, with cert-positive, missing
  client certificate, wrong CA, expired/revoked client cert, incorrect SNI,
  anonymous/forged Firebase session, two-tenant RLS and restricted method
  negative cases.
- Before and after, verify original public Caddy fingerprint, RLS roles,
  zero financial evidence rows, two owner maps and NO financial Apply.
- Explicit owner approval for any real infrastructure mutation. An approved
  packet is only a necessary prerequisite, not sufficient authorization.
  Production release still requires separate acceptance and sign-off.

Source references:
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/json/apps/http/servers/tls_connection_policies/

**R31.11.4K ends at read-only readiness / approval preparation.**
