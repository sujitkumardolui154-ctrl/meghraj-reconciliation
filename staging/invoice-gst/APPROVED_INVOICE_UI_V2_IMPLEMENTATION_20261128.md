# Invoice Generator UI Version 2 — Approved Review Implementation

**Owner design approval:** 2026-11-28, explicitly approved Invoice UI v2 with SOL ID / branch-name search, multi-month bill period, editable AWB rows, and unchanged production write locks. **Scope: staging/QA review only.**

**Based on:** Owner-reviewed standalone interactive UI prototype `SBI_Invoice_CreditNote_UI_Review_v2.html`; prototype is a design reference and is **not** a production site. No sample customer records or private assets are committed.

## Approved fields and mechanics

1. **Verified SBI Branch *** search accepts either a SOL identifier or a branch-name fragment; choices are retrieved from `sbi_invoice_gst.verified_branches` with `verified=TRUE`. The user must choose an actual returned branch key; typing plain text does not create a verified identity.
2. **Bill Period From** and **Bill Period To** accept different calendar months in the **same Indian financial year**. `2026-09-01` through `2026-10-31` displays **Sept To Oct 2026**. Same-month labels continue to use `September 2026`. Dec 2026 through Jan 2027 displays `Dec 2026 To Jan 2027`. March through April of a different FY is rejected for independent review.
3. **Annexure Upload, Merge & Select:** accepts a strict six-column `.xlsx` (Dispatch Date; LR No/AWB No; Packet Ref No; Consignee; Weight; Amount), with source row parsing in memory, duplicate dispatch-date/AWB detection and skipped-duplicate counts. No file data is written to PostgreSQL on upload. Excel formulas, malformed files, oversized files and data beyond approved limits are rejected. Pasted six-column TSV remains a fallback.
4. **Editable AWB rows:** every AWB has a checkbox. The working table allows inline changes to Packet Ref, Consignee, Weight (kg) and Amount ₹; user can select/deselect all and remove unchecked rows **from the local working draft only**. Totals recalculate for selected, eligible AWBs; the actual server recomputes taxable, CGST and SGST from transmitted canonical lines, enforcing amounts to 2 decimal places and weight to 3.
5. **Find Invoice:** exact `MXP[0-9]{4,10}` query reloads a finalized invoice **and its full saved AWB annexure** into the same screen using `GET /api/invoice-gst/invoices/<number>?include_lines=1`; loading does not mutate the source.
6. **Prepare Correction Draft:** copies the immutable source into local review state but requires a new invoice number; backend checks original source exists and was not cancelled. `preview` is allowed with `correction_review_only=true`; `finalize` unconditionally rejects `replaces_invoice_no` pending an audited revision/credit-note process. This prevents overwriting an issued invoice.

## Critical multi-month GST contract and release safety

- `service_month` stores the approved human-readable label, while the legacy `service_month_key` remains **the starting month** solely for backward-compatible indexing. It does **not** automatically allocate taxable revenue between months.
- The monthly GST report now **blocks** with `MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING` if any active finalized cross-month invoice overlaps the requested calendar month, so the application neither silently omits such an invoice nor duplicates it across months.
- **All finalization, including single-month, is QA-only** under `SBI_INVOICE_GST_DEPLOYMENT_MODE=ISOLATED_QA`. Any other mode returns `INVOICE_UI_V2_PRODUCTION_FINALIZATION_LOCKED`. This prevents editing and selected-AWB workflows from being used for live financial writes before a separately approved release. Even with that mode set, the server verifies `current_database()='invoice_qa'` inside the transaction before any insertion; pointing the same code at `sbi_reconciliation_main` is refused.
- Invoice-source corrections are review-only and never override previously finalized headers or AWBs. Existing append-only PostgreSQL triggers are unchanged.
- **No production financial writes**, reconciliation allocations, GST filings, invoice master migrations, service config changes, deployment or new database creation under this PR.

## Endpoint and regression scope

- `GET /api/invoice-gst/branches?search=<SOL|name>`: query verified branch names, SOL or invoice branch.
- `POST /api/invoice-gst/annexure/parse`: authenticated creator and CSRF-protected `.xlsx` parser; no persistence.
- `GET /api/invoice-gst/invoices/<number>?include_lines=1`: read-only canonical invoice header/annexure, count integrity check and immutable/correction warning.
- `POST /api/invoice-gst/preview`: exact source value validation, multi-month label, correction review only.
- `POST /api/invoice-gst/finalize`: existing auth/CSRF/vendor/source locks; reject correction and live multi-month.

QA tests: `tests/test_invoice_v2_qa.py`, `tests/test_invoice_gst_combined.py` plus the existing combined Credit Note, source import and GST regression workflows. The separate Credit Note UI and approved format are unchanged.

## Remaining explicit release decisions

1. Approve an **accounting/GST policy** for service periods spanning months: whether and how values should be attributed to month-specific reporting, filings and credit-note references. Until then, relevant GST reports remain blocked.
2. Approve an immutable correction/revision workflow with original-invoice link, reason, reviewer and issued credit-note treatment before allowing finalization of a correction.
3. Run authenticated multi-owner Firebase/CSRF and staging PostgreSQL QA with private verified vendor and branch records, verify UX against owner-approved prototype, and seek separate production authorization.

**Result classification:** Implementation for isolated QA; no live deployment authorization.
