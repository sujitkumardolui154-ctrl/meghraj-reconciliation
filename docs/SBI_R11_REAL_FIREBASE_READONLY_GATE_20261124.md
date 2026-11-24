# SBI R11 — Real Firebase Authentication API read-only authorization check (24 November 2026 IST)

## Grounded progress from Google Cloud Shell
Owner's screenshot showed `R9_KEYLESS_IMPERSONATION=PASS` for service account `sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com` in project `sbi-r9-staging`. This verifies temporary impersonated credentials, **not** Firebase user/session verification.

## Safe next stage
First confirm that the temporary identity can perform one **real Firebase Authentication read-only** request. The official Identity Toolkit method `GET /v1/projects/{targetProjectId}/accounts:batchGet?maxResults=1` needs `firebaseauth.users.get`. This tests project scoping and authentication permissions; it never creates, deletes or changes Firebase users. The Python probe reads the result but prints neither user data nor access tokens.

### Files
- `scripts/ci/sbi_r11_firebase_keyless_readonly_probe.py`: read-only opt-in probe, no third-party Python package requirement, uses Cloud Shell's pre-authorized `gcloud` CLI with explicit impersonation. Runs **only when manually approved** in the separate Cloud Shell, never in CI or on Lightsail.
- `tests/test_sbi_r11_firebase_keyless_readonly.py`: 14 offline-only unit/refusal tests including optimized Python, mocked API success and 403, no token/user leakage.
- `.github/workflows/sbi-r11-firebase-keyless-readonly-preflight.yml`: runs offline tests only.

### Execution boundary
Required explicit environment gate: `SBI_R11_READONLY_FIREBASE=SBI_R11_READ_ONLY_STAGING_FIREBASE_APPROVED`. Active gcloud project must be exactly `sbi-r9-staging`. QA service account is hardcoded to `sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com`.

Rejects an Auth emulator, `GOOGLE_APPLICATION_CREDENTIALS` files, inherited production Google project, evidence/database paths or R9's user-creating real-token probe gate. The R11 check calls only a single Firebase REST **GET**, with a temporary impersonated OAuth credential held in memory, and logs only status markers.

**Security note:** The QA account currently has `roles/firebaseauth.admin` (read/write). The source script does not exercise write privileges. Reduce/revoke temporary role and impersonation grant after QA; avoid exposing any account data. No GitHub Actions Firebase API calls, no Firebase Hosting, no AWS/Caddy changes, no production `main` merge, no financial writes or Apply activation.

### Interpretation
- `R11_REAL_FIREBASE_AUTH_API=PASS_READONLY` proves real Firebase Admin API **read access** using keyless impersonation.
- It is **not** proof that a real end-user Firebase ID token was issued or that its session cookie/CSRF/claim revocation is correct; R9 signed-token acceptance remains separately gated.
- The actual Cloud Shell test is still **NOT EXECUTED** until the user runs the explicit read-only probe. CI testing this source is not live Firebase testing.
- Financial Apply stays **LOCKED**; original upload intake cutoff remains `2026-11-23T00:00:00+05:30`.

References: https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/projects.accounts/batchGet and https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation
