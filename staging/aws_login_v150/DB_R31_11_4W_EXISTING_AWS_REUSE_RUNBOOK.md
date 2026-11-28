# DB-R31.11.4W — Existing AWS Resource Reuse Review

**Purpose:** identify host resources that may support future isolated external HTTPS/mTLS QA. Existing host configuration does NOT imply independent domain/certificate/ingress approval or permission to release PostgreSQL-backed financial writes.

## Existing references inspected
- R31.11.4G preflight source describes the private `sbi-r3114-private-postgres` container and `sbi-r3114-private-isolated` internal Docker network.
- R31.11.4Q defines a separate QA ingress, restricted source CIDRs, no public PostgreSQL port, no direct QA-to-production finance, and no production Caddy change.
- R31.11.4R explicitly records `NOT_GRANTED` deployment authorization and eight independent prerequisites not approved.
- R31.11.4S records 22 real external acceptance cases unexecuted.
- R31.11.4U 4K/4S targeted tests and public scanner passed on AWS, per the operator output. R31.11.4T reused exactly three GitHub synthetic/design QA checks.

## Dedicated 4W audit
`r31_11_4w_existing_aws_resources_readonly.py` uses pinned local source, read-only Docker inspect commands, and an in-memory SHA256 comparison of existing Caddyfile. It does not expose the config content. It examines the private QA Postgres container and network, and cross-checks the existing 4R/4S gated records. No secrets/certificates are read, no live DNS queries are made, no API/network ports are opened, no databases are queried and no tests are replayed. **This is host metadata evidence only.** If runtime or configuration has drifted the script stops for review.

## Need independent evidence before any external QA
1. Proof of organizational domain entitlement, delegated DNS control, and named owner approval.
2. Approved separate QA ingress, source CIDRs, change and rollback tickets; preserve production Caddy and private PG constraints.
3. Actual approved server TLS certificate, independent test-client CA, certificate inventory/custody, revocation implementation.
4. Named remote client/test owner, security reviewer and witnessed 22-case acceptance execution.
5. Independent security/finance signoff; financial Apply remains LOCKED and production release remains BLOCKED.

Do not put passwords, keys, client cert private material, Firebase cookies, real owner IDs, private Caddy contents, or complete Docker inspection JSON in chat or GitHub. Report only fixed PASS/NOT_VERIFIED status lines.
