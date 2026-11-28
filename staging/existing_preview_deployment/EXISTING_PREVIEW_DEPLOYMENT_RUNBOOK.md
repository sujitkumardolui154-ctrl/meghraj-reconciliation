# SBI R31 — Corrected Existing-Preview Deployment Decision
Date: 2026-11-28

## Owner's binding deployment target
**https://sbi-preview.13-232-241-221.sslip.io/login**

Deploy into the **existing AWS Lightsail application, Caddy routing and PostgreSQL-backed workspace**. Do not migrate the UI to another platform, replace the login URL with `*.ts.net`, purchase a domain, or silently create a separate production web service. The user-selected URL and existing system take precedence over the earlier private-multisite tailnet *proposal*.

The existing Caddyfile source contains a `/login` route to `sbi-login-workspace:8080`; the exact live route, certificate, current application commit and firewall exposure must be verified on AWS before any updates. No changes have been made in AWS by this GitHub decision.

## Private staff access at the same URL
An `sslip.io` hostname normally maps to the embedded IP; it does **not** by itself create private network isolation or grant DNS administration. An authenticated public HTTPS login is **not the same as network-private access**. Choose an approved deployment posture:
- **Restrict current HTTPS ingress** to organization-approved fixed office/VPN egress CIDRs while preserving the same hostname, valid TLS certificate, login and local Caddy routing; remote staff use the approved egress service. Handle IPv4 and IPv6, including other published containers and bypass routes.
- If staff lack stable egress CIDRs, independently review a private employee tunnel/overlay **that keeps this exact browser URL** and supports safe internal DNS/routing and TLS validation. Tailscale may serve as a network transport but **no new `*.ts.net` browser hostname** or app platform may be substituted.
- If existing URL remains directly reachable from the public internet, describe it as **publicly reachable, access-controlled**. Requiring Firebase login alone does not satisfy the no-public-access objective. Formal owner/security signoff must resolve the tradeoff before production acceptance.

Do not remove current ingress before verifying an approved replacement employee route, rollback access and independent verification of both IP families. Never change production Caddy, DNS, ingress or certificates just to make a QA status PASS.

## Pre-deployment read-only review
1. Pin repo and deployed application revision; capture Caddy SHA safely without displaying configuration or credentials. R31.11.4W operator-reported Caddy baseline and unpublished private QA PG are reusable as historical evidence, but recheck any actual changed runtime.
2. Inventory `/login`, `/auth/*`, authenticated app endpoints, firewall and port exposure, certificate/SNI, other publicly published Docker ports, private PG networking and actual IAM scope (no secrets).
3. Independently test the actual existing hostname (not hypothetical new origin) for correct TLS certificate, login/logout, secure cookie, CSRF/Host/Origin enforcement, server-side Firebase signature/expiry/revocation, authorized vs unauthorized employee and tenant RLS across two locations.
4. Validate reports, reconciliation v2.51 scope, source payments, credit-note and invoice/GST behavior, backups/restores, owner-scoped financial permissions and audit/rollback evidence. Reuse unchanged module QA where source SHA and test scope match.
5. Negative-test direct public reachability according to the explicitly approved network posture. Test wrong-tenant identity, revoked user/device/session, spoofed proxy/owner headers, prohibited finance routes, and bypass ports. Capture safely redacted witnessed results.
6. Obtain independent security, network-change, rollback and financial release approvals. Keep `FINANCIAL_APPLY=LOCKED` and `PRODUCTION_RELEASE=BLOCKED` until separately authorized.

## QA and legacy gates
The previous 22 public external mTLS test cases are **0/22 actually executed**, remain historically pending and are **not waived** by this correction. The previous tailnet P1–P7 proposal is not accepted as implemented and is superseded as a *deployment target*. A security reviewer must explicitly map retained, changed and replacement controls to the **existing URL** and approve appropriate real E2E tests before release. Do not repeat R31.11.4U–4Y unchanged tests; only target new source/architecture changes and necessary live acceptance.

## Current state
`DEPLOYMENT_TARGET=EXISTING_SSLIP_LOGIN`
`DOMAIN_PURCHASE=NOT_REQUIRED`
`NEW_PLATFORM=NOT_AUTHORIZED`
`PRIVATE_EMPLOYEE_INGRESS=DESIGN_REVIEW_PENDING`
`EXTERNAL_MTLS_ACCEPTANCE=0_OF_22_NOT_WAIVED`
`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
