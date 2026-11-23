# SBI R10 — Combined GitHub-hosted QA to minimize AWS server load
**Date:** 24 November 2026 IST
**Source baseline:** `2f2df7b233ca7edd5bd9a8f8e46a600d4549fc37` (R9 real staging project binding, development branch).

## Owner's result
Cloud Shell screenshot confirmed that `gcloud auth print-access-token --impersonate-service-account=sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com` succeeded and printed `R9_KEYLESS_IMPERSONATION=PASS` **without displaying a token**. This verifies short-lived Google IAM impersonation capability, *not* an actual Firebase ID/session-cookie test.

## Combined offline suite
Run once in a single GitHub-hosted Ubuntu job; install Python/Node dependencies once:
- **23** R9 real-project preflight/identity refuse tests (offline, zero real Firebase API calls).
- **20** R8 staging runtime, source import, inherited master/admin refusal tests.
- **19** preexisting payment evidence/upload, reconciliation readiness and R4 Flask HTTP tests.
- **13** R7/R8 Firebase Authentication Emulator tests with localhost-issued fake tokens/sessions (NOT real signed Firebase tokens).
- **One** isolated R8 staging-only Docker image build with source SHA label, fail-closed default startup, networkless read-only nonroot 384 MiB container, internal HTTP/status/Apply denial and automatic rollback.
- **One** postrun cleanup assertion.

**Expected 75 distinct Python tests**, plus one Docker canary; success is conditioned on every test. GitHub's own runner uses its CPU/RAM; **no builds occur on the 1 GB AWS Lightsail host**.

## Exclusions
R9 Cloud Shell proof only verifies IAM impersonation. It is not yet a real Firebase authentication QA session. Live signed-token testing requires a keyless authorized identity running the R9 probe from a secure Cloud Shell instance, along with the separately scoped Firebase project Web SDK configuration and synthetic-only settings. CI explicitly **never executes** the real Firebase user-creation probe. Also **NOT executed**: AWS Lightsail container deployment/rollback, production Caddy, invoice-payment engine allocation, bank date/UTR or finance writer parity.

## Guardrails
- No production GitHub `main` merge.
- No new AWS RAM/CPU consumption or Docker cleanup on AWS.
- No staging Firebase Cloud API calls from GitHub and no credentials uploaded to GitHub.
- Do not commit service-account keys, Firebase ID tokens, API key environment values or personal financial records.
- `FINANCIAL_APPLY=LOCKED`, no financial database writes; original cutoff `2026-11-23T00:00:00+05:30` unchanged.
- Remaining real Firebase signed-token gate tracked in [issue #148](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/148).

## Evidence
Combined GitHub workflow: `.github/workflows/sbi-r10-combined-offline-qa.yml`. This documentation does not assert CI PASS until run results are independently checked.
