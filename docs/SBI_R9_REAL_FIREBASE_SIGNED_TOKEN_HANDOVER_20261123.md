# SBI R9 — Real Signed Firebase Staging Token QA: Prepared, Not Executed
**Date:** 23 November 2026 IST. **Development-only QA artifact.**

## Exact source
- `scripts/ci/sbi_r9_real_staging_signed_token_probe.py` — deliberately **opt-in** executable. It is not called by any CI job or production application entrypoint. It requires `SBI_R9_REAL_STAGING_PROBE=R9_REAL_FIREBASE_STAGING_QA_ONLY` plus `SBI_R8_STAGING_MODE=SBI_R8_STAGING_ONLY_NONFINANCIAL`, an independently supplied `sbi-r8-staging-...` project, separate HTTPS staging origin, staging-only web key, an explicit synthetic SOL review-group list, and an **exactly matching staging-only ADC project and service-account identity**.
- It refuses `FIREBASE_AUTH_EMULATOR_HOST`, `GOOGLE_APPLICATION_CREDENTIALS`, inherited production Firebase API key, financial evidence or workspace paths, and Google project mismatch **before Firebase Admin SDK import**.
- It creates two random fictitious `@example.invalid` Firebase users **only after authorization and ADC project match** in the separate real staging project; signs in through Firebase Identity Toolkit password endpoint to retrieve an actual signed ID token; Admin SDK verifies token audience/issuer, mints session cookie, tests owner-scoped synthetic upload, anti-CSRF/login, duplicate refusal, blocked preflight, cross-user isolation, disabled-user denial and forbidden financial Apply. It deletes created Firebase QA users at the end; cleanup failure fails the run. No actual SBI data, payment matching or invoice posting.
- `tests/test_sbi_r9_real_staging_probe_guards.py` runs **21 offline-only** negative/positive configuration checks, including under optimized Python.
- `.github/workflows/sbi-r9-staging-signed-token-preflight.yml` executes **only** offline guard tests, never calls the real staging probe, and has `permissions: contents: read`.

## Real Firebase staging *not connected*: accepted plan for later execution
1. Use a separately approved Firebase test project matching `sbi-r8-staging-...`. Never reuse `meghraj-reconciliation` or production users.
2. Set dedicated authorized staging HTTPS origin and minimal staging runtime identity via workload/attached identity (not service account JSON committed to GitHub or chat).
3. Provide staging web API key privately and a synthetic-only SOL quarantine list; no financial or SBI customer uploads.
4. Before any live test, review the runtime identity permissions and confirm ADC project ID is the separate staging project. Ensure cost/usage safeguards and cleanup permissions.
5. Run `python scripts/ci/sbi_r9_real_staging_signed_token_probe.py` **only** inside an approved, restricted nonproduction runtime with all strict environment variables and actual staging project bound. Never activate it in GitHub Actions or on the current 1 GB Lightsail production host.
6. Save sanitized pass/fail outcome only; no ID tokens, passwords, session cookies or API keys in logs.
7. An independent human security reviewer must still approve real-project test findings before any release promotion.

## Mandatory limits
- **No cloud project or test users were created by preparing this source.** No authenticated real Firebase token has been verified yet.
- Firebase Auth Emulator results (R7/R8), offline Docker image tests and source-level checks are **not** real signed-token proof.
- The separate project's own IAM/API setup, owner acceptance and connection are still external dependencies, tracked in [issue #148](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/148).
- Do not change AWS/Caddy, GitHub `main`, original financial records, master v2.51/v2.39 approval or the financial writer. Upload cutoff stays `2026-11-23T00:00:00+05:30` (upload time only). **Financial Apply remains LOCKED.**
- Source references: [Firebase Auth REST password endpoint](https://firebase.google.com/docs/reference/rest/auth), [Firebase session cookies](https://firebase.google.com/docs/auth/admin/manage-cookies), [Admin SDK](https://firebase.google.com/docs/admin/setup).
