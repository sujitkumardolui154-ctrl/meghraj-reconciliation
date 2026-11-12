# SBI Credit Note — Batch A2 isolated import-preview integration

**Workstream:** SBI Reconciliation only, WS-LOCK-001.
**Execution classification:** Synthetic/offline QA only. No live financial reads or writes; no merge or deployment.
**Scope:** Incremental future Credit Note uploads, independent of historical Meghraj reference-file row counts.

## Implemented on this isolated branch

- \`backend_source/credit_note_validation.py\`: pure marker, MXP format, duplicate and historical-register error logic.
- \`backend_source/credit_note_import_file.py\`: bounded UTF-8 CSV or XLSX parser; rejects ambiguous/missing required headers, formula/error cells and malformed rows. Outputs formula-safe Error CSV.
- \`backend_source/credit_note_registry_readonly.py\`: Firestore-compatible, **dependency-injected read-only** adapter. Never performs a write. Uses caller-provided database object and explicit registry certification.
- \`backend_source/credit_note_import_preview.py\`: isolated future Credit Note preview and existing-invoice workbook annotation. No route registered. Authentication is mandatory at the application router before this helper can be invoked.
- \`backend_source/invoice_import_preview.py\`: adds Credit Note narration counts without modifying original invoice acceptance or duplicate rejection decisions.

No existing invoice import writer, financial ledger, reconciliation allocation, Cloud Run deployment, AWS running container, or production database was modified.

## Approved business behavior

1. Accept plain \`CREDIT NOTE\` and a valid optional date (\`Credit Note @ 30/11/2024\`, \`Credit Note @ April 2026\`). Malformed dates or spelling variants require review.
2. Count **each affected row** under Error for duplicate Invoice No, duplicate Credit Note No, invalid/non-MXP numbers, and duplicate replacement invoice references. Retain source row identifiers. Do not silently delete rows.
3. Keep the actual **Credit Note Number** distinct from original Invoice No and "New Invoice Against Credit Note". New CN imports require a dedicated Credit Note No column. Historical workbooks lacking that column remain reference data only.
4. An existing invoice is an expected reference for a new Credit Note; it is not an attempted re-import of that invoice.
5. Allow new uploads indefinitely; 20,000 rows is an operational cap **per preview**, not a global financial database size limit.
6. A preview can report ERROR, SCREENED_REFERENCE_ONLY or REVIEW_PENDING_REGISTRY; none authorizes persistence or approval.

## Proposed database indexes: NOT CREATED

The adapter expects:

- \`dashboard_invoice_keys_v140\`, field \`invoice_no\`
- \`dashboard_cn_keys_v1\`, field \`credit_note_no\` (**proposed**, not deployed)
- \`dashboard_cn_replacement_keys_v1\`, field \`replacement_invoice_no\` (**proposed**, not deployed)
- \`dashboard_cn_registry_control_v1/read_only\` (**proposed**, not deployed)

Before the adapter can claim registry-readiness, an independent backfill must verify all previously approved invoices, Credit Notes and replacement references; certify canonical uppercase SHA-256 keys and a stable snapshot hash; and record that the backfill is complete. The existing invoice-key collection's historical completeness is **not** established by the current tests. Missing or uncertified control metadata **blocks** readiness.

Even with a certified read-only preview, a later, separately approved writer must enforce atomic uniqueness again in a transaction; a preview cannot prevent concurrent duplicates.

## Explicitly pending

- Authenticated, role-scoped and CSRF-protected HTTP route and Error CSV download integration.
- Original source-file immutability receipts, transaction audit trail, rollback and owner confirmation.
- Certified, complete persistent CN and replacement indexes; authenticated index read tests.
- New payment import and payment-vs-invoice parity.
- Independent original-source financial-value parity; five unresolved historical CN conflicts.
- Live auth E2E, database recovery rehearsal, production approval and deployment.

## Release gate

\`FINANCIAL_WRITES=NOT_PERFORMED\`
\`PRODUCTION_DEPLOYMENT=NOT_PERFORMED\`
\`PRODUCTION_CUTOVER=BLOCKED\`
\`MERGE_TO_MAIN=NOT_PERFORMED\`

The branch-only GitHub Actions workflow runs synthetic tests without Google/AWS credentials and with repository-read permissions only.


## Batch A3: Authenticated staging route and historical identity index preflight (2026-11-12)

The staging-only \`dashboard_source/sbi_cn_staging_preview.py\` provides a **factory**, not an installed route. No application registration has occurred. Registration must be restricted to a separately isolated staging environment after the existing revocation-checked session middleware is installed, using a read-only backend handler and a restricted service account.

- Feature flag \`SBI_CN_STAGING_PREVIEW_ENABLED=true\` is required; disabled by default.
- Requires matching verified Firebase \`uid\`, enabled account, \`dil_dashboard=true\` and explicit \`sbi_credit_note_import_preview=true\` claim.
- Uses the existing \`dashboard_sessions.csrf_valid()\` with its origin and double-submit-CSRF checks, plus \`X-DIL-CN-Preview: 1\`.
- Accepts one authenticated bounded POST file, CSV or XLSX, at \`/staging/credit-note/import-preview\`. \`?format=errors\` returns a no-store Error CSV. No GET or apply route is exposed.
- Returns import_ready=false, database_changed=false and release_status=REVIEW_REQUIRED even for otherwise clean files; no persistent write is possible in the module.
- The live Firebase login, role assignment, HTTP E2E, and service-account isolation have **not** been tested.

The \`backend_source/credit_note_registry_audit.py\` module now produces source identity counts, duplicated-number error groups and candidate key fingerprints from owner-supplied records. It is **read-only** and always reports \`can_certify=false\`, \`certificate_created=false\`. Certification must remain blocked pending original authenticated sources and independently verified invoice/CN/replacement index completeness. Historical duplicate invoice groups require manual review; they are not auto-deduplicated.

**GitHub Actions synthetic QA on the isolated branch:** 18 Credit Note rule tests + 2 invoice-preview compatibility tests + 23 registry/CSV/XLSX tests + 20 staging HTTP/index-preflight tests = **63 / 63 PASS**, without cloud credentials or financial writes. This does not certify live auth, real database integrity, production data parity or deployment.

**Release lock:** No merge to main, no AWS or Google Cloud deployment, no index writes/backfill, no financial writes. Production cutover remains BLOCKED under WS-LOCK-001.
