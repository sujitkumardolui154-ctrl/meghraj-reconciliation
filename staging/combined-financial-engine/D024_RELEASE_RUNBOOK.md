# D-024 — Logic-only candidate package (owner's protected deployment path)
Date: 2026-11-20 · Workstream D

**Purpose:** Resume release preparation without processing any previous financial data.

## Source package scope
The `logic_only_package.py` builder takes an explicit 14-file allowlist of approved invoice layout validation, payment-value classification, 53/35-column credit-note reporting, GST v2.7 alias+invoice review, D-022/D-023 reference calculations, readiness/policy gates and a synthetic-only CLI probe. It packages code and public header/rule configuration only. No `.xlsx`, `.csv`, payment receipts, historical invoice source, private branch master, ledger, service account, authentication configuration or financial database drivers are included. Archive members are fixed, SHA256-listed and reproducibly packaged.

The CLI `synthetic_only_probe.py` accepts only `--status` or `--synthetic-selftest`, and has no file/path/URL input, HTTP listener, upload endpoint, database connections or financial writes. It intentionally **does not provide the canonical SOL waterfall payment allocator**; finance release gate remains blocked. Package manifest explicitly marks `canonical_allocator_certified=false`.

## Staging release steps

1. PR #116 has merged D-022 source review. PR #117 has D-023 reference math and owner logic-only restrictions, still pending review.
2. D-024 source PR stacks on PR #117; GitHub Actions runs preexisting and new **synthetic-only** contract tests, static import exclusions, reproducible archive tests and the isolated synthetic smoke probe.
3. CI saves the `sbi-d024-logic-only-candidate` artifact for 7 days, containing source code and a non-sensitive bundle manifest only. No action deploys to AWS, changes Firebase, accesses previous financial records or writes a financial database.
4. Before any isolated AWS dry-run of this candidate, a separate host-level preflight must certify: network disabled, no prior finance mounts/environment secrets, non-root + read-only filesystem, no production network/ports, no old-data job scheduling, no change to running services, and verified cleanup. It may run *only* `--status` or `--synthetic-selftest`; don't call other processes.
5. **Complete engine still blocked:** the full canonical allocator and controlled new-payment-evidence intake are not present/certified. Do not rebrand this package as a complete engine or promote it to production. Finish approved logic modules with synthetic cases and separately authorize deployment of those modules without ever calculating earlier financial records.

## Owner's immutable restriction
- Do not calculate, recalculate, inspect financial values, compare, reconcile, replay, migrate, or modify earlier/historical invoices, payments, Credit Notes, GST or allocations.
- Test exclusively with generated synthetic data and source-level contract checks.
- A future new-evidence intake must require intentional submission and independent review; no old-data scanning or implicit backfill.
- Current report dashboards, authenticated routes, Caddy configuration, AWS containers, source financial records and allocations remain untouched.

**D024_PACKAGE=SOURCE_ONLY; SYNTHETIC_QA=REQUIRED; FULL_ALLOCATOR=NOT_CERTIFIED; HISTORICAL_DATA=NOT_ACCESSED_BY_PACKAGE; AWS_DEPLOYMENT=NOT_PERFORMED; PRODUCTION_RELEASE=BLOCKED.**
