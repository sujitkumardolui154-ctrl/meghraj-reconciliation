# R31 — Same-URL, Same-Lightsail Firebase→PostgreSQL RLS Integration: Approval Design

Date: 2026-11-28
Status: **DESIGN/CHANGE-CONTROL REVIEW ONLY. NO DEPLOYMENT AUTHORIZED.**
Owner's binding URL: **https://sbi-preview.13-232-241-221.sslip.io/login**
Existing Caddy and login container: PRESERVE
New application platform: FORBIDDEN without explicit separate approval
Public domain purchase or `*.ts.net` replacement: NOT REQUIRED / NOT AUTHORIZED
Production financial execution: **LOCKED**
Production release: **BLOCKED**

## Grounded existing source and AWS evidence

1. Existing `staging/aws_login_v150/Caddyfile.workspace` routes `/api/*` to `sbi-login-workspace:8080` in the *tracked source template*. Active Caddy's literal route was not verified by prior read-only tools; baseline fingerprint was unchanged and live auth endpoints responded correctly.
2. Existing `staging/aws_login_v150/app.py` is primarily a Firebase-authenticated UI shell. The R31 private staging flag registers `stage_r31`; only with the additional R31.11.4 flag does the private PostgreSQL RLS blueprint register. Existing `/healthz` source reports `financial_data_connected=false` and `financial_execution_enabled=false`.
3. The R31.11.4 blueprint exposes a GET-only source-evidence route conditional on **both** flags. Its adapter binds the already verified Firebase session user to a protected per-user restricted PostgreSQL LOGIN role in the dedicated QA database, with read-only SQL and no self-declared HTTP owner identity.
4. Current operator-reported AWS result: both exact flag values `NOT_ENABLED_OR_REVIEW`, candidate module `NOT_VERIFIED_IN_RUNNING_IMAGE`, anonymous HTTPS `HTTP_401`. This is not evidence the HTTP handler exists or that RLS works through the existing URL.
5. Reusable PASS: real A/B HTTPS login+CSRF; protected A/B UID-to-QA-role mapping attestation; restricted PostgreSQL 16 QA RLS catalog, two roles/maps and zero QA source rows. **No need to repeat unchanged checks.**
6. R31.11.4F private real-auth Flask test-client design, synthetic rollback rows and prior QA records are scoped to private/in-process or isolated PostgreSQL tests; they are **not** existing-host external HTTPS A↔B acceptance.

## Core security decision: do NOT flip the legacy R31 staging flags on the public login service

Enabling `SBI_R31_PRIVATE_STAGING_ENABLED` may also register *other* R31 staging routes on the already publicly addressable `sslip.io` origin. The existing R31.11.4 PostgreSQL adapter assumes isolated internal-only access and protected UID10001 mode-0600 secret files. Connecting the public-facing login container directly to the dedicated QA PostgreSQL network or mounting protected QA secrets is a new trust-boundary and security decision, even though it uses the same AWS host.

A green catalog test does **not** authorize those modifications. Never automatically add the private Docker network, enable both existing QA flags, copy password files, weaken Firebase checks, or expose a database port just to make an HTTP test return 200.

## Proposed in-place implementation contract (no code deployment in this artifact)

- Retain **the existing browser origin** `https://sbi-preview.13-232-241-221.sslip.io` and `/login`. Any approved application update is an in-place, rollback-capable revision to the same Lightsail application; no replacement platform/domain.
- A dedicated independently reviewed *single-route* feature gate for the R31 read-only tenant acceptance path is preferable to enabling the broad private-staging flag on the public runtime. All other financial routes remain disabled. Exact path/method, authorization audience, QA-only marker, and network/access restrictions must be approved before implementation.
- Verify **real Firebase Admin session** via current middleware with revocation checks, verified non-admin QA identity and claims; trust only server-side session identity, never `owner_uid`, `pg_role`, custom proxy headers, query string, or client cookies as tenant authority.
- Verify per-account PostgreSQL session_user bound to protected owner map, transaction read-only, forced-RLS active, denied INSERT/UPDATE/DELETE and zero bypass/superuser privileges. The current source adapter was designed for the isolated QA DB; never aim it at `sbi_reconciliation_main` or `sbi_reconciliation_staging` by implicit fallback.
- Keep QA PostgreSQL unpublished on port 5432. Review exact network path and credential isolation (private service connection, minimum bridge/attach rights, non-root process, read-only mounts, no Docker socket). Any same-host internal process is **not** a new application platform but still needs the owner's explicit architecture/security approval.
- Existing public URL must not be described as network-private merely because Firebase login is required. Explicitly approve restricted source access (e.g., fixed office/VPN egress plus equivalent remote employee path) or formally accept a public-internet-reachable authenticated service with compensating controls. Test IPv4 AND IPv6 bypass paths.
- Preserve Caddy image/config SHA, exact TLS hostname trust, existing login and other documented routes, existing database isolation, monitoring, rollback image digest and fail-closed financial routes.

## Mandatory acceptance gates before any in-place change

| ID | Gate | Evidence required | Current |
|---|---|---|---|
| S1 | Owner-approved existing URL + same-host scope | Already committed policy, exact deployed revision/image ID and rollback owner | PARTIAL |
| S2 | Independent exposure/network design | IPv4/IPv6, Caddy, method/path allowlist, restricted ingress or explicit risk acceptance | PENDING |
| S3 | Review targeted read-only RLS handler delta | Auth chain, feature flag isolation, DB role binding, no other staging routes, no financial DML | PENDING |
| S4 | Secret & QA DB network boundary | Non-root, protected secret mounts, dedicated read-only DB, unpublished ports, no production finance access | PENDING |
| S5 | Two real HTTPS test user sessions | Prior A/B successful Firebase login receipts, same mapping attested | PASSED WITH RECORDED SCOPE |
| S6 | Real owner-isolation HTTP tests | A→A positive and A→B denied; B→B positive and B→A denied; anonymous, forged UID/role, wrong method | NOT TESTED |
| S7 | Revocation/cookie and endpoint negative tests | Expiry/revocation without disrupting genuine staff; CSRF, cross-origin, cookies, errors and safe logs | PARTIAL |
| S8 | QA data + cleanup and rollback | Approved **non-customer synthetic** data; verified cleanup, role grants, exact original Caddy/app restoration | PENDING |
| S9 | Independent deployment release | Reviewer signoff, operations rollback and no financial Apply authorization | NOT GRANTED |

## Critical test-data point

The current QA data contains **zero payment/source rows**. An empty list for both users does not prove RLS excludes another owner's records. A real HTTPS positive/negative test needs approved non-sensitive owner-tagged QA fixtures visible to separate HTTP/database connections. **Uncommitted rows in a transaction-local ROLLBACK fixture are generally invisible to another request/connection** and cannot substitute for real HTTP acceptance. A separate DBA/security-approved synthetic fixture lifecycle (possibly committed *only within the isolated QA DB*, with explicit post-test cleanup and zero-row verification) is required. Do not insert actual SBI/customer evidence or write to main/staging financial databases.

## Intended safe next actions

1. Perform a **source-only diff review** of the existing login app, current R31.11.4 blueprint/adapter and protected QA network. Record the minimum single-route in-place design and its owner/security approvals.
2. Separately verify current deployed container image and approved access/release topology using read-only metadata. Reuse earlier Caddy/HTTPS/role catalog receipts unless a relevant component changes.
3. Only after authorization, implement and test the narrowly scoped application delta in a restricted QA process **on the same Lightsail host**, preserving the exact existing URL and ensuring the RLS route is not exposed prematurely.
4. Independently authorize any controlled in-place rollout; run real HTTPS A/B isolation with approved synthetic fixture lifecycle and negative cases; verify cleanup and rollback. No automatic promotion to production.
5. Maintain historical external HTTPS/mTLS case count **0/22**, with explicit risk-equivalent replacement approvals rather than silently waiving them.

## No-release state

`R31_EXISTING_HTTPS_RLS_ROUTE=NOT_VERIFIED_ENABLED`
`R31_TWO_WAY_CROSS_TENANT_HTTP=NOT_TESTED`
`R31_INPLACE_INTEGRATION_CHANGE=NOT_APPROVED`
`R31_REAL_FINANCIAL_WRITES=ZERO`
`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
