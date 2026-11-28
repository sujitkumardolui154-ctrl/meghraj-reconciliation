# R31.11.4R — Controlled Isolated QA Endpoint Deployment APPROVAL PREFLIGHT

**Scope: non-executable deployment-approval precheck and private QA
read-only security audit.** There is intentionally no command in this
milestone to deploy a QA HTTPS endpoint or change financial operations.

## Evidence inherited

Owner-supplied AWS operator screenshot of R31.11.4Q reported:
- \`DB_R31_11_4Q_4P_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY\`
- \`DB_R31_11_4Q_EXISTING_CADDY_PROXY_ISOLATION=PASS_READONLY_METADATA\`
- \`DB_R31_11_4Q_AFTER_QA_DB_AND_CADDY=PASS_UNCHANGED\`
- \`DB_R31_11_4Q_COMBINED_INGRESS_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY\`

These passes cover source-level policy and private QA infrastructure
preflight, NOT a publicly reachable QA endpoint or remote mTLS security.

**Outstanding: 23/23 approved change fields PENDING; 22/22 remote external
mTLS/application tests NOT TESTED; no QA hostname, DNS-authority evidence,
test CA or client/server cert issuance/revocation, restricted ingress
approval, deployed nonroot HTTP adapter or independently approved
rollback.**

## R31.11.4R deliverables

1. \`r31_11_4r_deployment_gate.json\`: an exact 23-source-field
   approval inventory, 8 independent deployment prerequisites,
   9 designed-not-executed rollback steps, locked QA/prod resource
   boundaries, and all 22 real external acceptance tests NOT TESTED.
2. \`r31_11_4r_combined_approval_preflight.py\`: a single SHA-pinned,
   read-only AWS QA run that reuses the 4Q→4P→4O→4N→4M→4L→4K→4J→4H
   checks, 4I local auth operator receipt, forced Postgres16 tenant RLS,
   private networks, Caddy fingerprint and no ephemeral QA resources.
3. Offline GitHub regression tests fail closed when anything falsely
   says deployment allowed, live mTLS accepted, financial Apply unlocked,
   rollback executed or missing approvals completed.

The preflight can **PASS** with the intended output
\`DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS\`. This is not a
contradiction: the source/infrastructure integrity checks passed and
there is still no independent authorization to deploy.

## Eight independent prerequisites; none established

| Check | Status | Required actual evidence |
|---|---|---|
| Organization-controlled QA FQDN / DNS | Pending | Approved DNS zone and owner-authenticated control |
| Restricted QA ingress / firewall | Pending | Reviewed narrow access CIDR and network change scope |
| Test-only client CA / real revocation | Pending | CA custody, client identity management and actual revoked-cert denial |
| Server TLS certificate | Pending | Valid server SAN/chain for approved QA hostname, expiry and renewal |
| Dedicated nonroot QA HTTP adapter | Not deployed | Peer-reviewed service, isolated from financial routes |
| Exact method/path + Firebase/RLS | Design only | Actual service auth, CSRF/Origin, identity binding and negative tests |
| Independent change approval / rollback | Pending | Approved ticket, authorized reviewer and tested cutback |
| Monitoring and external test ownership | Pending | Logs/alerts, rate limits and named authorized external tester |

Metadata tickets, hashes, Boolean \`true\` values in source and CI
\`PASS\` cannot certify the actual approvals. Store approvals in the
organization's authorized external system; GitHub must not contain secrets.

## AWS commands — exact source pin, immutable checkout

Replace the SHA with the exact current GitHub CI-passed commit:

\`\`\`bash
(
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4q/source
TARGET=/home/ubuntu/sbi-r31-11-4r/source
BRANCH=feature/sbi-r31-11-4r-external-qa-deployment-approval-20261128
SHA=<EXACT_GITHUB_CI_PASSED_40_CHARACTER_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4r
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
echo "DB_R31_11_4R_SOURCE=PASS_PINNED"
)
\`\`\`

\`\`\`bash
SHA=<EXACT_GITHUB_CI_PASSED_40_CHARACTER_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4r/source/staging/aws_login_v150/r31_11_4r_combined_approval_preflight.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

Expected safe successful preflight status excerpts (AWS NOT YET TESTED):

\`\`\`text
DB_R31_11_4R_GATE_MANIFEST=PASS_NONDEPLOYABLE_SCHEMA
DB_R31_11_4R_INDEPENDENT_PREREQUISITES=8_OF_8_UNVERIFIED
DB_R31_11_4R_LINKED_APPROVALS=23_OF_23_PENDING
DB_R31_11_4R_ROLLBACK_STEPS=9_DESIGNED_NOT_EXECUTED
DB_R31_11_4R_REMOTE_ACCEPTANCE=0_OF_22_TESTED
DB_R31_11_4R_REAL_OWNER_SECURITY_SIGNOFF=NOT_VERIFIED
DB_R31_11_4R_QA_HOSTNAME_DNS_AND_CERTS=NOT_APPROVED
DB_R31_11_4R_ROLLBACK_EXERCISE=NOT_EXECUTED
DB_R31_11_4R_DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS
DB_R31_11_4Q_COMBINED_INGRESS_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY
DB_R31_11_4R_4Q_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY
DB_R31_11_4R_AFTER_COMBINED_CADDY_AND_PG=PASS_UNCHANGED
DB_R31_11_4R_APPROVAL_PREFLIGHT=PASS_READONLY_RELEASE_BLOCKED
DB_R31_11_4R_EXTERNAL_HTTPS_MTLS=NOT_TESTED
DB_R31_11_4R_QA_ENDPOINT=NOT_DEPLOYED_BY_THIS_PHASE
DB_R31_11_4R_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4R_FINANCIAL_APPLY=LOCKED
DB_R31_11_4R_PRODUCTION_RELEASE=BLOCKED
\`\`\`

On \`STOP\`, halt and review only the fixed reason code. Never amend
approval JSON, change Caddy, Docker networks, DNS/CA, firewall, PG roles or
production finance privileges to force a PASS.

## After 4R approval preflight

The next work is real evidence closure, **not automatic deployment**:
securely establish and independently review one organization-controlled
QA FQDN, DNS ownership, test-only client CA and real revocation,
server/client cert lifetime, restricted public CIDRs, nonroot auth adapter,
audit/rate limits and approved rollback. No real external QA endpoint may
be created without a separately recorded and scoped owner authorization.
Once such deployment is independently approved and safely executed,
the **22 genuine remote HTTPS/mTLS and application acceptance cases**
still need execution before final security acceptance.

Production financial Apply remains LOCKED and requires independent,
explicit approval even if future external mTLS acceptance passes.
R31.12 stays ACTIVE_QA_DESIGN_RELEASE_GATED.
