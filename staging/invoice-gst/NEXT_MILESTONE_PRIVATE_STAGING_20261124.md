# SBI Invoice/GST — Private Staging Integration Milestone
Date: 2026-11-24 · Branch: feature/sbi-invoice-gst-combined-20261124 · PR #182

## Source evidence located (never uploaded to GitHub)

- Connected Drive contains `SBI_SOL_Branch_Master_FINAL.xlsx`
  (SHA-256 `ba90aa8320a3283debe059be9cd6dd3083795782b13874d9823329f2185de3e0`).
- Four tabs: `Clean Branch Master`, `Sheet1`, `Name Match Audit`, `Review Summary`.
- `Review Summary` declares **1,484 canonical rows** and explicitly
  `WORKING REVIEW — NOT FINAL`, despite the filename containing FINAL.
- `Clean Branch Master` contains 1,484 canonical SOL records plus **19
  appended supplementary review rows**. Do not treat the appendices as branches.
- In canonical records, **917** have `No billing location found` and
  **two** have no master address. The billing-location column can contain a
  human or routing label, not necessarily an invoice-issuing address.
- `Review Summary` also notes 8 source SOL codes absent from the raw SBI
  master and two conflicting official-name groups. Do not auto-resolve these.
- Source's canonical records cannot be marked DB `verified=TRUE` solely
  because the file name says FINAL.

A legacy native `sbi invoice format  FEBRUARY 2026.xls` also exists in Drive
(17,761,792 bytes; SHA-256
`1ec2194169266a72facbfaaabce29d3b852a996e4b07a7440e13955d9a4faa57`).
It is retained as a private source for a future native-layout comparison;
the approved PDF reference remains the agreed template.

## Owner-approved vendor asset

- Approved PDF SHA-256:
  `631bfbcb15c4db3edca61f953bbe3f2e865dac370ff0f437cf443afacb111495`
- Approved vendor asset archive SHA-256:
  `ae9dfefd1d40c6be399657e7f508751583bab7dc99fcbe0c8239abb882170f8f`
- Original logo SHA-256:
  `f65ab5173cb1fdbc3a5971f8b2c376b923ad77e7e3f1b35f363640626da131d8`
- Local private archive passed SHA-256 integrity and required field checks.
- Private vendor profile **has not been imported to the AWS database**.
- No vendor bank-account details or other confidential values are in the repo.

## Implemented staging connectors

1. `staging/invoice-gst/master_workbook_gate.py`: verifies the exact
   four-tab workbook, review status, pinned raw SHA256, canonical count and
   strips 19 supplementary rows. Optional private CSV handoff (mode 0600).
2. `staging/invoice-gst/load_private_branch_master.py`: merges canonical
   candidates with separately approved private customer/location evidence;
   reviewed-subset mode rejects all missing, inconsistent or conflicted rows.
   Only approved rows can be staged in a DB named exactly `invoice_qa`.
3. `staging/invoice-gst/private_vendor_loader.py`: checks approved vendor
   archive, logo and exact header fields and can import privately in
   `invoice_qa`. A PostgreSQL integration test exercises the importer.
4. `scripts/sbi_invoice_gst_aws_staging_readiness.py`: read-only, opt-in
   source/QA database/unauthenticated ingress preflight; never asserts
   authenticated AWS success without observing a real signed-in request.

## QA-only execution sequence (private AWS operator)

```bash
# Do NOT put the private source files or DSNs into GitHub.
# Operate only on a dedicated isolated QA database named invoice_qa.
python staging/invoice-gst/master_workbook_gate.py \
  --source-xlsx /private/SBI_SOL_Branch_Master_FINAL.xlsx \
  --expected-sha256 ba90aa8320a3283debe059be9cd6dd3083795782b13874d9823329f2185de3e0 \
  --candidate-output /private/SBI_Canonical_Candidates.csv \
  --audit-output /private/SBI_Master_Extraction_Receipt.json

# Independently verify customer, SOL, address, invoice issuing location and
# recipient title in /private/verified_customer_evidence.json first.
# Use a separate private reviewer to attest every approved row.
# Obtain actual hashes on the private machine; use them as inputs.
python staging/invoice-gst/load_private_branch_master.py \
  --master-csv /private/SBI_Canonical_Candidates.csv \
  --evidence-json /private/verified_customer_evidence.json \
  --master-sha256 <actual-private-candidate-csv-sha256> \
  --evidence-sha256 <actual-approved-evidence-sha256> \
  --reviewed-subset-only

# Apply SQL migrations 001 then 002 in the isolated DB ONLY after
# snapshot/rollback verification; import remains a separate deliberate action.
python scripts/sbi_invoice_gst_aws_staging_readiness.py \
  --master /private/SBI_SOL_Branch_Master_FINAL.xlsx \
  --vendor-bundle /private/Meghraj_Invoice_Private_Assets_With_Full_Header_20261124.zip \
  --qa-db --check-public-ingress
```

## Release status

| Area | Status |
| --- | --- |
| Owner-approved invoice printable reference | APPROVED |
| Source/master fingerprint checks | PASSED LOCAL READ-ONLY |
| Canonical vs supplementary source segregation | IMPLEMENTED |
| Verified private subset importer | CODE + SYNTHETIC QA |
| Vendor asset integrity | PASSED LOCAL READ-ONLY |
| Real QA PostgreSQL private asset import | NOT EXECUTED ON AWS |
| Authenticated AWS staging invoice/PDF/GST E2E | NOT TESTED |
| Production release or financial reconciliation writes | NOT PERFORMED |

**Do not merge directly to a live production-connected release or enable
invoice finalization as a result of synthetic QA alone.**
