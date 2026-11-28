# R31 — Real Firebase HTTPS Acceptance on Existing SBI Preview

## Correct deployment target

**https://sbi-preview.13-232-241-221.sslip.io/login** is the only intended browser URL. Do not purchase a domain, deploy an alternate platform, replace the hostname with *.ts.net, or modify Caddy in this milestone.

## Previous AWS evidence reused, not rerun

- HTTPS trusted, HTTP 200 login page, existing Caddy baseline unchanged, private unpublished QA Postgres.
- Existing login /auth/config, /auth/csrf, /login.js HTTP 200; unauthenticated /auth/me HTTP 401; existing login service running and shares a Docker network with Caddy.
- Active Caddy literal route still unresolved ("PROXY_PRESENT_ROUTE_NEEDS_REVIEW"), although the application endpoints respond.
- These are availability/read-only findings, **not real authenticated session acceptance**.

## Critical source-level risk

The current tracked \`dashboard_source/dashboard_sessions.py\` defines \`ORIGINS\` with only former Cloud Run hostnames, **not** the selected sslip.io origin. The running AWS revision might differ. Therefore, **do not assume login works** solely because GET /auth/csrf returns 200.

The first check sends a deliberately invalid/empty ID token with the correct existing Origin, a genuine fresh CSRF cookie and matching CSRF header. The expected HTTP status is **400**, proving the Origin/CSRF guard accepted the request but the invalid token was refused. HTTP **403** at this point is a blocker requiring actual live origin/CSRF review; do not auto-edit the production allowlist or weaken CSRF. Wrong and missing origins must both return **403**. This test does not attempt to sign in, creates no Firebase user or financial record, and displays no tokens.

## Pinned, targeted AWS usage

With \`ROOT\` pointing at a dedicated source-pinned clean Git worktree:

Default safe diagnostic:

\`\`\`bash
python3 -B -u "$ROOT/staging/existing_preview_deployment/verify_firebase_https_acceptance.py" --source-sha "$SHA"
\`\`\`

Only if the default diagnostic **PASSes** and an authorized security owner approves two distinct existing non-admin Firebase QA accounts:

\`\`\`bash
python3 -B -u "$ROOT/staging/existing_preview_deployment/verify_firebase_https_acceptance.py" --source-sha "$SHA" --real-users
\`\`\`

Use an actual interactive terminal. Confirm the exact explicit phrase shown at the prompt, then type each QA email and password locally. The script calls the existing Firebase Identity Toolkit password-login endpoint and **current sslip.io** /auth/session, then verifies /auth/me matches the submitted email and returns administrator=false; it also verifies secure, host-only, HttpOnly, SameSite Lax session cookies and distinct Firebase UIDs. It does not print or persist passwords, ID tokens, local UIDs, session cookies, CSRF tokens, public API keys or response data. Sensitive values are used in RAM and discarded with the script process. It does **not** call /auth/logout, which in the tracked implementation revokes refresh tokens.

No master/admin or personal production accounts. If either account is unavailable, leave real QA as NOT_TESTED. Do not create test users or assign claims without independent owner authorization. Cloud authentication may generate identity-provider logs, but this script makes **zero financial or PostgreSQL writes**.

## What passing would and would not establish

- **Preflight PASS**: exact Origin/CSRF contract and denial of wrong/missing Origin with an invalid ID token; no real Firebase login.
- **Real-user PASS**: two distinct nonadmin test Firebase identities can obtain and read separate dashboard HTTPS sessions at the current hostname.
- **Still NOT VERIFIED** even if both pass: cross-tenant PostgreSQL RLS over HTTPS (requires a documented safe read-only endpoint and distinct approved owner mappings), true expired/revoked sessions, compromised/revoked device access, public IPv4/IPv6 denial, firewall configuration, independent deployment authorization, reconciliation financial parity, or production write readiness.

The 22 previous external mTLS acceptance cases remain historically 0/22. The private-only design substitution requires a separate independent security change review at this same URL. Reuse unchanged 4U–4Y QA receipts; this milestone adds only new targeted harness tests.

### Security invariants

\`FINANCIAL_APPLY=LOCKED\`  
\`PRODUCTION_RELEASE=BLOCKED\`  
\`EXISTING_LOGIN_URL=UNCHANGED\`  
\`NO_NEW_PLATFORM=TRUE\`  
\`POSTGRES_FINANCIAL_WRITES=ZERO\`
