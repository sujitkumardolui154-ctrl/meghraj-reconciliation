# SBI Invoice/GST — 25 November 2026 private staging continuation

**Status:** SOURCE DISCOVERY COMPLETE; CODE QA PASSED; PRIVATE AWS INTEGRATION PENDING.
**Owner-approved design:** corrected Meghraj Express MXP18430 six-page PDF, 24 Nov 2026.
**Pull request:** #182 (draft).
**Latest verified head:** `3957ef410f01568f6f9c63f95cd6555d6ca4ee38`
**Latest completed combined CI:** [run 45469923102](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45469923102), PASS.
**Production/financial writes:** NONE by this milestone.

## Verified connected Drive sources

- `SBI_SOL_Branch_Master_FINAL.xlsx` at
  `https://docs.google.com/spreadsheets/d/1BWLwiISc3IMcG6uEgkzptyPODNgu2hTj/edit`.
  This is an **Excel workbook stored in Drive** (not a native Google Sheet).
  A later upload dated 20 November 2026 was found. The same filename also
  exists in an older 27 October 2026 version; do not silently switch IDs.
- `MXP_GST_SBI_BRANCH_MASTER_ALIAS_CORRECTIONS_v2_7_REVIEW.xlsx` at
  `https://docs.google.com/spreadsheets/d/1DEf6SeQXSSIE9LlnnFQtdUw_CMSYBT1v/edit`.
  This is a **review** source; it does not supersede the separately approved
  private master or justify promoting unresolved aliases.
- Original legacy `sbi invoice format  FEBRUARY 2026.xls` at
  `https://docs.google.com/spreadsheets/d/1HykxWHLbi6O_aIxP6MjAQUcaZ6d5Yhho/edit`.
  File size ~17.8 MB. Avoid whole-workbook text hydration, which can exceed
  connector size limits. Its original native formatting is not yet certified
  against the approved PDF reference.

## Read-only findings requiring careful interpretation

The connected Drive representation of the master workbook includes appended
supplementary and review tables; it is **not a single homogeneous list**.
The canonical tab and Review Summary should control accepted range, not
a naive count of every row in a flattened CSV export. Existing private
workbook gate pins 1,484 canonical rows and 19 supplementary review rows,
with production status `WORKING REVIEW — NOT FINAL`.

In the flattened representation, 917 entries are annotated with missing
billing-location selection, and the canonical area contains missing or
nonstandard SOL examples. Billing-location labels may identify a delivery
contact rather than the legal invoice issuing location. Therefore:

1. Do not set `verified=true` for all rows, even when a SOL and address exist.
2. Never convert a four-digit or missing SOL, customer address, recipient
   designation, GST classification or invoice generating location from a guess.
3. Never promote the `SBI FUND MANAGEMENT LTD _ Krishanagar` alias to 99922
   solely from an incomplete master row: source conflicts with the separate
   `MUTUAL FUND KHAGRA` entry and requires record-specific evidence.
4. Do not treat a review sheet's notes as automatic authorization to remap
   the RBO 6 Kalyani identity to RBO 5 Krishnagar.
5. Use the GitHub v2.7 matcher only for exact or documented unique aliases,
   with separate owner-approved row-level legal invoice details.

## What the existing code provides

- `master_workbook_gate.py`: exact workbook SHA + canonical/tab review.
- `load_private_branch_master.py`: fingerprinted, independently verified
  **subset** intake; prohibits duplicate SOL and silent changes to addresses.
- `private_vendor_loader.py`: private, hash-verified exact logo/legal
  profile; rejects conflicting replacement.
- `001_isolated_invoice_schema.sql` → `002_vendor_header_fields.sql`
  → `003_verified_sol_uniqueness.sql`: QA-only migrations.
- `sbi_invoice_gst_aws_staging_readiness.py`: read-only local source/database
  preflight and optional ingress inspection.
- `sbi_invoice_gst_private_qa_gate.py`: fail-closed QA prerequisite check.

## Execution instructions for authorized AWS operator

1. Do not alter the live Caddy routes, production database or existing
   financial reconciliation engine. Obtain a **separate** isolated
   `invoice_qa` database and prove a backup/restore point.
2. Download the exact pinned owner-approved master workbook, PDF, and
   private logo/vendor ZIP to a private path. Verify the SHA256 pins in
   `scripts/sbi_invoice_gst_aws_staging_readiness.py`.
3. Run migration 001, then 002, then 003 on **invoice_qa only**. On any
   duplicate-SOL or collision failure, stop for review.
4. Obtain row-level recipient title, customer address, client class/GSTIN
   and invoice issuing location approval. Run the reviewed-subset importer;
   excluded branches stay excluded.
5. Import the private vendor profile into `invoice_qa` and confirm exact
   logo and all right-hand company-header fields. Do not log bank details.
6. Run source/DB/ingress preflight and `--assert-ready`; stop on nonzero
   exit or unresolved source. Only after a positive result run authenticated
   Firebase/CSRF staging QA for preview, finalize, PDF and GST XLSX.
7. Keep production finalize and payment allocation disabled. A private QA
   pass **does not authorize production cutover**.

### Operator commands (read-only until separately approved QA import)

```bash
# Run from the reviewed PR checkout on the isolated AWS operator machine.
# No credential values or tokens should be pasted into ChatGPT/GitHub.
python scripts/sbi_invoice_gst_aws_staging_readiness.py \
  --master /private/SBI_SOL_Branch_Master_FINAL.xlsx \
  --vendor-bundle /private/Meghraj_Invoice_Private_Assets_With_Full_Header_20261124.zip \
  --approved-pdf /private/Meghraj_Express_MXP18430_Corrected_Full_Header_Invoice.pdf \
  --qa-db --check-public-ingress \
  --output /private/sbi-invoice-gst-private-qa-preflight.json

python scripts/sbi_invoice_gst_private_qa_gate.py \
  --preflight-json /private/sbi-invoice-gst-private-qa-preflight.json \
  --assert-ready
```

## Explicit unverified items

- Raw master/legacy XLS binary was not copied to AWS through this conversation.
- No AWS SSH/terminal, isolated PostgreSQL DSN, private snapshot or
  Firebase-authenticated staging session was available to this invocation.
- Private vendor ZIP and source master were not imported to AWS.
- No real invoice was finalized; no real GST report from an AWS DB generated.
- GitHub CI PASS is synthetic/isolated and should never be labeled real
  production financial parity.

**Next action:** private operator supplies the output JSON from the above
preflight without passwords/DSNs, or enables a sanctioned AWS terminal
connector/session; then inspect the exact failing gate and execute signed-in
isolated combined QA only when prerequisites are satisfied.
