# R31.11.4M — External mTLS Approval Evidence Collection + Combined Preflight

**Scope:** approval evidence **metadata collection**, offline regression QA,
and combined **read-only AWS** checks from R31.11.4L. It is NOT real external
HTTPS/mTLS testing, new server/certificate/CA creation, production financial
deployment, Caddy modification, DNS/firewall editing, or AWS role change.

## Proven predecessor

Owner-supplied screenshots on 27 Nov 2026 showed R31.11.4L combined design
review PASS, including R31.11.4H source and QA isolation; R31.11.4I real
two-account Flask *in-process* Firebase-to-PG acceptance; R31.11.4J
synthetic loopback TLS; R31.11.4K non-deployed Caddy candidate and 23
unapproved external mTLS requirements. Original Caddy checksum:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

External mTLS, genuine revoked client certificates, genuine expired/revoked
Firebase sessions, and all 22 real external acceptance tests remain
**NOT TESTED**.

## 4M deliverables

1. \`r31_11_4m_evidence_register.json\`: 23 exact register entries, one
   for each existing 4K approval field (16 Boolean + 7 string). Every entry
   starts PENDING, with no invented evidence, reviewer or timestamp.
2. \`r31_11_4m_combined_evidence_preflight.py\`: combines accepted 4L
   read-only live checks, validates register shape and receipt metadata,
   refuses unreviewed approval claims in the original 4K packet, rechecks
   Caddy, PG16 private isolation and no 4F temporary resources.
3. Offline CI: validates all pending register entries; exact field names;
   forbidden release-status changes; invalid ticket/hash/metadata;
   spoofed reviewed evidence; Caddy drift and release locks.

The register is a **non-secret pointer index**, never an authoritative
source of approval. A ticket ID or SHA-256 string alone cannot establish
whether the underlying approval exists, was issued by an authorized
reviewer, corresponds to a legitimate DNS/certificate, or covers the
present deployment configuration. Never auto-approve based on register
state, including REVIEWED_METADATA_ONLY.

## States permitted in evidence register

- \`PENDING\` — no evidence supplied. All reference, digest, reviewer and
  timestamp fields must remain \`PENDING\`.
- \`SUBMITTED_UNVERIFIED\` — a safe external evidence ticket and lower-case
  SHA-256 digest have been supplied. Independent review not performed.
  Reviewer ticket and timestamp remain \`PENDING\`.
- \`REVIEWED_METADATA_ONLY\` — a second distinct non-secret reviewer ticket
  and RFC3339 UTC timestamp are recorded. This is still NOT an
  independently verified security approval.

Evidence ticket metadata format: capital A-Z followed by 4–79 uppercase
letters, digits, underscore or hyphen; no emails, passwords, private keys,
Firebase IDs or API/session tokens. SHA-256 is 64 lowercase hex digits.
Use source-specific identity/ownership and actual evidence checks
**outside GitHub** through the named authorized reviewer. Do not create
a fake ticket or approval merely to change status.

## Ownership/evidence collection groups

| Evidence area | 4K requirements |
|---|---|
| Change/DNS | change ticket, QA FQDN, domain owner approval, DNS control |
| Reachability | source CIDRs, restricted firewall, QA public scope |
| PKI | client CA owner, cert inventory, real revocation mechanism, server cert lifecycle |
| App isolation | restricted QA proxy, reviewed Caddy, test Origin, no financial routes |
| Rollback | approved ticket, owner and tested cutback |
| Observability | monitoring, alerts, external negative tests, authorized external test owner |
| Peer review | independent security reviewer and reviewed approvals |

All 23 requirements remain pending until actual external proof is reviewed.
**Do not edit the source-controlled 4K packet on the AWS QA checkout** to
mark booleans true; the pinned checkout must stay clean. Later, a
separately reviewed release process can validate actual evidence content
and authorized approvals without putting secrets in the repository.

## AWS combined read-only execution

After the GitHub source CI shows SUCCESS on the exact source SHA:

\`\`\`bash
(
set -euo pipefail

BASE=/home/ubuntu/sbi-r31-11-4l/source
TARGET=/home/ubuntu/sbi-r31-11-4m/source
BRANCH=feature/sbi-r31-11-4m-mtls-evidence-closure-20261127
SHA=<FULL_40_CHARACTER_CI_VERIFIED_COMMIT>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4m
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"

echo "DB_R31_11_4M_SOURCE=PASS_PINNED"
)
\`\`\`

\`\`\`bash
SHA=<FULL_40_CHARACTER_CI_VERIFIED_COMMIT>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4m/source/staging/aws_login_v150/r31_11_4m_combined_evidence_preflight.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

The full 4M command is **read-only**, makes no external TLS connection,
has no live approval execution path, and does not change file modes,
PostgreSQL, Caddy, firewall, DNS or Docker state.

Expected (not yet confirmed on AWS):

\`\`\`text
DB_R31_11_4L_DESIGN_REVIEW=PASS_PREPARATION_ONLY
DB_R31_11_4M_4L_COMBINED_SECURITY=PASS_READONLY
DB_R31_11_4M_REGISTER_SCHEMA=PASS_EXACT_23_FIELDS_NO_SECRETS
DB_R31_11_4M_EVIDENCE_PENDING=23
DB_R31_11_4M_EVIDENCE_SUBMITTED_UNVERIFIED=0
DB_R31_11_4M_EVIDENCE_METADATA_REVIEWED=0
DB_R31_11_4M_4K_APPROVALS=23_OF_23_PENDING
DB_R31_11_4M_22_EXTERNAL_CASES=ALL_NOT_TESTED
DB_R31_11_4M_AFTER_AUDIT_DB_CADDY=PASS_UNCHANGED
DB_R31_11_4M_COMBINED_EVIDENCE_PREFLIGHT=PASS_READONLY_NO_DEPLOY
DB_R31_11_4M_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4M_REVOCATION_TESTS=NOT_TESTED
DB_R31_11_4M_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4M_FINANCIAL_APPLY=LOCKED
DB_R31_11_4M_PRODUCTION_RELEASE=BLOCKED
\`\`\`

On \`STOP\`, inspect the first safe \`DB_R31_11_4M_BLOCK_REASON\` and
previous PASS lines. Never run provisioning, loosen permissions, import
CA/cert files, expose a port or repeat financial writes to get PASS.

## Later acceptance cannot be skipped

Even after independently collecting and verifying all 23 approvals, real
external mTLS acceptance remains a separate milestone requiring a remote
test client and signed deployment change, exact QA FQDN, reviewed DNS,
test-only trusted CA/certs with revocation enforcement, approved limited
ingress, a separately deployed *nonproduction* QA HTTP service, Caddy and
PG baseline attestation before/after, and 22 actual negative/positive
acceptance cases. A legitimate approved deployment still does not enable
production financial Apply. R31.12 remains ACTIVE_QA_DESIGN_RELEASE_GATED.

**No credentials or source financial data should be entered in GitHub, CI,
screenshots shared in ChatGPT, or the approval register.**
