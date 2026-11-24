# SBI R13 — Combined Authentication, Payment Evidence and Staging QA
**Date:** 24 November 2026 (IST). **Scope:** GitHub-hosted synthetic/offline tests; no AWS build or real Firebase API access from GitHub.

## Prior real Firebase evidence (provided by owner)
On the separately configured Firebase project `sbi-r9-staging`, the owner reported:
```
R12_REAL_LOGIN=PASS
R12_SIGNED_TOKEN=PASS
R12_ISSUER_AND_AUDIENCE=PASS
R12_FINANCIAL_APPLY=LOCKED
```
The owner used a disposable testing user and Cloud Shell. This is valid user-supplied result evidence, **not** a real-project credential, token or identity accessible to GitHub Actions. The Firebase test password, API key, ID token and account records are not stored in GitHub.

## R13 combined regression job
- Execute **23** R9 real-project configuration refusal checks, all offline.
- Execute **14** R11 keyless real Firebase read-only API checks, all mocked, without contacting Firebase.
- Execute **20** R8 staging runtime and inherited-role isolation tests.
- Execute **19** existing payment-evidence upload/reconciliation readiness/Flask regression checks.
- Execute **13** R7/R8 Firebase Auth Emulator tests using local disposable test identities and sessions.
- Total **89** distinct Python tests, plus one SHA-verified staging-only Docker image build; one `--network none` nonroot readonly 384 MiB container verifies health and reconciliation/Apply denial; automated rollback and container cleanup.
- Use one GitHub-hosted runner. Do not run on the 1 GB AWS Lightsail server.

## Limitations / pending gates
1. **R12 real signed-token pass is historical user-provided evidence**, not repeated inside GitHub; the real Firebase project and API keys are never connected to Actions.
2. The SBI backend's **real** session cookie issuance, access claims, CSRF and disabled-user enforcement have been integration-tested with the Firebase Auth **Emulator**, but not with a real staging-signed ID token and Cloud Shell service-account runtime.
3. The real-app verified session integration requires a separately authorized restricted staging runtime and independently reviewed end-to-end test.
4. No AWS application deployment, production `main` merge, invoice database update or financial engine/writer authorization. Financial Apply stays **LOCKED**. Original upload intake cutoff remains `2026-11-23T00:00:00+05:30`.
5. Human security signoff and actual AWS canary remain outstanding.

**Acceptance criterion:** 89/89 source tests and Docker canary must succeed; do not call this financial-production or live-signed-token session QA. Keep [Issue #148](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/148) open for real authenticated staging-app session and security review.
