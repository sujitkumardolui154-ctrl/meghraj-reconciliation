# R31 — In-Place Integration Security Review: Existing Lightsail Application

Review date: 2026-11-28
GitHub scope: **Source-only audit and approval design**, not an application patch, IAM grant, Docker deployment, Caddy edit, financial write, or production release.

## Binding owner decision

The only approved browser login target is **https://sbi-preview.13-232-241-221.sslip.io/login**. Preserve the original Lightsail host, original application/platform, existing Caddy and Firebase login. No domain purchase, no `*.ts.net` replacement, no shadow deployment to another platform.

## Evidence reused

- Live HTTPS login: operator-reported certificate trusted, HTTP 200, /auth/config and /auth/csrf HTTP 200; anonymous /auth/me HTTP 401.
- Exact-origin CSRF: empty token HTTP 400, wrong/missing origin HTTP 403; unit tests 7/7.
- Two separate non-admin real Firebase accounts: password sign-in and HTTPS dashboard sessions PASS, secure cookie properties PASS (operator).
- Dedicated private PostgreSQL QA catalog: 6/6 corrected offline tests; isolated/unpublished container, forced RLS, exactly two restricted LOGIN roles and two protected owner mappings, zero QA rows.
- Same two approved Firebase users to PG role mappings: matched by local operator attestation, no emails or UIDs in repo.
- Runtime route check: running login workspace; two private QA flags not observed enabled; R31.11.4 module not confirmed in image; anonymous route HTTP 401 **cannot prove route registration**.

No need to repeat these successful tests for unchanged sources.

## Source review findings

| Finding | Reviewed source | Risk/meaning |
|---|---|---|
| S3-1: existing app is primarily a login/UI shell | `staging/aws_login_v150/app.py` | Financial data source not declared connected; do not claim financial integration acceptance |
| S3-2: private staging flag is **broad** | `app.py` and `r31_stage_blueprint.py` | Registers other QA routes, including POST receipt-sync that writes **isolated QA evidence**; enabling it on existing public-facing login is outside a read-only acceptance |
| S3-3: R31.11.4 blueprint is conditional and not confirmed live | `app.py`, `r31_11_4_runtime_rls_blueprint.py` | Two flags required by source; AWS container flags NOT_ENABLED_OR_REVIEW; standalone QA source is not deployed to existing login image |
| S3-4: R31.11.4 adapter is pinned to isolated QA database | `r31_11_4_runtime_rls_adapter.py` | Explicit QA DB/host, protected owner UID bindings and per-role secret files, fail-closed SQL; no implicit production fallback permitted |
| S3-5: application authentication is reusable | `dashboard_source/dashboard_sessions.py` | Firebase session verified with revocation check; claims and user read; session object populates `g.dil_user` |
| S3-6: Caddy source routes `/api/*` to existing login | `Caddyfile.workspace` | The new route could be publicly network-reachable. Source template != live active Caddy route; restriction/IPv4+IPv6 requires explicit review |
| S3-7: existing private candidate Dockerfile includes RLS modules | `Dockerfile.r31_11_4_private_candidate` | Designed for separate private QA, not proof the existing login image carries `psycopg`, modules, credential mounts, or correct network access |
| S3-8: synthetic rollback fixture did not cross HTTP connection boundary | `r31_11_4d2_rollback_rls_acceptance.sql` | Uncommitted synthetic rows are visible in transaction-local SQL but not to separate HTTPS request connections. HTTP A/B acceptance needs a separately approved, isolated, strictly cleaned test-data lifecycle |
| S3-9: handler's Flask GET may implicitly support HEAD/OPTIONS | `r31_11_4_runtime_rls_blueprint.py` and Flask routing | Negative method tests must explicitly cover POST, PUT, PATCH, DELETE plus HEAD/OPTIONS behavior; do not assume GET-only in literal wire-method sense |
| S3-10: independent revocation/network security remains | Existing design and operator receipts | Browser-login pass and auth-cookie checks alone do not establish revoked-session E2E or private-only internet access |

These findings are **source-level** plus user-provided AWS status. They do not certify the current runtime's complete security or assert that a new route was exposed.

## Proposed minimum safe **in-place** implementation contract (not implemented)

1. **A separate single-route enable gate**, distinct from the legacy `SBI_R31_PRIVATE_STAGING_ENABLED`, must register only the reviewed R31.11.4 read-only handler. It must remain disabled by default and **must not import/register `stage_r31`** or its QA sync/write endpoints on the current public-facing container.
2. **Existing Firebase session chain** must run first, including check-revoked and authorization to a specifically approved QA test cohort. The role lookup uses `g.dil_user.uid` from the verified session, not any request headers or `owner_uid`/role parameters.
3. **Dedicated PostgreSQL QA scope only:** `sbi_r31_11_4_auth_qa_20261126` / `sbi-r3114-private-postgres`; exact protected two-role map, restricted password roles, `SET TRANSACTION READ ONLY`, verified RLS, no privileged fallback or connection to `sbi_reconciliation_main`.
4. **In-place runtime security** must be designed and peer reviewed: existing login image revision and rollback, non-root execution, credentials mounted read-only with exact UID/file modes, minimal internally authorized database network path and **no published PG port**. Do not simply attach the public login container to the isolated QA network without a reviewed firewall/trust-boundary design.
5. **HTTP exposure policy:** The same `sslip.io` URL stays canonical, but if reachable directly from the internet it remains publicly reachable. Security owner must approve office/VPN egress restriction or compensating protection and then independently test IPv4 and IPv6 bypass.
6. **Synthetic owner fixtures:** A DB/security-authorized design must allow separate committed test-only A/B records in the *isolated QA database* for cross-connection visibility, with bounded lifetime, an audit receipt, exact cleanup and post-test zero-row verification. A transaction-local `ROLLBACK` fixture alone cannot prove HTTPS filtering. This test-data authorization is **not granted by this review**.
7. **Rollback:** Record source SHA, deployed image digest, Caddy fingerprint, applied runtime config and allowed method/path list before any change. Validate that staff login and other existing paths still work, and that every financial-write route remains denied after rollback.

## Current go/no-go matrix

| Gate | Result |
|---|---|
| Keep existing `sslip.io/login` and same host | OWNER DECISION RECORDED |
| Reused real Firebase two-user login and mapped PostgreSQL roles | OPERATOR PASS WITH SCOPED EVIDENCE |
| Existing QA PostgreSQL RLS catalog | OPERATOR PASS CATALOG ONLY |
| Review risk of enabling broad private staging flag | **FOUND — DO NOT ENABLE IN PUBLIC LOGIN** |
| Separate single-route source change, review and tests | NOT DEVELOPED OR APPROVED |
| Credential/DB network trust boundary, ingress and rollback | INDEPENDENT APPROVAL PENDING |
| Cross-tenant real HTTPS A→A/B, B→B/A with visible QA fixtures | NOT TESTED |
| Real revoked/expired session acceptance | NOT TESTED |
| Original external mTLS 22 cases or approved equivalent mapping | 0/22, NO WAIVER |
| Financial Apply and production release | **LOCKED / BLOCKED** |

## Source-only focused QA

`r31_inplace_source_security_review.py` checks the tracked code structure, exact URL and preserved locks. Its status `PASS_SCOPE_RISKS_IDENTIFIED_NOT_IMPLEMENTED` would mean the anticipated risk was found in source and the review is internally consistent—not that the future application change is secure, deployed, or authorized. Targeted `test_r31_inplace_source_security_review.py` exercises the checker with changed origin, revoked-cookie check, QA database drift, missing transaction read-only, baseline image contents and release-lock regression.

**Neither command touches AWS, GitHub settings, bank records or PostgreSQL.**

## Next milestone after source-review PASS

Obtain signed scope/architecture and security change approval. Then prepare a separate reviewable **source-only** minimal single-route candidate (with its own unit/integration QA) before contemplating approved same-host rollout and real HTTPS A/B acceptance. No broad flag flip, auto-deployment or default-route change.

`FINANCIAL_APPLY=LOCKED`  
`PRODUCTION_RELEASE=BLOCKED`
