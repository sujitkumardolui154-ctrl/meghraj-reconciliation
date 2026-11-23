# SBI R7 — Firebase Authentication Emulator and Payment Evidence QA
**Date:** 23 November 2026 (IST). **Development-only; no AWS, Firebase production, or financial writes.**

## Test strategy
- Use the official disposable Firebase **Auth Emulator** bound to localhost 127.0.0.1:9099, with project ID `demo-sbi-r7`.
- The app's existing `dashboard_sessions` functions and Firebase Admin SDK run against locally issued ID and session cookies, **without monkeypatching Firebase token verification**.
- CI explicitly denies `GOOGLE_APPLICATION_CREDENTIALS`, requires exact demo project and emulator hostname, uses fictitious users `@example.invalid`, fake SOL `07001` and temporary mode-0700 evidence storage.
- Test password-based session creation, secure cookies, dashboard claims, disallowed users, invalid ID/session cookies, CSRF, uploading a synthetic workbook, receipt preflight, duplicate detection, cross-identity access denial and locked financial POST endpoints.
- Retain existing 19 mocked Flask regression tests separately.
- The Auth Emulator is a **simulator**, not the real Firebase production authentication service. The full live sign-in, browser redirects, production token/cookie signature verification, Firebase revocation behavior, real SBI source and financial ledger parity remain unverified.

## Security guardrails
The 23/11/2026 00:00 IST cutoff is an upload receipt boundary, not bank-transaction proof. No production credentials, live bank files, AWS public routing, external port publishing, financial writer or Apply operation. GitHub Actions is read-only at repository scope and creates no cloud service. The auth emulator starts and stops during the CI job.

## Release decision
A green R7 Auth Emulator run supports the development integration only. It is not approval to merge production, deploy AWS, or unlock Financial Apply. Human security review and an separately owner-approved real Firebase test environment remain required.
