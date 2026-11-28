# R31 — Existing SSLIP Real Firebase HTTPS QA Receipt (Operator-Reported)

Date: 2026-11-28
Application target: https://sbi-preview.13-232-241-221.sslip.io/login
Acceptance harness source SHA: 9ef8f6c3424711a14bcc820dc95ab945daeb61de
Evidence type: AWS Lightsail terminal output transcribed by operator into the project conversation.
Independent reviewer sign-off: NOT_RECORDED
Secrets and identities: EXCLUDED — no email, password, UID, token, CSRF value, cookie, raw response or bank data.

## Operator-reported PASS results
- R31_FIREBASE_SOURCE_AND_EXISTING_URL=PASS_PINNED
- R31_FIREBASE_EXACT_ORIGIN_EMPTY_TOKEN_HTTP=400
- R31_FIREBASE_WRONG_ORIGIN_HTTP=403
- R31_FIREBASE_MISSING_ORIGIN_HTTP=403
- R31_FIREBASE_HTTPS_ORIGIN_CSRF=PASS_ANONYMOUS_NEGATIVES
- R31_FIREBASE_USER_1_PASSWORD_SIGNIN=PASS
- R31_FIREBASE_USER_1_HTTPS_SESSION=PASS
- R31_FIREBASE_USER_1_SECURE_SESSION_COOKIE=PASS
- R31_FIREBASE_USER_2_PASSWORD_SIGNIN=PASS
- R31_FIREBASE_USER_2_HTTPS_SESSION=PASS
- R31_FIREBASE_USER_2_SECURE_SESSION_COOKIE=PASS
- R31_FIREBASE_TWO_DISTINCT_NONADMIN_USERS=PASS_REAL_HTTPS_AUTH

These operator receipts establish two separate test non-admin accounts successfully signed in to the existing-hostname application via Firebase and obtained recognized dashboard sessions. The script checked identity/cookie properties. They do not prove roles/ownership in PostgreSQL, account revocation or global ingress isolation.

## Explicitly still pending
- R31_FIREBASE_CROSS_TENANT_POSTGRES_RLS=NOT_TESTED
- R31_FIREBASE_EXPIRED_REVOKED_LIVE_SESSIONS=NOT_TESTED
- R31_FIREBASE_NETWORK_PRIVATE_ACCESS=NOT_VERIFIED
- R31_FIREBASE_PRODUCTION_AUTHORIZATION=NOT_GRANTED
- Previously proposed external HTTPS/mTLS real cases: 0/22 executed; no implied waiver.
- FINANCIAL_APPLY=LOCKED
- PRODUCTION_RELEASE=BLOCKED

## Next minimal evidence
First identify the existing HTTPS read-only owner-scoped API or integration path and the two approved PostgreSQL QA owner mappings. Do not invent or deploy an endpoint as a QA prerequisite. Use the existing R31.11.4I / R31.11.4L source and previous synthetic evidence only for their exact tested scope. Any real A-to-B/B-to-A isolation, forbidden finance methods and actual IAM/network security tests require separate independently reviewed runtime evidence.

Do not re-run the already passed real login test without source changes or a specific new security claim that needs retesting.
