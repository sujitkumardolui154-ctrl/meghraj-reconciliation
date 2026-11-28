# R31 — Existing-URL RLS Route Metadata AWS Receipt (Operator-Reported)

Date: 2026-11-28
Source/target: existing SBI Lightsail login at `https://sbi-preview.13-232-241-221.sslip.io/login`
Classification: read-only operator-reported route metadata, **NOT** deployed HTTPS tenant-isolation acceptance.

## Reported result

```text
R31_ROUTE_EXACT_EXISTING_URL=PASS_PINNED
R31_ROUTE_LOGIN_CONTAINER=RUNNING
R31_ROUTE_PRIVATE_STAGING_FLAG=NOT_ENABLED_OR_REVIEW
R31_ROUTE_R3114_FLAG=NOT_ENABLED_OR_REVIEW
R31_ROUTE_CANDIDATE_MODULE=NOT_VERIFIED_IN_RUNNING_IMAGE
R31_ROUTE_ANONYMOUS_HTTPS_STATUS=HTTP_401
R31_ROUTE_ANONYMOUS_STATUS_PROVES_REGISTRATION=NO
R31_ROUTE_REAL_TWO_OWNER_RLS_HTTPS=NOT_TESTED
R31_ROUTE_NEXT_CHANGE=SEPARATE_AUTHORIZED_REVIEW_REQUIRED
R31_ROUTE_FINANCIAL_APPLY=LOCKED
```

This confirms the exact QA flags were **not observed as enabled** in the running Docker container configuration and the specific RLS module path was **not confirmed**. The `HTTP_401` may be issued by the general Firebase middleware before route matching; it does **not** prove the route is registered or that two-owner tenant isolation works.

The user's output did not include `R31_ROUTE_PRODUCTION_RELEASE`; the audited GitHub policy separately requires `PRODUCTION_RELEASE=BLOCKED` and no permission to release is inferred.

## Reusable evidence (do not repeat)
- Real existing-host HTTPS Firebase A/B login and origin/CSRF: operator-reported PASS.
- Protected Firebase user → QA PG role mapping correspondence: operator-attested PASS.
- Dedicated QA PostgreSQL schema, forced-RLS catalog, two roles/two mappings, no QA data and no financial-write privilege: operator-reported PASS.

## Meaning
The **running application's actual HTTPS Firebase-session → dedicated QA PostgreSQL restricted-login path remains unverified/not accepted**. Do not confuse static blueprint source or the private in-process R31.11.4F candidate with this missing external/browser path.

No account, role, schema, network, Caddy, TLS, container or financial configuration was modified in this reported read-only audit.

**FINANCIAL_APPLY=LOCKED. PRODUCTION_RELEASE=BLOCKED.**
