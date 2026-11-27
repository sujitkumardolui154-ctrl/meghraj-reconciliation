# DB-R31.11.4N — QA Hostname/DNS & Certificate Evidence Intake

**Scope:** nonsecret evidence intake and combined read-only AWS preflight. This is NOT authorization to deploy an external mTLS listener, issue certificates, change DNS, Caddy or firewall, alter Firebase credentials or write to PostgreSQL.

## Source acceptance carried forward

- R31.11.4M AWS operator screenshot: combined preflight PASS_READONLY_NO_DEPLOY.
- Original 4K/4M approval register: 23 PENDING, zero submitted and zero reviewed.
- R31.11.4L: 22 real external acceptance cases NOT_TESTED.
- Original Caddy SHA-256 baseline: 61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b.
- R31.12 ACTIVE_QA_DESIGN_RELEASE_GATED; Financial Apply LOCKED; production BLOCKED.

## Phase-specific approval fields: 10 PENDING

| Required evidence | Exact source field |
|---|---|
| Authorized QA change request | change_ticket |
| Proposed QA hostname | qa_fqdn |
| Domain-owner sign-off | fqdn_owner_approved |
| Independent DNS-control proof | dns_control_verified |
| Test CA ownership and trust-scope sign-off | qa_client_ca_owner_approved |
| Client certificate inventory and expiry policy | qa_client_cert_inventory_approved |
| Actual certificate revocation enforcement plan | qa_client_revocation_mechanism_approved |
| Server-certificate lifecycle and rotation | server_certificate_lifecycle_approved |
| Approved server certificate provider | server_certificate_provider |
| Nonsecret test-client CA reference | client_ca_metadata_reference |

All ten items begin PENDING in the 4N JSON intake. The other 13 deployment approvals remain PENDING in the unchanged original 4K/4M packet.

### Evidence states, not approval states

PENDING: no ticket, digest, reviewer or time.

REFERENCED_UNVERIFIED: a genuine external evidence-ticket ID and SHA-256 digest are recorded, but independently reviewed approval is absent.

METADATA_REVIEWED_NOT_APPROVED: a different reviewer ticket and a UTC timestamp have been provided. This is only a metadata review, not proof of DNS ownership, CA custody or security approval.

Never fabricate ticket IDs, SHA-256 values or timestamps. Actual evidence must be reviewed outside this intake in the proper authorized source. Do not store private keys, PEM, Firebase UIDs, passwords, cookies, tokens or secrets in this file, GitHub or chat.

The optional proposed QA hostname and DNS zone remain PENDING until the organization actually supplies a candidate. A syntactically valid hostname is still PROPOSED_UNVERIFIED; no DNS queries are executed by this stage.

## AWS source pin and read-only combined audit

Use ONLY the exact GitHub CI-verified commit in the next commands.

Source checkout:
    BASE=/home/ubuntu/sbi-r31-11-4m/source
    TARGET=/home/ubuntu/sbi-r31-11-4n/source
    BRANCH=feature/sbi-r31-11-4n-dns-pki-evidence-intake-20261127
    SHA=<FULL_CI_VERIFIED_40_CHARACTER_SHA>
    test -d "$BASE"
    test ! -e "$TARGET"
    git -C "$BASE" fetch origin "refs/heads/$BRANCH"
    test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
    mkdir -p /home/ubuntu/sbi-r31-11-4n
    git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
    test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
    test -z "$(git -C "$TARGET" status --porcelain)"
    echo "DB_R31_11_4N_SOURCE=PASS_PINNED"

Combined read-only execution:
    SHA=<FULL_CI_VERIFIED_40_CHARACTER_SHA>
    PY=/home/ubuntu/sbi-r3114c-firebase-venv/bin/python
    SCRIPT=/home/ubuntu/sbi-r31-11-4n/source/staging/aws_login_v150/r31_11_4n_combined_dns_pki_preflight.py
    "$PY" -B -u "$SCRIPT" --source-sha "$SHA"

Expected key statuses, not yet confirmed on AWS:

    DB_R31_11_4M_COMBINED_EVIDENCE_PREFLIGHT=PASS_READONLY_NO_DEPLOY
    DB_R31_11_4N_4M_COMBINED_SECURITY=PASS_READONLY
    DB_R31_11_4N_DNS_PKI_INTAKE_SCHEMA=PASS_EXACT_TEN_FIELDS
    DB_R31_11_4N_EVIDENCE_PENDING=10
    DB_R31_11_4N_EVIDENCE_REFERENCED_UNVERIFIED=0
    DB_R31_11_4N_METADATA_REVIEWED_NOT_APPROVED=0
    DB_R31_11_4N_QA_HOSTNAME=NOT_PROVIDED
    DB_R31_11_4N_DNS_OWNERSHIP=NOT_INDEPENDENTLY_VERIFIED
    DB_R31_11_4N_CERT_ISSUANCE_AND_REVOCATION=NOT_VERIFIED
    DB_R31_11_4N_AFTER_QA_DB_CADDY=PASS_READONLY_UNCHANGED
    DB_R31_11_4N_COMBINED_EVIDENCE_PREFLIGHT=PASS_NO_DEPLOY
    DB_R31_11_4N_EXTERNAL_HTTPS_MTLS=NOT_TESTED
    DB_R31_11_4N_FINANCIAL_APPLY=LOCKED
    DB_R31_11_4N_PRODUCTION_RELEASE=BLOCKED

If STOP appears, use the fixed DB_R31_11_4N_BLOCK_REASON to review source/metadata only. Do not mutate Caddy, firewall, DNS, certificates, PostgreSQL or any application runtime.

## Separately gated next activities

When an approved candidate domain and zone are supplied, a future, independently authorized process can review DNS authority via read-only inspection. DNS response data alone never constitutes owner approval. A test-only CA, client/server certificate lifecycle and actual revocation implementation need real evidence and independent review. Live external HTTPS/mTLS acceptance remains NOT_TESTED across 22 cases and requires a separately approved rollout and rollback.

**R31.12 development may continue in isolated design QA. Financial Apply stays LOCKED and production release BLOCKED.**
