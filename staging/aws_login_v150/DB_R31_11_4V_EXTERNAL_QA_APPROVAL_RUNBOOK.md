# DB-R31.11.4V — External QA Infrastructure Approval Inventory

**Status:** Source-only preparation; NO external endpoint approval or deployment.

## Evidence reviewed
- 4N DNS/PKI intake: QA hostname and DNS zone PENDING.
- 4O domain dossier: registrant, zone delegation, DNS rights, and owner approval NOT_VERIFIED.
- 4P PKI plan: client CA, server certificate, revocation NOT_SELECTED_OR_APPROVED / NOT_TESTED.
- 4Q isolation policy: separate QA ingress/HTTP adapter NOT_DEPLOYED, firewall scope and rollback designed but not accepted.
- 4R approval gate: eight independent prerequisites NOT_APPROVED_OR_VERIFIED; authorization NOT_GRANTED.
- 4S acceptance matrix: 22 cases NOT_TESTED_EXTERNAL.

## Audit
`r31_11_4v_approval_inventory.py` reads the existing 4O/4P/4Q/4R/4S JSON sources and verifies unchanged fail-closed states. The program is strictly static: it does not perform external DNS lookup, contact AWS, verify real certificates, start containers, connect PostgreSQL, or run combined prior QA.

## Required owner/security evidence (not provided yet)
1. Organization-controlled hostname, registrar entitlement, delegated zone and independent change authorization.
2. Isolated QA ingress, approved source CIDRs, no public PostgreSQL access, isolated proxy and explicit rollback plan.
3. Approved server certificate, separate QA client CA/key custody and revocation enforcement plan.
4. Independent reviewers, named remote test client and approval tickets, plus scope for 22 external tests.

Keep private keys, test-user passwords, tokens and identity data out of GitHub and chat. Only safe ticket IDs, hashes and review status may be recorded in public source after independent verification.

## Rules
- Reuse R31.11.4T three previously verified synthetic/design QA results; do not rerun 4J/4O/4P.
- R31.11.4U scanner and 16 targeted AWS unit tests have owner-reported PASS at SHA 35dbc930c04faccd42777b12076fd764211e5910. This is not authorization to release.
- Only new 4V inventory logic needs targeted CI.
- No deployment, DNS changes, certificate issuance, firewall changes, financial writes, or production configuration mutation.
- Financial Apply LOCKED; Production release BLOCKED.
