# SBI R8 — Independent R7 Review & Controlled Firebase Staging Readiness
**Review date:** 23 November 2026 (IST). **Scope:** development-only QA review and prerequisite planning. No live Firebase test project has been accessed or created.

## Current source-specific findings

1. **R7 emulator protections used Python `assert` for mandatory safety checks.** Assertions are disabled by optimized Python (`python -O`). R8 replaces those particular checks with explicit `RuntimeError` failures and adds CI tests that deliberately execute `python -O` under missing emulator, wrong project, and unexpected credentials.
2. **R7 had no post-login disabled-user or role-revocation regression test.** R8 adds emulator-backed tests for user disablement after a session is issued, dashboard claim removal after login, and preflight CSRF enforcement.
3. **Real staging Firebase is not configured.** The actual code sets `dashboard_source/dashboard_sessions.py:PROJECT = "meghraj-reconciliation"` and `staging/aws_login_v150/app.py:SITE_ORIGIN = "https://sbi-preview.13-232-241-221.sslip.io"`. The emulator test temporarily changes the `PROJECT` in its own process. **This is NOT a deployment-safe staging Firebase configuration**. Before a real separate-project trial, a strictly allowlisted staging-only project/origin configuration and IAM/access review must be developed and approved; never set `FIREBASE_AUTH_EMULATOR_HOST` in a live signed-token environment.
4. **R7 Auth Emulator issues unsigned locally trusted test tokens.** The Firebase Admin SDK honors the emulator host environment variable; do not confuse an emulator pass with authentic signed Firebase production tokens or MFA/real browser proof. See https://firebase.google.com/docs/emulator-suite/connect_auth .
5. **No complete v2.51 / Matrix v2.39 signed financial engine is attached.** The authenticated route still returns `503 APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED`. This is an intentional safety lock, not failed authentication.

## Nonproduction Firebase project acceptance plan — NOT AUTHORIZED FOR CLOUD ACTION
- The project owner should designate or approve a **separate Firebase/Google Cloud project ID** specifically for R8 staging; do not use existing `meghraj-reconciliation` production Firebase.
- Use separately permissioned disposable QA accounts, no actual SBI bank data, no customer records, and no production Firebase service-account JSON in repository, CI logs or chats.
- Create isolated staging origin/host and explicitly allowlist it; do not route through the existing SBI preview or change live Caddy.
- Enable only the minimal Email/Password auth testing features, set conservative IAM, quota/usage safeguards and a cleanup plan. Confirm billing implications before project creation.
- Provide an approved secure runtime-identity method for signed token verification. Do **not** add Firebase credentials to the public GitHub repository, commit them to CI or share secrets in chat.
- Validate real signed ID tokens, auth time, session-cookie signature, revocation/disabled-user behavior, anti-CSRF, user isolation, duplicate workbooks, `503` reconciliation preflight and `403` Apply.
- Collect sanitized result codes and reviewer signoff, not tokens, passwords or bank data. Destroy disposable QA accounts after.
- Keep Financial Apply locked and financial database disconnected throughout.

## Release gate status
| Gate | State |
|---|---|
| R7 local Auth Emulator regression | PASSED previously, 10/10 |
| R8 optimized-Python fail-closed emulator guards | CI pending |
| R8 post-login claims and disablement emulator QA | CI pending |
| Signed tokens from **separate real staging Firebase project** | NOT TESTED |
| Independent human security reviewer | NOT SIGNED |
| AWS Lightsail canary | NOT RUN (RAM safety block on current server) |
| Financial database/write activation | **BLOCKED** |

R8 test changes are *only* in test suite, GitHub Actions workflow and documentation. No production Firebase connection, AWS deployment, GitHub `main` merge or financial allocation/write is authorized by this review.
