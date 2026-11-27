# 27 November 2026 — Credit Note Historical Invoice Read-Only Source Discovery

**Milestone:** Connect the owner-approved credit-note generator to existing historical invoice records without altering the master database, payment evidence, GST reports, credit-note registry, or reconciliation engine.

**This work is a READ-ONLY DISCOVERY and REVIEW milestone. It is NOT authorization to issue credit notes against historical records.**

## Verified architecture (from repository)

- The credit-note QA generator currently reads exact original invoice facts from `sbi_invoice_gst.invoices`, writing its own append-only QA `credit_notes` and `credit_note_lines` only when the isolated finalize flags and the `invoice_qa` database checks pass.
- Existing selected Bulk Report uses `dashboard_source/aws_verified_invoice_lookup.py` to query a pinned Firestore source:
  - the 14,374-row, 53-column verified baseline;
  - `dashboard_invoice_rows_v140` incremental imports with completed receipts;
  - read-only, exact-number lookup with duplicates, conflicts and incompleteness placed in `review`.
- A previously discussed central PostgreSQL database (`sbi_reconciliation_main`) is not proven to hold the historical row set. The public repository contains no reviewed PostgreSQL relation/column mapping that could be used safely for issuing credit notes.

## Implemented for this milestone

### A. Verified historical evidence — REVIEW ONLY

- `dashboard_source/credit_note_historical_evidence.py` translates existing PR129 53-column invoice report matches into *read-only evidence* for a credit-note lookup.
- It preserves exact Invoice No., source Invoice Date, source Month, source SBI branch name, original SOL and model SOL separately, source GSTIN and amount cells. It raises a review flag when source tax totals, SOLs or customer names conflict.
- A duplicate report match, unverified data type, incomplete result, unavailable authentication, or report error fails closed.
- **Every historic match has `credit_note_eligible: false`**, no computed uncredited balance, and explicitly states that historical credit-note ledger and GST filing coverage are not certified.
- `POST /api/credit-notes/lookup` may expose this review-only evidence for invoice numbers absent from the isolated registry **only when** `SBI_CREDIT_NOTE_HISTORICAL_REPORT_REVIEW=1`. This feature flag is OFF by default.
- `preview` and `finalize` STILL use verified isolated `sbi_invoice_gst.invoices` records. A report-only history match cannot be used to issue or store a credit note.

### B. PostgreSQL main/staging catalog discovery — READ ONLY

- `scripts/sbi_credit_note_history_catalog_preflight.py` accepts an existing private **reporting-role** DSN via `SBI_HISTORY_REPORT_READONLY_DSN`; it does not print the DSN.
- It starts an explicit `BEGIN TRANSACTION READ ONLY`, verifies the database is `sbi_reconciliation_main` or `sbi_reconciliation_staging`, and queries only `information_schema` column metadata for candidate invoice/credit tables.
- Reports relation/column names, whether the role has SELECT/write privileges, expected-field presence, a schema fingerprint and all unresolved release gates. It never selects actual invoice contents, counts actual financial transactions, or creates database objects.
- Output always says `credit_note_history_issuance_allowed: false`. A candidate table name cannot silently authorize a source mapping.
- The `--isolated-qa` option allows `invoice_qa` for synthetic CI only.

### Safe operator invocation (READ ONLY)

```bash
# On the private AWS operator terminal, after obtaining the correct
# read-only PostgreSQL reporting role and its DSN locally:
python3 scripts/sbi_credit_note_history_catalog_preflight.py \
  --dsn-env SBI_HISTORY_REPORT_READONLY_DSN \
  --output /private/sbi-credit-history-catalog-20261127.json

# Inspect the JSON. Do not paste credentials, tokens, bank data,
# customer addresses or unredacted DSNs into ChatGPT or GitHub.
```

**This command does NOT enable either credit note Finalize flag.**

## Source identity and release blockers

1. Owner must identify the actual authoritative historical PostgreSQL relation/view if the invoices are indeed stored there. Confirm its approved identity, ownership, and duplicate treatment, not merely its name.
2. Obtain exact original invoice numbers, invoice dates, service months, SOL/client/GST identity, taxable/CGST/SGST/total and source SHA/snapshot evidence. Flag inconsistencies without auto-correction.
3. Independently cross-check every requested invoice against all historical credit notes (including existing non-`MXP` or invalid CN references), cancellations, reconciled payments/TDS and GST return filing status to prevent duplicate tax adjustments.
4. Verify the 2-owner Firebase session isolation, private PostgreSQL access and approved accountant workflow.
5. Only after a separately approved adapter and full QA should historical credit notes become draftable/finalizable. Original invoices remain immutable; issuing a credit note does not silently reverse bank reconciliation.

## QA and audit statements

Automated tests exercise synthetic report matches, ambiguous duplicates, missing sources, inconsistent GST totals/SOLs, existing credit markers and the hard rule that historical results NEVER qualify for credit-note finalization. Catalog tests enforce real read-only transactions against isolated `invoice_qa`.

**Financial Apply remains locked. No production AWS migration or deployment has been performed under this milestone.**
