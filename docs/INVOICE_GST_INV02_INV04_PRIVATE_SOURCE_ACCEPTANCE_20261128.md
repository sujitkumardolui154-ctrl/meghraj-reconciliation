# Invoice/GST INV-02–INV-04 — Existing QA Reuse and Private Source Acceptance
Date: 28 November 2026
Scope: Invoice Creation & GST Reports ONLY
Status: SOURCE_REVIEW_COMPLETE / PRIVATE_RUNTIME_ACCEPTANCE_PENDING / DOCUMENTATION_ONLY

## QA-first lookup (completed before changes)
Integrated Invoice UI v2 / selective QA PR #235 exact head: `2375eb71d02b07adaedd1350efc385000d48291d`.
GitHub Actions completed successfully for:
- Invoice/GST isolated combined QA: run 46143265488
- Module exact-SHA selective QA policy: run 46143265456
- AWS Lightsail preview safety: run 46143265510
- Railway preview safety: run 46143265506
- Synthetic private migration safety: run 46143265520
Do not rerun these successful unchanged-commit scopes. These tests DO NOT prove authenticated live Invoice/GST endpoint acceptance or private asset imports.

## Verified connected source discovery (metadata/read-only)
1. Drive file `SBI_SOL_Branch_Master_FINAL.xlsx`:
   ID `1BWLwiISc3IMcG6uEgkzptyPODNgu2hTj`, Office XLSX, size 189014 bytes, modified 20 Nov 2026.
   Readable content confirms 1484 canonical rows, review status `WORKING REVIEW — NOT FINAL`, unresolved billing-location and alias review. Do not bulk-promote `verified=true`.
2. `MXP_GST_SBI_BRANCH_MASTER_ALIAS_CORRECTIONS_v2_7_REVIEW.xlsx`:
   ID `1DEf6SeQXSSIE9LlnnFQtdUw_CMSYBT1v`, XLSX, size 115625 bytes, modified 20 Nov 2026.
   Reviewed content contains a `NOT AUTO-APPROVED` alias conflict list. It is not an authorization to overwrite the canonical master.
3. `sbi invoice format  FEBRUARY 2026.xls`:
   ID `1HykxWHLbi6O_aIxP6MjAQUcaZ6d5Yhho`, legacy XLS, size 17761792 bytes, modified 24 Nov 2026.
   File existence confirmed; native-cell/style pixel-parity comparison NOT performed.

## Material master conflict for row-level adjudication
The canonical/readable master includes `MUTUAL FUND KHAGRA` for SOL `99922` while the alias-review file also includes other 99922 descriptions. No automatic transfer of 99922 ownership to `SBI FUND MANAGEMENT LTD KALYANI` or Krishnanagar is authorized by this review. Require verified private branch owner evidence before any invoice use. Existing approved SBI FUND GSTIN classification rules alone do not establish a branch identity.
RBO Kalyani and RBO Krishnanagar aliases likewise require unique evidence; do not remap by fuzzy name.

## Source-approved invoice/GST contract already in PR #235
- Verified SBI branch name/SOL selection only, with immutable origin and branch/source status.
- 6-column AWB intake and editable eligible draft rows, server-side amount/tax recalculation.
- The Meghraj six-page corrected invoice PDF is a design reference (approved 24 Nov; exact SHA in `staging/invoice-gst/APPROVED_INVOICE_TEMPLATE_20261124.md`). Private logo/profile and native-source formatting not certified in AWS.
- Exact existing GST 16-column order, including FY, Invoice Branch, Invoice Generate Location, service Month, invoice date, duplicated Branch Code position, Client Name, GST NO, Invoice No, Taxable, CGST, SGST, Total Bill Amount, error flags and original branch name. Original column-name spelling remains governed by the committed source `dashboard_source/invoice_gst_core.py`; no changes authorized here.
- Source `invoice_gst_feature.py` enforces QA-only finalization and isolated `invoice_qa` database fence.
- Month-overlap monthly GST export fails closed with `MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING` until independent accountant/owner policy; do not guess GST tax period from service-month index.

## INV-02 authenticated staging evidence still needed (no duplicate shared security QA)
First check the Deployment/Security module for an actual matching, signed and timestamped Firebase/HTTPS session acceptance on the exact INVOICE endpoints. Do not reuse shared PG R31 tenant tests as proof of invoice API behavior.
Invoice-only real-acceptance matrix for authorized isolated QA, after its preflight passes:
1. Creator login: verified branch query, annexure parse and preview allowed; signed request+CSRF; no public exposure of private data.
2. Viewer login: read-only access as entitled; annexure parsing, finalize/correction/cancellation denied for unentitled account.
3. Anonymous, forged cookie, missing/wrong CSRF, wrong tenant/branch and unauthorized source read denied.
4. Invoice correction preview remains read-only; finalize production mode denied; only approved `invoice_qa` fixtures allowed when explicitly authorized.
5. Confirm generated PDF and 16-column GST export on authorized QA data, with exact invoice and source-row audit references.
6. Recheck no writes to `sbi_reconciliation_main`, payment allocations, historical GST filings or live invoices.
No real Firebase passwords, sessions, private source data or database DSNs in GitHub.

## INV-03 / INV-04 go-no-go
- Reuse already documented private-source hash QA and the source/DB/ingress preflight in `staging/invoice-gst/STAGE_PRIVATE_OPERATOR_HANDOFF_20261125.md`; before new work, verify applicable exact-commit results.
- First authorized operator checks pinned XLSX/logo/vendor/PDF SHA256 in private storage, approved per-row branch source and isolated `invoice_qa` availability. A Drive metadata/readable-text inspection does not independently certify raw binary SHA-256.
- Do NOT import whole WORKING REVIEW master. Only explicitly verified branch subset and supplier fields; any conflict HOLD.
- After positive, redacted preflight, perform only missing invoice-specific Firebase, PDF and GST read-only/isolated-QA acceptance. Preserve six-page approved PDF reference and full AWB annexure. No native Excel pixel-match claim until actual original XLS comparison.

## GST-01 & INV-05 policy hold
- Multi-month service period must be separated from invoice issue date/GST tax period; accounting treatment and filing/credit note impact requires explicit approval. Continue fail-closed monthly exports.
- Corrections must be new linked, audited events, never edit finalized invoice/AWB. Approved cancellation/credit-note production handling requires independent source, payment and filing validation; do not guess.

## Handoffs (not implementation)
Database module owns provision/schema, tenant grants and authoritative read adapter. Reconciliation module owns settlements/credit notes/payment ledger effects. Deployment module owns HTTPS/Firebase infrastructure, release and real external acceptance. This Invoice/GST module only records dependencies and consumes verified evidence.

No code/test workflow changed. No GitHub test rerun requested for documentation-only checkpoint. No AWS changes, SQL writes, merges, Tailscale, financial Apply or live deployment performed. Production release BLOCKED.
