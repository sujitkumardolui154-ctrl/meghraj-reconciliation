# R31.11.4X — External QA Domain, Certificate and Ingress Authorization

Scope: **authorization evidence intake / source-only preflight**. No external endpoint deployment, no DNS change, no certificate issuance, no firewall changes, no PostgreSQL or financial writes.

## Previously accepted findings reused
- 4U scanner + 16 targeted 4K/4S tests: AWS operator-reported PASS at 35dbc930c04faccd42777b12076fd764211e5910.
- 4V static source inventory: AWS PASS at 79c384aa82ff1055c4c0486e0eed50d797061ef0.
- 4W pinned host inspection: Caddy baseline unchanged, private QA PostgreSQL unpublished, AWS PASS at cc14dc96abfdfd07465929e1b7ead4ef2a42b7de.
- 4T previously verified 3 synthetic/design reuse receipts. No replay of 4J, 4O, 4P or 4R–4S combined QA.

## Exact source-based block
The 4K approval packet has 16 false flags; 4N has QA hostname/zone PENDING; 4O owner/domain NOT VERIFIED; 4P server certificate/client CA NOT SELECTED; 4Q ingress design NOT AUTHORIZED; 4R has 8 independent prerequisites NOT APPROVED; 4S has 22 real external cases NOT TESTED.

## Independent evidence required
1. Approved organization-owned QA FQDN and DNS control: owner, change ticket, zone delegation, record-change authorization; independent verification outside source.
2. Approved isolated QA ingress/firewall restricted source CIDRs, separate proxy, no production Caddy modification, no public PostgreSQL port, and no financial endpoint access.
3. Approved server certificate for that QA FQDN and client-cert CA under controlled custody; inventory, validity, renewal and actual revocation enforcement plan.
4. Security-approved rollback owner, separate change/rollback tickets, monitoring, approved external test client and independent reviewer.
5. Written authorization **before** any external network or mTLS acceptance run; 22 planned cases then require witnessed real evidence.

Never paste or commit keys, certificates containing private material, cookies, passwords, tokens or sensitive AWS configs. Record only independently validated metadata and safe ticket identifiers. Do not edit historical 4K–4S approvals merely to make automated checks pass. Use reviewed change records, not assertions of approval.

## 4X new work
`r31_11_4x_external_authorization_preflight.py` only checks 7 existing JSON schemas and confirms that they still explicitly block external deployment. This is a pass for *accurate unmet-prerequisite reporting*, not security acceptance. The runtime command must be pinned to a source SHA and operate in an isolated worktree.

Security release: BLOCKED. Financial Apply: LOCKED. 0/22 external cases executed.
