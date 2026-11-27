# OWNER APPROVAL — MEGHRAJ EXPRESS CREDIT NOTE DESIGN

**Owner decision:** APPROVED — credit-note design / printable format  
**Approval date:** 2026-11-27 (Asia/Kolkata)  
**Owner message:** "APROVED" after inspecting the supplied PDF review artifact  
**Project:** SBI Reconciliation Workspace — Reports > Generate Credit Note

## Approved exact reference PDF (private artifact, not committed)

- **Filename:** `Meghraj_Credit_Note_508_Invoices_Design_Review_SAMPLE.pdf`
- **SHA-256:** `342070cff20357dc0ec18ef2794262bda316f2c9ab7fa946c479847c7e85d54c`
- **Pages:** 10, A4
- **Watermark:** SAMPLE — NOT ISSUED; footer says no database record
- **Illustrative credit note number/date:** `MXP/2026-2027/01`, 2026-05-31
- **Example source:** 508 original invoice-number entries provided by the owner
- **Illustrative taxable total:** INR 529,931.32
- **CGST 9%:** INR 47,693.82
- **SGST 9%:** INR 47,693.82
- **Exact total:** INR 625,318.96; sample rounded display INR 625,319

The original uploaded markdown had an inconsistent displayed subtotal (529931 vs the source-row sum of 529931.32); the owner approved the regenerated PDF with the independently reconciled values. The sample PDF remains a design reference; neither these invoice rows nor the number/date are actual newly issued records.

## Approved design and workflow baseline

1. **Separate Generate Credit Note section** in Reports, distinct from Invoice Creation, Invoice Cancellation and read-only Credit Note reports.
2. **Manual credit-note number** (uniqueness validated; documented series including `MXP/YYYY-YYYY/NN`), **manual credit-note date**, mandatory reason and explicit finalize/preview.
3. Multi-invoice credit note: paste/enter `Invoice No` and intended taxable `Credit Amount` per row. The 508-row sample demonstrates multi-page rendering, not a compulsory 508-row limit.
4. Original Invoice No., Invoice Date, Service Month, customer identity/SOL/GSTIN, original taxable and previously credited amount must be fetched from the authoritative PostgreSQL invoice record, never guessed or taken from editable user metadata.
5. The displayed invoice detail table includes `Sl. No.`, `SAC CODE`, `INVOICE NO.`, `INVOICE DATE`, `MONTH`, `AMOUNT`, with repeating headings across pages for large notes.
6. Show independently calculated Sub Total, Central GST 9%, State GST 9%, Grand Total and amount in words; show round-off as an explicit display value when the approved source requires it. Never copy an inconsistent subtotal.
7. Preserve verified Meghraj Express logo and company details; show SBI recipient/GST details and authorized-signatory section. Customer mailing address still needs private verification for legally sufficient live issuance.
8. Full or partial credit must not exceed the remaining uncredited original invoice amount; duplicate note number and duplicate source invoice rows rejected. Retain approved original invoice/credit-note snapshots and audit actor/time in immutable PostgreSQL tables.
9. Preview must not create an invoice, credit note, tax adjustment or payment allocation.
10. Never delete or rewrite original invoices/annexures to generate a credit note. Credit Note, Invoice Cancellation and payment reconciliation are separate financial events.

## Explicitly **not** approved by this message

- Sample PDF is NOT a legally issued/posted credit note, signed tax instrument, or evidence of bank deduction.
- No automatic import/posting of the 508 sample rows.
- No authorization to use or reserve `MXP/2026-2027/01` as a new issued document; check historical registry first.
- No approval to commit original customer data, private branch master, PAN/bank instructions or logo bytes to public GitHub.
- No migration/deployment in `sbi_reconciliation_main`, and no production payment or GST filing writes.
- No bypass of historical duplicate/credit-note, reconciliation, GST filing, multi-tenant/authentication or release QA gates.
- No declaration that uploaded markdown is a legally complete format: recipient verified address, Rule 53 particulars and authorized signatory require release checks.

## Engineering acceptance handling

- **Design approval:** COMPLETE. Keep this PDF SHA-256 as the reference for future PDF layout regression.
- **GitHub PR:** #182 remains DRAFT; code tested on isolated `invoice_qa`.
- **Technical release:** BLOCKED pending verified read-only historical invoice lookup, prior credit-note/settlement checks, customer legal address, actual private vendor/master import and separate owner release approval.
- **Financial Apply:** LOCKED.
