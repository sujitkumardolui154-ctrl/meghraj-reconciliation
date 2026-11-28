# R31 — QA PostgreSQL RLS Catalog PASS (Operator-Reported)
Date: 2026-11-28

Exact application target remains `https://sbi-preview.13-232-241-221.sslip.io/login`.

Original R31 tenant catalog source: `f99df275164a8cd21e05fbc0f89932828ed6759f`.
The test fixture bug (`invoker_view` was not actually mutated) was fixed on the same development branch, with the correction recorded in `R31_RLS_UNIT_TEST_FIX_20261128.md`.
Corrected source SHA executed by the operator: `97dd13dddef9534aa306e18e760579c6d12d22d2`.

## Reported AWS results — only the observed scope
```text
Ran 6 tests in 0.001s
OK
R31_RLS_TARGETED_UNIT_TESTS=PASS
R31_RLS_SOURCE_AND_EXISTING_URL=PASS_PINNED
R31_RLS_PRIVATE_QA_POSTGRES=PASS_ISOLATED_UNPUBLISHED
R31_RLS_QA_ROLE_MAPPING_POLICIES=PASS_RESTRICTED_CATALOG_ONLY
R31_RLS_QA_DATA=ZERO_ROWS_TWO_MAPPINGS
R31_RLS_PREVIOUS_FIREBASE_TWO_USER_HTTPS=OPERATOR_REPORTED_PASS_SEPARATE_TEST
R31_RLS_SAME_TWO_FIREBASE_USERS_BOUND_TO_DB=NOT_VERIFIED
R31_RLS_CROSS_TENANT_HTTPS_A_TO_B=NOT_TESTED
R31_RLS_CROSS_TENANT_HTTPS_B_TO_A=NOT_TESTED
R31_RLS_SYNTHETIC_ROW_BOUNDARY=HISTORICAL_SCOPE_ONLY_NOT_REPLAYED
R31_RLS_REAL_HTTP_ENDPOINT=NOT_DEPLOYED_OR_PROVEN_BY_THIS_AUDIT
R31_RLS_MODE=READONLY_CATALOG_NO_FINANCIAL_DATA
R31_RLS_FINANCIAL_APPLY=LOCKED
R31_RLS_PRODUCTION_RELEASE=BLOCKED
```

This is a locally executed **read-only catalog test**, and does NOT exercise the production database or the actual restricted PostgreSQL login session over HTTPS. Zero QA rows does not show cross-owner filtering.

Owner identity matching requires verifying that the specific two accounts used in the HTTPS QA correspond to the existing privately stored Firebase Admin and PostgreSQL role records. There are no email addresses, UIDs, tokens, passwords or financial rows in this receipt. Independent release signoff is not provided.

**Next narrow gate:** `verify_firebase_pg_owner_binding_readonly.py` compares the two locally confirmed prior HTTPS test email identities to the protected Admin-SDK verified account records and existing PostgreSQL mapping, without committing or printing account identifiers. The result remains **operator-attested identity correspondence**, not HTTPS A-to-B/B-to-A row-level acceptance.

`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
