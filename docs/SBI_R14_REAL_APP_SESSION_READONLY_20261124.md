# R14 — REAL Firebase ID Token → SBI Flask Session (read-only) | 24 Nov 2026

## State
Development-only review artifact. The existing R12 owner-reported Cloud Shell proof shows real staging Firebase password sign-in, cryptographic signature, issuer and audience PASS. R13 89/89 offline/emulator tests PASS; **neither proves that a real signed token is accepted by the actual SBI Flask session**.

This R14 manual harness is deliberately **not run by CI**, Cloud Run or AWS. Only 12 offline guard tests execute on GitHub. It does not edit production main, AWS routing, Firebase users/claims or financial records. Financial Apply remains LOCKED.

## Source
- `scripts/ci/sbi_r14_real_app_session_readonly.py`
- `tests/test_sbi_r14_real_app_session_readonly.py`
- `.github/workflows/sbi-r14-real-session-source-guards.yml`

## Prerequisites / explicit external authorization
1. Run only inside authorized Google Cloud Shell for **separate** project `sbi-r9-staging`, not production and not a public AWS instance. Use source from the approved review commit.
2. The existing, disposable `sbi-r9-test01@example.com` account must be enabled with an **already-approved** `dil_dashboard: true` custom claim. The harness **will not add it**.
3. Google Application Default Credentials (ADC) must resolve to the project `sbi-r9-staging` **and** service-account identity `sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com`. **gcloud CLI impersonation alone is insufficient.** Do not use JSON keys, copy access tokens or expand privileges silently.
4. QA account needs Firebase Auth user read permission and ability to create a session cookie with staging-only IAM signing credentials. Revoke temporary privileged access after independent approval and checks. Do not reuse production service accounts.
5. An owner-approved synthetic-only SOL quarantine key list must exist; this is a startup safeguard and **no evidence is uploaded**. No financial DB or production payment path may be present.
6. `python -m pip install -r staging/aws_login_v150/requirements.txt` and project CLI setup must be completed on the isolated Cloud Shell.
7. Never paste passwords, Web API keys, tokens, ADC files or private data into chat, GitHub, logs or screenshots.

### Explicit manual invocation (Cloud Shell only)

```bash
cd ~/meghraj-reconciliation
git fetch origin review/sbi-r14-real-firebase-app-session-readonly-20261124
git switch --detach FETCH_HEAD
export GCLOUD_PROJECT=sbi-r9-staging
export SBI_R14_REAL_APP_SESSION=R14_REAL_STAGING_APP_SESSION_READONLY
# Supply only APPROVED synthetic quarantine SOL key(s) privately; no real SBI SOLs.
read -r -s -p "Approved synthetic SOL key(s): " SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS; echo
export SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS
python scripts/ci/sbi_r14_real_app_session_readonly.py
unset SBI_R14_REAL_APP_SESSION SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS
```

The program prompts securely for the staging Web API key and disposable QA account password (hidden terminal input). They are not persisted. If ADC is absent/mismatched or the preapproved test user lacks the dashboard claim, expect a **BLOCKED** result; do not bypass safety gates or elevate user privileges merely to satisfy a test.

The harness uses Flask's in-process `test_client`, with a synthetic `https://sbi-r9-staging-local.invalid` origin for session/CSRF logic. This is **not** external HTTPS/DNS or AWS canary testing. The script signs in to real Firebase, verifies the ID token through Firebase Admin, checks application CSRF refusal, issues a session cookie through the actual app, reads `/auth/me` and protected reconciliation status, and checks Financial Apply refusal. It does **not** call Firebase logout because that revokes tokens.

### Expected markers ONLY on real success
```text
R14_REAL_ID_TO_FLASK_SESSION=PASS
R14_SESSION_COOKIE_CSRF_ORIGIN=PASS
R14_SESSION_PROTECTED_STATUS=PASS
R14_FINANCIAL_APPLY=LOCKED
R14_AWS_HTTP_DEPLOYMENT=NOT_TESTED
R14_ROLE_REVOCATION_AND_OWNER_ISOLATION=NOT_TESTED
R14_FIREBASE_USERS_AND_FINANCIAL_WRITES=NONE
```

**Incomplete independent gates:** live application identity revocation and cross-account isolation; human security review; AWS staging HTTPS canary; authoritative Invoice Details. and PAYMNENT source ingest; v2.51 calculation and version parity; PostgreSQL transaction and Excel writer integration. Preserve all finance locks.
