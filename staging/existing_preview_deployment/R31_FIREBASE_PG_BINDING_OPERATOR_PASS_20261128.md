# R31 Firebase → QA PostgreSQL Owner Mapping: Operator PASS Receipt
Date: 2026-11-28
Approved application URL: https://sbi-preview.13-232-241-221.sslip.io/login
QA scope: isolated PostgreSQL tenant database, read-only mapping comparison

## Operator-reported status
```text
R31_BINDING_APPROVED_FIREBASE_TO_PG=PASS_APPROVED_PAIR_MATCHES_PROTECTED_DB_MAP
R31_BINDING_EMPLOYEE_EMAILS=LOCAL_OPERATOR_ATTESTATION_ONLY
R31_BINDING_LIVE_HTTPS_IDENTITY_TO_DB=NOT_PROVED_BY_THIS_CHECK
R31_BINDING_TWO_WAY_RLS_HTTP=NOT_TESTED
R31_BINDING_NO_DATABASE_CHANGES=PASS_READONLY
R31_BINDING_FINANCIAL_APPLY=LOCKED
R31_BINDING_PRODUCTION_RELEASE=BLOCKED
```

The two non-admin Firebase accounts previously authenticated via the existing HTTPS login were identified locally by the operator and matched against the preapproved Firebase Admin receipt and the two protected PostgreSQL QA role-owner mappings. This is a **local operator attestation**, NOT session-to-database runtime proof or independent review. No bank, invoice, payment, customer, email, UID, token or role password was stored with this receipt.

## Reuse prior evidence; do not repeat
- Two real Firebase sign-in and secure HTTPS session passes: `R31_REAL_FIREBASE_HTTPS_OPERATOR_RECEIPT_20261128.md`.
- PostgreSQL 16 isolated QA role/policy catalog and zero evidence rows: `R31_POSTGRES_RLS_CATALOG_OPERATOR_PASS_20261128.md`.
- R31.11.4F source is a distinct **in-process** test of Firebase→PostgreSQL restricted RLS; it is not a pass for real browser HTTPS A↔B filtering.

## Next pending gate
Actual HTTPS request from employee A must reach an explicitly approved, authenticated GET-only application handler which uses the trusted Firebase UID and restricted PostgreSQL role to access A-only test data; employee B must be independently tested for B-only and cross-owner denials. Prior catalog is empty (0 payment rows), so success on an empty query cannot by itself prove tenant filtering.

Source check in `staging/aws_login_v150/app.py`: existing AWS login shell advertises `financial_data_connected=false`, and the R31.11.4 RLS route is conditional on **two QA-only feature flags**. These are tracked-source facts, not proof of the running container's flags or handler availability. Current live route must first be inspected read-only. Do not enable the QA route, edit Caddy or deploy an alternate hostname merely to get a green test.

R31 external HTTPS/mTLS historical cases remain 0/22; any replacement requires independent security sign-off. Finance/reconciliation/invoice application release and production writes are separately gated.

`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
