# DB-R31.11.4Y — Independent Authorization Evidence Collection

## Scope
This is a real-evidence intake milestone, NOT another source-level authorization rehearsal. R31.11.4U, 4V, 4W, and 4X previous successful AWS checks are reused without replay. There is **no live external HTTPS/mTLS approval**, no new QA FQDN, certificate, ingress, or firewall configuration, and no production-finance authorization.

## Intake workflow
1. **Domain ownership / DNS:** Obtain an owner-authorized organizational QA FQDN choice, registrar entitlement proof, zone administration and delegation verification, approved change request, and independent reviewer receipt. These must be verified through the organization's real DNS/registrar administration and owner, not inferred from public DNS alone.
2. **Ingress and isolation:** Obtain approved nonproduction topology, restricted source CIDRs, no change to public Caddy, no published PostgreSQL port, exact method/path allowlist, no finance endpoints, independent firewall review, and specific change/rollback ticket.
3. **TLS and client CA:** Obtain the certificate provider and QA domain SAN suitability, authorized CA custody owner, named client certificate inventory, issuance/renewal plan, and independently reviewed revocation enforcement. Do not store any private key or client secret in GitHub.
4. **Change / rollback / reviewers:** Obtain the named security reviewer and external test owner, time-bounded authorization, independent rollback owner, monitoring and emergency stop plan, and written scope for all 22 real external acceptance cases.

## Handling evidence
Keep actual sensitive proof and credentials in an authorized private evidence store. Only nonsecret reference IDs and vetted SHA256 digests go into a candidate copy of `r31_11_4y_evidence_template.json` stored **outside the Git worktree**. Allowed group statuses: `PENDING` or `SUBMITTED_FOR_INDEPENDENT_REVIEW` only. Submitted evidence does not mean verified, approved, ready to deploy or security accepted.

Do **not** fill placeholders with invented approvals; do not push external evidence bundles to public GitHub. The screening script only checks safe metadata shape and rejects attempts to set financial write/release flags. An independent reviewer must validate the source proof, approve the exact configuration and change ticket, and record external acceptance separately.

## Execute targeted QA only
`python3 -B staging/aws_login_v150/r31_11_4y_nonsecret_evidence_screen.py`
`python3 -B -m unittest discover -s staging/aws_login_v150 -p 'test_r31_11_4y_nonsecret_evidence_screen.py' -v`

No pre-existing 4J/4O/4P or 4K/4S suites are rerun. External acceptance remains **0/22** pending actual authorized nonproduction QA infrastructure. Financial Apply **LOCKED**; Production Release **BLOCKED**.
