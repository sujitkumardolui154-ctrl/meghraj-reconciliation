> **SUPERSEDED DEPLOYMENT TARGET — 2026-11-28:** The owner explicitly requires deployment at **https://sbi-preview.13-232-241-221.sslip.io/login** on the existing AWS Lightsail application. Do **not** replace the user-facing hostname with a new `*.ts.net` address, launch a separate application platform, or purchase a domain. The Tailscale Serve and new-WSGI-entrypoint proposals below remain historical design candidates, **not authorized deployment instructions**. The controlling decision is [existing_preview_target_policy.json](../existing_preview_deployment/existing_preview_target_policy.json) and [the updated runbook](../existing_preview_deployment/EXISTING_PREVIEW_DEPLOYMENT_RUNBOOK.md). Keep all old QA and release locks intact.\n\n# SBI Reconciliation Workspace — Private multi-location access (review-only proposal)
Owner scope changed on 28 November 2026: **authorized employees from multiple locations, no public application access and no domain purchase**.

## Decision: private tailnet, NOT a public HTTPS QA endpoint

**Proposed transport**: separately administered Tailscale tailnet with named staff identities, MFA at the identity provider, approved devices, and restrictive grants, allowing only employee devices to reach the application service over tcp/443. Use Tailscale MagicDNS + **Tailscale Serve (private HTTPS)** on a Tailscale-supplied `*.ts.net` hostname. **Never Tailscale Funnel** (which exposes services to the public internet). Public registrar/Route 53/LightSail domain purchase is not required for this design.

Architecture:
```text
Approved employee office / home / branch devices
      | employee-specific tailnet sign-in, device approval, deny-by-default grants
      v
Private WireGuard-based Tailscale overlay (NO public web ingress)
      |
      v
Tailscale Serve HTTPS (*.ts.net; employee-only ACL)
      | local host 127.0.0.1:18181 ONLY (subject to approved implementation)
      v
Separate nonroot staged WSGI candidate with exact Host + Origin allowlist
      | Firebase signed session, CSRF, explicit employee entitlements
      v
Existing read-only reporting / approved invoice APIs
      |
      v
Restricted PG16 row-level roles (never a public Postgres port)
```

**Security fact**: an existing publicly reachable `sbi-preview.13-232-241-221.sslip.io` and Caddy route remain public network endpoints even if they require a login. Merely installing a VPN does not make the project private. Public port exposure must be removed or restricted on **both IPv4 and IPv6** after approved cutover. Do NOT disable the current working access before verifying the private route and an independently approved rollback path.

**This PR is source-only.** It does not install Tailscale, change Caddy, alter Firebase users/claims, publish or close Docker ports, change Route 53/IAM, rotate certificates, issue network grants, restart services, change financial SQL grants or deploy anything to AWS. Existing production public preview and private PG remain unchanged.

## Seven replacement-scope acceptance gates — ALL PENDING

| Gate | Acceptance requirement | Reuse / fresh proof |
|---|---|---|
| P1 — Private scope, change owner, rollback | Written architecture change authorization; confirm no public web access and separate private-only staging; Caddy/DB snapshots; rollback owner | Reuse R31.11.4W baseline only; new approval needed |
| P2 — Staff identity and device admission | Tailnet created by authorized organization; individual employee invites, role group grants only to app HTTPS; approved devices, offboarding, MFA, deny-by-default, no public share/Funnel | Entirely fresh live identity/device evidence |
| P3 — Tunnel & HTTPS origin | Verified Tailscale Serve HTTPS and correct *.ts.net certificate; upstream bound to loopback, no public Docker bind; health checks; stable internal DNS; no plaintext user route | Reuse synthetic TLS design concepts, not external or live acceptance |
| P4 — Firebase/auth/CSRF & employee scopes | Configure the exact hostname as an approved Origin and Firebase Auth domain *where necessary*, test two distinct real nonadmin employees, fresh/invalid/expired/revoked session, CSRF, role/owner separation | Reuse previous two-user in-process R31.11.4I evidence only as historical comparison; new tailnet browser acceptance required |
| P5 — Financial source, RLS, backup and parity | Confirm restricted Postgres role grants and tenant separation; reports/credit notes/branch SOL validation, historical source parity, isolated backup/restore rehearsal, zero unauthorized financial writes | Reuse previous synthetic invoices and RLS tests as scoped evidence; targeted live source QA fresh |
| P6 — Two-location private positive & negative tests | Authorized staff at two independent sites can reach only own permitted APIs; unauthorised staff/device, removed user, wrong tenant, spoofed headers and forbidden upload/financial endpoints DENIED; safe logs | Fresh external-location **over private tailnet** test evidence required |
| P7 — IPv4/IPv6 public exposure removal, rollback & signoff | Verify app not reachable from ordinary internet on either IP family; preserve locked PostgreSQL, close old preview access only after approved cutover, rollback verification, independent security and finance signoff | New witnessed network acceptance; no synthetic substitution |

The old R31.11.4K–4S **23 external-public-infrastructure approval fields** and **22 external HTTPS/mTLS cases** remain historically PENDING / 0 tested. They were designed for an independent **public-facing external QA listener**. They are **not marked PASS, waived, or automatically N/A** by this proposal. An independent security reviewer must approve the topology substitution and map remaining risks/tests to the new seven private gates. If an external public QA endpoint is later chosen, the old 23/22 requirements reactivate. The standalone source-only QA script confirms this strict boundary.

## Reuse existing QA — do not replay unchanged workflows

1. **R31.11.4W**: source-pinned Caddy baseline + private unpublished PG host checks from operator AWS output; exact SHA `cc14dc96abfdfd07465929e1b7ead4ef2a42b7de`. No claim it validates Tailscale.
2. **R31.11.4U** targeted scanner and fixture QA at `35dbc930c04faccd42777b12076fd764211e5910`. Earlier different-commit scanner failures must still be reconciled for any matching affected source.
3. **R31.14** verified three exact-blob synthetic/design packages (synthetic loopback mTLS R31.11.4J, DNS dossier R31.11.4O, PKI design R31.11.4P), no live TLS or domain ownership certification.
4. **Invoice UI v2 draft PR #227**: combined QA 140/140 at `84260273ae06ec080d1748e2f6a902e9d47ce1df`. Does NOT approve historical GST allocation policy, live financial writes, issue corrections or production usage.
5. **QA policy draft PR #229**: 13/13 targeted QA and 123/123 combined at `5b8e5aa03fde0694abe5e76647250a972c623aba`. Draft and not merged.

**Testing rule**: unchanged source + same workflow SHA + tested scope => reuse; new private-origin/entrypoint/gate files => only new dedicated private multi-site offline tests. No automatic whole-repo combined QA rerun. Production security tests always require real authorized evidence.

## Actual source configuration prepared (disabled by default)

- `staging/private_multisite/private_origin.py` validates `SBI_PRIVATE_ACCESS_MODE=tailnet-staff-only-v1` and `SBI_PRIVATE_TAILNET_ORIGIN=https://<approved-machine>.<approved-tailnet>.ts.net` as a canonical exact HTTPS origin. It refuses wildcard, public sslip, ports, HTTP, and malformed Host/Origin values.
- `staging/private_multisite/private_entrypoint.py` is the ONLY opt-in WSGI adapter. It **replaces** the legacy Cloud Run and sslip CSRF origins and sets Flask 3.1 `TRUSTED_HOSTS` to the exact private host. It intentionally refuses startup when mode/origin are not both configured.
- `staging/private_multisite/Dockerfile.private_multisite_review` is a **separate candidate**. The original AWS Caddy and Dockerfiles are not edited. The container exposes an internal port only; future host-binding must use `127.0.0.1:18181:8080` or a reviewed equivalent, never `0.0.0.0` or public IPv6.
- App origin logic **does not prove tailnet network admission**. Tailnet grants and Lightsail firewall are independent and mandatory. No ordinary employee may join with unrestricted access to Docker/SSH/Postgres.

**Firebase note**: The current `dashboard_source/login.js` uses Firebase email/password via Identity Toolkit and sends an ID token to the same-origin backend; it does not require OAuth redirect login for the existing path. Browser session cookie security, Origin/CSRF, staff authorization and any required Firebase authorized-domain configuration **must still be tested** at the actual private hostname. Do not weaken `__Host-` Secure cookies or add wildcard CORS.

## Scope of required fresh QA (NO commands yet to change AWS)

1. Authorize and document the private-only access change. Select accountable tailnet admin and secondary security reviewer. Approve user/device enrollment, offboarding and rollback process.
2. Inventory current AWS public routes, Docker port publishing, OS/Lightsail IPv4 and IPv6 firewalls, and Tailscale status **read-only**, without printing credentials, DNS zone ownership, users, network topology details or sensitive records.
3. Provision a test-only tailnet machine and two approved staff devices in a separate change, restricted policy, no public Funnel; validate private HTTPS and exact host/origin login in a test sandbox.
4. Perform independent private remote E2E tests across at least two sites, including wrong-user/role, expired/revoked device and session, no route to PG/finance Apply, request spoofing, and safe logged denial.
5. After access and rollback pass, independently authorize public ingress reduction on both IPv4/IPv6; prove direct internet cannot reach the login/API, including formerly public sslip URL. Keep isolated break-glass access.
6. Verify backup/restore readiness, source-financial parity, GST/credit-note approval, and actual release gate. Only an independently approved transaction-release process can unlock financial Apply; this PR cannot.

Reference provider docs (these are documentation references, not completed implementation):
- https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team
- https://tailscale.com/docs/features/magicdns
- https://tailscale.com/docs/features/access-control/grants
- https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html

## Private review evidence outputs

Static only:
```bash
python3 -B staging/private_multisite/private_qa_preflight.py
python3 -B -m unittest discover -s staging/private_multisite -p 'test_private_multisite.py' -v
```

Expected:
```text
SBI_PRIVATE_MULTISITE_SOURCE_POLICY=PASS
SBI_PRIVATE_PROPOSED_RELEASE_GATES=7
SBI_PRIVATE_APPROVED_GATES=0
SBI_PRIVATE_TAILNET=NOT_PROVISIONED
SBI_PRIVATE_PUBLIC_IPV4_IPV6_SHUTDOWN=NOT_VERIFIED
SBI_PREVIOUS_EXTERNAL_MTLS=0_OF_22_EXECUTED_NOT_WAIVED
SBI_FINANCIAL_APPLY=LOCKED
SBI_PRODUCTION_RELEASE=BLOCKED
```

No private business data, DNS secrets, session tokens or raw AWS credentials should be committed to GitHub, CI logs or chat. **Status until actual independent acceptance: PRIVATE SOURCE DESIGN COMPLETE, PRIVATE NETWORK NOT DEPLOYED, FINANCIAL APPLY LOCKED, PRODUCTION RELEASE BLOCKED.**
