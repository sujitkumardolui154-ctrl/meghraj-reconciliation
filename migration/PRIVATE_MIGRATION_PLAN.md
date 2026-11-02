# SBI Reconciliation — Private hosting migration plan

Status: PREPARATION ONLY. This repository is PUBLIC and contains partial code. Never commit real invoices, payment files, Firestore exports, credentials, signed URLs, secrets, or private audit reports.

## Target
New PRIVATE GitHub repository, Railway-hosted UI/API, isolated test database, GitHub Actions CI. Spending target ₹500–₹1,500/month is a target, not a guaranteed cap. Keep Google Cloud production unchanged.

## Source inventory required (Cloud Shell or recovered archive)
- dashboard_source: Flask gateway, templates, JS, dependencies, startup command
- backend_source and source: financial engine, report API, imports, schema, rulebook
- tests and staging_candidates: independent QA and deployment logic
- current Cloud Run image digests/configuration, excluding secret values
- approved 53-column data contract and approved header mapping
- original baseline provenance, dataset SHA, Firestore export metadata

## Mandatory isolation
1. Create private repo and inspect visibility before any transfer.
2. Build sanitized source bundle only; allowlist paths after auditing contents.
3. Scan file contents AND git history for secrets; remove and rotate leaked credentials.
4. Keep SBI invoice/payment data and Firestore backups OUT OF GIT.
5. Use synthetic fixtures for CI; disable external network and financial writes in tests.
6. Mark finances REVIEW_REQUIRED until independent baseline/exception QA passes.
7. Deploy privately with immutable image, nonproduction DB, least-privilege identity.
8. Verify authenticated HTTP isolation, backups, restore rehearsal and rollback.
9. Only later consider DNS/production cutover after signed go/no-go.
## Known blockers
- Private destination repository not yet created.
- Complete Cloud Shell local files not available through GitHub.
- Authenticated final-container security QA outstanding.
- 9 duplicate-or-missing keys, 4 GST arithmetic mismatches, 5 Credit Note conflict groups unresolved.
- Original baseline authentication, full engine regression and rollback proof outstanding.
- Existing public repo readme says backend/database source is not present.

## Exit criteria for this preparation
A private destination exists; a reviewed source manifest and content secret scan pass; a synthetic CI pipeline is green; separate staging service can be deployed without any connection to Google Cloud production.
