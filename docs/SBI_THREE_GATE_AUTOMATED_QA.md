# SBI automated three-gate QA — private, read-only, fail-closed

This system produces QA evidence, **not** financial-release authorization. It never writes invoice or bank records, grants permissions, performs settlement, or deploys services.

## Automated execution

- Scheduled daily at 02:23 UTC after this workflow is merged to the default branch: synthetic auth/financial source-contract tests on a hosted GitHub runner. Every synthetic run explicitly leaves real Firebase login, live database parity, and bank-reconciliation correctness **NOT_VERIFIED**.
- A separate private live job can run manually, or daily when repository variable `SBI_PRIVATE_QA_ENABLED=true` is configured. It uses **only** a protected self-hosted runner labeled `sbi-private-financial-qa`.
- Production cutover remains `BLOCKED` in both modes. Synthetic PASS must not be treated as evidence of real finance readiness.

## Required protected private-runner setup

1. Create a protected GitHub environment `sbi-private-financial-qa` and authorize a dedicated, non-admin Firebase QA account with the necessary dashboard-viewer role. Do not use the real owner's account.
2. Install a private runner and install Python 3 and `google-cloud-firestore`. Provide narrowly scoped Firestore **read-only** credentials through approved application default credentials (no finance writer or Cloud Run deployer role).
3. Store the independently approved 53-column original source CSV and the 53-column exported reports **only on this private runner**. Approve the source and report SHA256 values independently of their fetched contents.
4. Set GitHub protected environment secrets `SBI_QA_FIREBASE_API_KEY`, `SBI_QA_FIREBASE_EMAIL`, `SBI_QA_FIREBASE_PASSWORD`.
5. Set protected environment variables `SBI_PRIVATE_QA_APPROVED=true`, `SBI_QA_TEST_ACCOUNT_ISOLATED=true`, `SBI_QA_READONLY_IDENTITY_CONFIRMED=true`, `SBI_QA_DASHBOARD_URL` (one of the explicitly allowed project dashboard hosts), `SBI_QA_SOURCE_CSV_PATH`, `SBI_QA_APPROVED_SOURCE_SHA256`, `SBI_QA_DATASET_ID` (<approved SHA>-report-v1), `SBI_QA_REPORT_MANIFEST_PATH`.
6. For scheduled private execution only, set repository variable `SBI_PRIVATE_QA_ENABLED=true` **after** the private reader credentials, data provenance, and isolated QA identity are independently approved. Otherwise, the live job is skipped.

## Live checks

- **Firebase:** real email/password sign-in via Firebase Identity Toolkit, ID-token lookup, dashboard CSRF/session validation and `/auth/me` identity comparison; **does not** use a synthetic mock for a real PASS.
- **Firestore:** read-only page retrieval of baseline `dashboard_report_datasets/{approved-source-sha}-report-v1/rows`. Exact 53-column string values, row positions, count, source hash, and header order must match an independently hashed local original CSV. Imported rows cause a blocked result requiring separate import-parity testing.
- **Financial reports:** reuse `tools/sbi_financial_report_parity.py` to compare independently hashed local exports `unpaid`, `ok`, `error-value` and optional `balance-review` against original values. Fail on GST inconsistencies, missing rows and duplicates until reviewed. **Bank-payment settlement and reconciliation allocation parity are NOT verified** by this evaluator, even when source/report partition checks pass.

Report manifest example stored on private runner (never committed):
```json
{"reports":{"unpaid":{"path":"/private/unpaid.csv","sha256":"<approved-64-hex>"},"ok":{"path":"/private/ok.csv","sha256":"<approved-64-hex>"},"error-value":{"path":"/private/error-value.csv","sha256":"<approved-64-hex>"}}}
```

## Safety and current limitations

- Do **not** store private bank/invoice rows, passwords, Firebase ID tokens, service account keys, or signed links in GitHub repositories, runner logs, artifacts, or this chat.
- This automated QA has not been authenticated against live Firebase or live Firestore merely because the source workflow exists. The private runner, independent evidence and authorized credentials must be configured first.
- Even a successful real Firebase login and exact Firestore baseline parity do not demonstrate complete bank settlement correctness, actual reconciliation values, production rollback readiness, or a deployable release.
- The private job deliberately fails with `REVIEW_REQUIRED` while independent bank/reconciliation validation is unresolved; no traffic or financial changes should be linked to its result.
