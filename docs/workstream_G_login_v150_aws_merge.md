# G — Login v150 to AWS Preview UI merge

Status: SOURCE_RECOVERY_REQUIRED — implementation not yet merged.
Branch: `feature/g-ui-login-v150-aws-preview`
Source: https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app/
Target: https://sbi-preview.13-232-241-221.sslip.io/

## Immutable boundaries
- Merge login presentation and compatible authenticated navigation only; do not copy cloud service-account credentials, tokens, cookies, or backend secrets.
- AWS must validate identity server-side; neither the Origin header nor `X-DIL-Upload` may authorize access on its own.
- Keep AWS preview private until authentication tests pass.
- No financial database reads/writes, upload apply, reconciliation executions, or production deployment as part of this UI integration.
- Keep existing report header schema at 53 columns and preserve the existing reports/API contracts.
- Maintain an independently revertible commit for all UI changes.

## Known repository entrypoints (observed on main)
- `dashboard_source/index.html`: existing dashboard UI, Reports and Database Update navigation.
- `dashboard_source/production_gateway.py`: Flask route for index, API gateway, and upload origin checks.
- Gateway contains a reference to the Google Cloud login-v150 domain; this is NOT evidence of a login UI merge.

## Required source recovery (read-only)
1. Identify the Cloud Run revision `login-v150` and its source/image digest using authorized Google Cloud access.
2. Identify AWS preview's deployed container image digest, compose configuration, and source commit.
3. Acquire the matching v150 HTML, CSS, JS and authentication contracts from the *source repository* or authorized artifact, not from credentials or protected sessions.
4. Compare page routes, asset paths, login/logout flows, CSRF/session handling, and Firebase/IAP assumptions.
5. Make a UI-only patch on this branch; keep the existing AWS authentication backend until its contract can be verified.

## Release QA gates
- Source traceability (Cloud Run revision and AWS image digest)
- Existing AWS protected endpoints remain 401/403 to anonymous callers
- Successful authenticated login, logout, expired/invalid/revoked session denial
- Unauthorized report, upload, update, admin, and assistant API requests denied
- Navigation, responsive layout, keyboard accessibility and asset loading
- Existing report CSV header parity: exactly the approved 53 fields, in order
- 0 financial database writes during tests; non-production integration environment
- Combined regression QA passes and results recorded
- Explicit owner approval required for deployment and any financial writes

## Operational state
- Branch creation: complete.
- v150 authenticated source retrieval: pending.
- AWS preview image/source mapping: pending.
- UI merge: pending.
- QA: not executed.
- Deployment: not authorized.
