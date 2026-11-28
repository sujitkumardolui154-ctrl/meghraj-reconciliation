# R31 Existing Login Routing & Authentication Verification

**Canonical existing deployment URL:** https://sbi-preview.13-232-241-221.sslip.io/login

This is a targeted, read-only, source-pinned milestone to distinguish the earlier ambiguous Caddy route status from an actual login outage. No new platform, domain, DNS, Caddy edit, container restart, database write, financial Apply or production release.

## Reused validated evidence (no repeat)
- The operator previously observed trusted HTTPS and HTTP 200 for `/login`, unchanged Caddy SHA, running login container candidate and unpublished private QA PostgreSQL.
- The GitHub `staging/aws_login_v150/Caddyfile.workspace` template routes `/login` to `sbi-login-workspace:8080`, but the **running** Caddyfile did not contain the literal pair needed by the earlier checker. Do not invent a broken route. Its live routing may use imports or variable upstream names; the exact handler still needs review.
- `dashboard_source/login.js` performs GET `/auth/config`, GET `/auth/csrf`, Firebase password sign-in, then POST `/auth/session`. This targeted probe **does not** attempt password sign-in or obtain/print API keys or CSRF values.

## New read-only checks
The script tests fixed URL paths using curl with TLS verification enabled, without sending credentials or following redirects. It suppresses response bodies and headers and prints only HTTP response codes, not secrets. It checks the live Caddyfile for an explicit route, the running login container and whether its Docker network intersects with the Caddy network.

- `/login`: expected 200 based on prior result.
- `/login.js`: expected 200 if login assets are served.
- `/auth/config` and `/auth/csrf`: expected successful 2xx if the unauthenticated login setup is available; a status is **not proof of valid JSON or sign-in**.
- `/auth/me`: may return an anonymous denial (401/403) or redirect; interpret according to actual route contract, not as a universal pass or fail.
- Docker common network: shows only network intersection, not that a specific Caddy request reached the correct upstream.
- Real signed Firebase user, independent user B, CSRF, cookie flags, expiry/revocation, cross-owner RLS and external multi-location access require approved **separate real acceptance**.
- Caddy and QA PG, previously passed, are not redundantly re-inspected beyond required route/network questions.

## No false release
All old 22 external mTLS cases remain 0 of 22 tested and not waived; private-only vs publicly reachable access at this existing URL still needs an independently approved network policy. Production financial writes stay locked.

Run in pinned isolated worktree:
`python3 -B -u staging/existing_preview_deployment/verify_login_route_auth_readonly.py --source-sha <pinned sha>`
