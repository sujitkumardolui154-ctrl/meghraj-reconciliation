# SBI R8 — Separate Firebase Staging Launcher & Evidence Gate

**Development-only proposal; not deployed.** User authorized autonomous engineering work but current restrictions remain: no GitHub `main` merge, no AWS service change, no financial database writes, no production Firebase identity/account reconfiguration, and Financial Apply locked.

## Architecture
- Existing application entrypoint: `staging/aws_login_v150/app.py` **unchanged**.
- Optional nonproduction-only entrypoint: `staging/aws_login_v150/r8_staging_entrypoint.py` with WSGI object `app`.
- The separate entrypoint refuses to start until its nonproduction guard and its **distinct** Firebase project, HTTPS origin, API key, private evidence directory and SOL quarantine registry are explicitly configured. It **does not** create a Firebase project, credentials or DNS.
- At import time this separate process overrides only its own `dashboard_sessions.PROJECT`, session `ORIGINS` and `app.SITE_ORIGIN`; the production app process is never modified. It disables inheritance of the original master user identity.
- The dedicated evidence folder must be owned by its process and mode 0700, with an approved staging-specific name under `/tmp`, `/var/lib` or `/srv`. Production storage and workspace environment variables are refused.
- `FIREBASE_AUTH_EMULATOR_HOST` must not be set in a real signed-token staging process; service-account key file paths are refused in favor of separate workload/runtime identity. Any inherited production Google project is refused.

## Required configuration — examples only, NOT real credentials
```text
SBI_R8_STAGING_MODE=SBI_R8_STAGING_ONLY_NONFINANCIAL
SBI_R8_STAGING_FIREBASE_PROJECT_ID=sbi-r8-staging-<unique-id>
SBI_R8_STAGING_SITE_ORIGIN=https://sbi-r8-staging-<unique-host>
SBI_R8_STAGING_FIREBASE_WEB_API_KEY=<test-project-web-key-set-privately>
SBI_R8_STAGING_EVIDENCE_DIR=/var/lib/sbi-r8-staging-<unique-dir>
SBI_READONLY_QUARANTINE_SOL_KEYS=<privately-approved-numeric-keys>
```
No actual Firebase keys, account credentials, live user identities or SBI financial records should be committed in GitHub.

## CI evidence and limitations
- New test file: `tests/test_sbi_r8_staging_runtime.py` with 19 subprocess tests, including valid local startup, blocked production Firebase project, blocked live origin, blocked inherited key/data paths, bad storage permissions, missing quarantine and Python `-O` safeguard.
- Workflow: `.github/workflows/sbi-r8-staging-runtime-qa.yml`.
- Tests exercise only local process initialization and unauthenticated health/denial. **They do NOT contact a real Firebase project or test signed Firebase tokens.**
- Real staging still requires a separately authorized **new** Firebase project, isolated DNS/HTTPS origin, runtime identity, billing/quotas, secure secrets, and human security review. Those are external account actions not automatically performed by this source patch.
- R8 original emulator QA (32/32 tests and three optimized safety checks) already passed.
- Finance routes remain blocked (403), no allocation engine connected, and cutoff remains `2026-11-23T00:00:00+05:30` for upload intake only.

## Release decision
No AWS/Lightsail deployment, no real Firebase test project, no financial Apply. A passing GitHub CI run on this branch permits further **development** review only. Never treat code-startup QA as verified real signed-token authentication or as evidence that actual SBI transactions are new.
