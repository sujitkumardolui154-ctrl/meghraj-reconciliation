# R24 — Original SBI Source Column Contract Correction (24 Nov 2026)

## No financial source position shift permitted

An authorized user submitted an Excel source file. Its original `Invoice Details.` A:AH headers were inspected against two preserved historical evidence references:
- `MEGHRAJ_PAYMENT_RECONCILED_v2.18_2026-10-26.xlsx`: historical output source-layout reference (NOT current financial certification)
- `INVOICE_MEGHRAJ_EXPRESS_SBI_ORIGINAL_BACKUP_2026-10-28.xlsx`: historical original source-layout reference

Both originals agree on the following:
| Column | Original field |
|---|---|
| G | Branch Code/SOL |
| H | Client Name |
| J | Invoice No |
| K | Taxable Amount |
| L | CGST |
| M | SGST |
| N | Total Bill Amount |
| S | Original Payment Received (With/Without GST) Payment Date; **any nonblank including 0 is protected** |

`PAYMNENT` original A:L remain immutable. Bank credit is only column I; H is debit, J is balance, K is an original marker, and L is original reserved blank header. Do not change original sheet names, formulas, ordering or historical data.

**Root defect:** R16 and R19/R20 synthetic fixtures expected invoice IDs in M, which is really SGST. Moving the financial source to make M an invoice string would destroy the tax amounts. Instead, change *readers and test fixtures* to use invoice J and monetary K:N, preserving all source bytes.

## Actual R24 development changes
- R16 `EXPECTED_INVOICE_HEADERS`: verify G Branch Code, H Client Name, J Invoice No, **M SGST**.
- R16 two-pass duplicate and identity scans use zero-based `row[9]`, never `row[12]` to derive invoice identity.
- R19 synthetic-only worksheet fixture and financial math read J (invoice), K (taxable), L (CGST), M (SGST), N (gross); validate formula and total; preserve S marker.
- R20 synthetic-only Excel serializer uses `invoice_sheet.cell(row,10)` for invoice identity. Original A:AH source is byte-for-byte preserved by its output comparison.
- R16/R18/R19/R20 tests updated. New R16 negative tests assert SGST M never masquerades as invoice ID, wrong J/M headers fail, and original S nonblank is protected.
- Combined R24 workflow includes all R15–R21 offline/synthetic and disposable PostgreSQL tests plus source-column invariants.

## Security / source data
No actual SBI rows, invoice IDs or bank values are committed to GitHub. No real workbook is fed to the synthetic CI financial engine. The uploaded workbook is preserved as the only current user-supplied private source, with SHA256 verified in the private intake report; its row data remains outside public GitHub.

R24 fixes **development mapping only**. It cannot authorize complete Master v2.51 / Matrix v2.39, correct financial allocations, cloud auth/DB access, or production cutover.

**Release:** `FINANCIAL_APPLY=LOCKED`, financial database writes NONE, `main` unchanged.
