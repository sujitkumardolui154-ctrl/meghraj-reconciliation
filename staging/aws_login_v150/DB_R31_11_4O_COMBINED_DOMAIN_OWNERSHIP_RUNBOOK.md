# R31.11.4O — Full combined QA / Domain and DNS ownership evidence

**4O is a read-only domain ownership EVIDENCE READINESS audit, not an
external TLS deployment or an independently verified DNS ownership test.**

## Previously supported facts

Owner-supplied AWS screenshots dated 27 Nov 2026 established:
- 4I: two real approved Firebase test accounts, private in-process
  Firebase-to-PG role mapping, denial of forged roles, QA receipt.
- 4J: real TLS loopback *synthetic* mTLS certificate positive/negative
  handshake tests with cleanup, NOT a public endpoint.
- 4K/4L/4M/4N: combined private PG16 forced RLS / Caddy read-only preflight
  PASS, two owner mappings, zero QA evidence rows, no temporary 4F network,
  no changes to Caddy, all 23 external mTLS deployment approvals pending.
- 4N: no proposed QA FQDN or zone, 10 DNS/PKI requirements pending.
- 4L: all 22 external HTTPS/mTLS acceptance cases NOT TESTED.

Current approved production Caddy SHA-256:
\`61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b\`.

## 4O specifically adds a six-gate domain owner evidence dossier

File: \`r31_11_4o_domain_ownership_dossier.json\`

| Gate | Proof to collect later | Initial status |
|---|---|---|
| change_authorization | Named approved QA hostname/DNS change ticket | PENDING |
| registrant_ownership | Authorization from real domain registrant/organization | PENDING |
| dns_zone_administration | Evidence from authorized DNS zone administrator | PENDING |
| authoritative_delegation | Nameserver delegation evidence from independent source | PENDING |
| dns_record_change_control | Authorized controlled DNS record change evidence | PENDING |
| independent_owner_review | Separate authorized security/reviewer assessment | PENDING |

The 4N 10-field and 4K/4M 23-field records remain intact. A 4O
dossier reference is not an extra approval and it cannot override them.

Evidence metadata states:
- \`PENDING\`: no genuine owner/zone evidence supplied.
- \`REFERENCED_UNVERIFIED\`: ticket + SHA-256 metadata only, no proof.
- \`METADATA_REVIEWED_NOT_APPROVED\`: distinct reviewer ticket + date
  supplied; still **NOT** authoritative proof or sign-off.

A proposed hostname must match 4N's proposed QA hostname and parent
zone exactly. An organization-controlled domain **has not been identified**.
Do not adopt \`sslip.io\`, \`.invalid\`, \`.local\`, localhost, a
third-party-owned public domain, an AWS console hostname or an unapproved
production subdomain as a QA FQDN.

Do NOT put passwords, domain registrar access tokens, bearer/cookie values,
certificate private keys, Firebase UIDs or personal identity information
into GitHub, the dossier or chat. Authorized domain owner can provide
non-secret approval ticket references separately.

## Full combined AWS read-only QA

The script runs the complete 4N→4M→4L→4K→4J→4H checks in one command,
including pinned GitHub source, two Firebase Admin user metadata reads,
existing 4I local authentication QA receipt, private PG16 RLS, zero QA
payments and two owner maps, Caddy baseline and temporary resource absence.
It validates the 4O six-gate dossier and rechecks Caddy/PG after.

It does NOT query DNS; a DNS response would not establish registrant
authorization. It does not write to AWS, PostgreSQL, certificates, DNS,
Caddy, Docker, IAM, Firebase or business financial tables.

Use the CI-passed, exact head SHA in these two commands.

\`\`\`bash
(
set -euo pipefail

BASE=/home/ubuntu/sbi-r31-11-4n/source
TARGET=/home/ubuntu/sbi-r31-11-4o/source
BRANCH=feature/sbi-r31-11-4o-domain-owner-dns-evidence-20261127
SHA=<FINAL_40_CHAR_CI_PASSED_COMMIT_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4o
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"

echo "DB_R31_11_4O_SOURCE=PASS_PINNED"
)
\`\`\`

\`\`\`bash
SHA=<FINAL_40_CHAR_CI_PASSED_COMMIT_SHA>
PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
SCRIPT=/home/ubuntu/sbi-r31-11-4o/source/staging/aws_login_v150/r31_11_4o_combined_domain_ownership.py

"$PY" -B -u "$SCRIPT" --source-sha "$SHA"
\`\`\`

Expected non-fabricated result examples (NOT YET tested on AWS):

\`\`\`text
DB_R31_11_4O_DOMAIN_DOSSIER=PASS_STRICT_SIX_GATES_NO_SECRETS
DB_R31_11_4O_OWNER_EVIDENCE_PENDING=6
DB_R31_11_4O_OWNER_EVIDENCE_REFERENCED_UNVERIFIED=0
DB_R31_11_4O_OWNER_METADATA_REVIEWED_NOT_APPROVED=0
DB_R31_11_4O_QA_HOSTNAME=NOT_PROVIDED
DB_R31_11_4N_COMBINED_EVIDENCE_PREFLIGHT=PASS_NO_DEPLOY
DB_R31_11_4O_4N_THROUGH_4H_COMBINED_QA=PASS_READONLY
DB_R31_11_4O_AFTER_QA_CADDY_PG=PASS_UNCHANGED
DB_R31_11_4O_REGISTRANT_AUTHORITY=NOT_INDEPENDENTLY_VERIFIED
DB_R31_11_4O_ZONE_DELEGATION=NOT_INDEPENDENTLY_VERIFIED
DB_R31_11_4O_DNS_CHANGE_RIGHTS=NOT_INDEPENDENTLY_VERIFIED
DB_R31_11_4O_DOMAIN_OWNER_APPROVAL=NOT_ESTABLISHED
DB_R31_11_4O_COMBINED_DOMAIN_PREFLIGHT=PASS_PREPARATION_ONLY
DB_R31_11_4O_REAL_DNS_OWNER_VERIFICATION=NOT_PERFORMED
DB_R31_11_4O_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4O_EXTERNAL_ACCEPTANCE_22=NOT_TESTED
DB_R31_11_4O_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4O_FINANCIAL_APPLY=LOCKED
DB_R31_11_4O_PRODUCTION_RELEASE=BLOCKED
\`\`\`

**STOP policy:** Any \`STOP=DB_R31_11_4O_DOMAIN_EVIDENCE_REVIEW_REQUIRED\`
is a hard stop. Do not run database provisioning, weaken access rules,
change Caddy, publish a port, add TXT DNS records, or create certificates
to force a PASS. Share only fixed nonsecret status lines.

## Next genuine work, which must be separately reviewed

1. Domain owner supplies one real organization-controlled candidate QA
   hostname and its parent authoritative zone.
2. Confirm registrant/domain control with authorized provider evidence,
   separately from DNS delegation/record control. Identify owner and
   independent reviewer by secure nonpublic process.
3. Review the change ticket, restricted QA endpoint/network and data flow.
4. Match independently verified external evidence to the 4N and 4M
   registers; do not mark 4K's approvals true without separate sign-off.
5. Only after explicit approved design and controlled rollback may a
   genuine external QA TLS listener be proposed. It still must pass
   external mTLS, certificate revocation, Firebase expired/revoked
   session, tenant isolation and 22 actual acceptance cases.

R31.12 is ACTIVE_QA_DESIGN_RELEASE_GATED. Financial Apply LOCKED.
Production release BLOCKED.
