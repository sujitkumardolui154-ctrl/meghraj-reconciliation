# Owner approval — Meghraj Express invoice reference format

**Decision:** APPROVED BY OWNER  
**Approval date:** 2026-11-24 (Asia/Kolkata)  
**Scope:** SBI Reconciliation Workspace > Invoice Generation module  
**Source:** User confirmed "Aproved this invoice" after reviewing the regenerated six-page PDF corrected from the Excel screenshot.

## Approved, immutable reference artifact

- Filename: `Meghraj_Express_MXP18430_Corrected_Full_Header_Invoice.pdf`
- SHA-256: `631bfbcb15c4db3edca61f953bbe3f2e865dac370ff0f437cf443afacb111495`
- Page count: 6
- Sample invoice: MXP18430; it is a **design reference**, not a new invoice to import, post, duplicate, or reconcile
- Original uploaded logo file: `meghraj_logo.webp`
- Logo SHA-256: `f65ab5173cb1fdbc3a5971f8b2c376b923ad77e7e3f1b35f363640626da131d8`
- Private vendor/source archive: `Meghraj_Invoice_Private_Assets_With_Full_Header_20261124.zip`
- Private archive SHA-256: `ae9dfefd1d40c6be399657e7f508751583bab7dc99fcbe0c8239abb882170f8f`

The PDF and private vendor archive are **not in this repository** and must not be committed to public GitHub. Identifiers above are for evidence verification only. Private asset import into AWS is **not** evidenced by this approval.

## Format baseline locked by this approval

1. Exact supplied Meghraj Express logo remains on the **left** of the company header, without redesign.
2. Registered-office, head-office, telephone, email, website and company GSTIN panel remains on the **right**, using verified private profile fields. Missing fields must block finalization rather than be omitted silently.
3. Full-width, black-bordered `TAX INVOICE` heading; SBI branch/customer address and invoice number/dates in their established positions.
4. Statement of service month is independent of the invoice issue month.
5. Financial table retains the approved columns: Invoice Month, Bill Amount, CGST 9%, SGST 9%, Total and Total With Round Off. Rounding is not invented when source does not establish it.
6. Amount in words, POD/self-declaration, remittance and legal text, signatory, and footer are preserved from the verified private vendor profile.
7. Six-column shipment annexure: Dispatch Date, LR No, Packet Ref No, Consignee, Weight, Amount. Preserve blank Packet Ref No values and original shipment ordering.
8. Future invoice numbers, dates, customers, SOL IDs, service periods and amounts are dynamic, validated and stored in the isolated invoice registry. The sample numbers and amounts must not be hardcoded into generated invoices.
9. GST reporting remains the existing approved 16-column contract; invoice financial fields only from finalized stored invoices and other fields from verified database snapshots.
10. Any future visible template change or legal/bank content update requires owner review; do not silently change this approved layout.

## What this approval does **not** authorize

- No claim of pixel-identical reproduction of a native Excel workbook: only the corrected PDF reference and Excel screenshot were provided.
- No approval to import invoice MXP18430 as a new transaction.
- No authorization to alter historical reconciliations, settlement allocations or credit notes.
- No permission to upload private source data to public GitHub.
- No approval for live AWS deployment, production database writes, or bypassing authenticated staging tests.
- Full private branch-master records and private vendor DB import must still be verified separately.

**Release handling:** This reference design is approved; keep implementation PR #182 in draft while technical/database and deployment release gates remain unresolved.
