# R31 — Verify existing AWS application before same-host deployment

## Binding target
`https://sbi-preview.13-232-241-221.sslip.io/login` remains the only authorized deployment URL. Use the existing AWS Lightsail web application, current Caddy reverse proxy, Firebase login, and private PostgreSQL infrastructure. No new platform, purchased domain, or substitute `*.ts.net` browser URL.

## Checked from GitHub source
- `staging/aws_login_v150/Caddyfile.workspace` has a `/login` route to `sbi-login-workspace:8080`.
- `dashboard_source/login.js` calls same-origin `/auth/config`, `/auth/csrf`, submits Firebase password sign-in to Identity Toolkit, then posts ID token to `/auth/session` and redirects to `/`.
- R31.11.4W operator AWS result previously confirmed the existing Caddy configuration baseline and dedicated *QA* PostgreSQL remained private/unpublished.
- Repo policy locks `FINANCIAL_APPLY=LOCKED` and `PRODUCTION_RELEASE=BLOCKED`.

These are source/previous-receipt facts, not proof the current login works or that the public URL is network-private.

## Read-only runtime audit
Run `verify_existing_runtime_readonly.py --source-sha <exact revision>` in a new pinned Git worktree. It issues one unauthenticated HTTPS GET to the **existing** login URL, without following redirects or sending credentials, and validates the TLS chain/hostname using normal curl verification. It inspects only the existing Caddy container route and SHA, observes whether a login-workspace container is running, and checks isolated QA PostgreSQL container/network metadata. It displays status labels only; no headers, response bodies, passwords, cookies, certificate keys, raw Caddyfile or Docker environment data.

A 200, 302, or any HTTP response is **not** Firebase login acceptance. Local inspection is **not** a substitute for independent public internet reachability checks across IPv4 and IPv6, cloud firewall review, current application revision provenance, backups, tenant RLS over HTTPS or real two-user session acceptance.

## Approval/QA sequence
1. Review exact AWS result codes. If HTTPS TLS or Caddy drift: investigate; do not automatically change live Caddy.
2. Determine the allowed employee access posture for the same hostname. Direct internet exposure plus Firebase login is access-controlled **publicly reachable**, not private networking. Restrict ingress using approved office/VPN egress or an independently approved same-URL private route.
3. Verify two real independent employee Firebase sessions, CSRF, cookie attributes, signed session expiration/revocation, wrong-tenant RLS, negative financial endpoints, no credential leaks, and safe audit logs.
4. Confirm unchanged financial source/backup/reconciliation QA receipts, perform targeted delta tests for any change; obtain independent security, rollback, business and financial-release approvals.
5. Keep the earlier 22 real external mTLS cases historically at 0; independent security authority must approve a documented replacement risk/test map before releasing the existing-URL deployment.

No Caddy writes, Docker starts/stops, IAM grants, TLS issuance, firewall updates or financial SQL writes are part of this audit. `FINANCIAL_APPLY=LOCKED`, `PRODUCTION_RELEASE=BLOCKED`.
