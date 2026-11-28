# R31 PostgreSQL Tenant RLS targeted unit-test correction — 2026-11-28

## AWS operator-reported failure (original SHA f99df275164a8cd21e05fbc0f89932828ed6759f)

The six-test offline source test suite returned FAIL (failures=1) at `test_rejects_any_weakened_rls_mapping_or_db_state` for `field='invoker_view'`. The test copied the secure expected catalog and assigned numeric `1` to each field, including `invoker_view` which ALREADY expected `1`. Thus the tested input was unchanged and the real `classify()` function correctly returned `PASS_RESTRICTED_CATALOG_ONLY` despite the test expecting `REVIEW_REQUIRED`.

This is a **test fixture defect**, not evidence that live PostgreSQL RLS was weakened or that tenant isolation was accepted. The shell's `set -e` stopped before the live read-only PostgreSQL catalog audit, so AWS catalog acceptance remained **NOT EXECUTED** at that moment.

## Correction

Adjust the offline test mutation to guarantee that every modified value differs from the secure baseline:
- Strings replaced with a different string.
- Booleans inverted.
- Positive integers decremented by one; zero changed to one.
- Assert the mutated input differs from the baseline before expecting refusal.

No changes to `verify_postgres_tenant_rls_catalog_readonly.py`, the database, schema, roles, policies, Firebase users, Caddy, AWS firewall, finance endpoints, or deployed applications were made as part of this correction.

## Next execution

Run only the corrected offline test suite followed, if PASS, by the previously defined **read-only catalog audit** from a fresh SHA-pinned clean worktree. Do not re-run schema migrations, real Firebase sign-in, 4A–4F provisioning or financial QA. Passing this catalog audit does not prove A/B cross-tenant HTTPS isolation; this remains separately gated.

`FINANCIAL_APPLY=LOCKED`
`PRODUCTION_RELEASE=BLOCKED`
