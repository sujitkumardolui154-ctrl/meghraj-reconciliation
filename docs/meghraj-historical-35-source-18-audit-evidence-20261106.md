# @meghraj reconciliation — historical source/model evidence rule (2026-11-06)

**Owner directive:** The first **35 physical columns of the currently approved original `Invoice Details.` workbook are invoice-related evidence**. All other fields in the approved 53-column *report projection* are **internal reconciliation/audit model fields**. Those model fields must be associated with each individual invoice/source-row identity and populated only from supported evidence; never fabricated or used to overwrite original invoice values.

## Evidence trail and legacy variants

1. **23 October 2026 approved Meghraj matching instruction (historical user context):** Original Invoice No. is NOT the primary payment-to-invoice matching key. Identify credible branch/SOL and amount context first; retrieve Invoice No. from the original invoice source row only after finding a valid invoice candidate. PAYMNENT Bank Credit = column I; preserve A:L; add working columns beginning M. Never overwrite protected source values.
2. **24 October 2026 Meghraj + MXP GST final rulebook, v1.0–v1.2:** Meghraj payment reconciliation and MXP GST are independent workflows; original Client Name H and all source invoice columns remain unchanged; only approved model identity columns are inserted after original H; never invent branch mapping or use invoice number as sole reconciliation proof. Reference Library: `RULEBOOK_MEGHRAJ_MXP_GST_v1.0_FINAL_APPROVED_2026-10-24.md` / `v1.2_APPROVED`.
3. **28 October 2026 v2.51 + v2.18 output schema addendum:** A historical 34-column original A:AH layout and separate AI:AM model fields existed under the v2.18 special *Execute* output contract. This is a DIFFERENT legacy schema; do not change its approved output headers or silently treat the present 35-column original as 34 columns.
4. **3–6 November 2026 approved 35→53 ingestion/report projection:** User supplied an *original 35-column* `Invoice Details.` workbook with an additional second `Branch Code` at source column I (original Branch Code G remains). Current `backend_source/invoice_source_schema.py` supports HEADERS_35 and `export_values_53`; `backend_source/invoice_import_contract.json` enumerates HEADERS_53. The approved 53-column report projects 35 protected original values into positions 1–8 and 11–37, and 18 internal model fields into positions 9,10,38–53.
5. **6 November 2026 user reaffirmation:** Preserve all first 35 physical source fields as invoice evidence; the other 18 fields are internal auditor/reconciliation remarks and must relate to each invoice number, disambiguated by source row/branch/amount when invoice numbers repeat.

The exact earliest standalone conversation titled `@meghraj reconciliation` was not recoverable in the historical search. The named rule is now recorded here with links to verifiable related rulebooks, current code and the owner's 6 November directive. Do not claim the precise wording was found in an inaccessible old chat.

## Approved current 53-column positional mapping

- Original source physical A:H (8 columns) → enriched report columns 1–8.
- Internal `Model SOL ID` and `Model Proper Client Name` → enriched report columns 9–10.
- Original source physical I:AI (27 further columns, including second `Branch Code`) → enriched report columns 11–37.
- Remaining internal model/audit fields (including `Model Reconciliation Status`, payment/match evidence and shadow status) → enriched report columns 38–53.
- **35 protected source fields + 18 evidence-controlled model fields = 53 approved output columns.**
- Repeated header labels are intentional: do not deduplicate, rename, reorder or infer by header name alone. Branch Code SOL and invoice identifiers must remain TEXT and original values retained verbatim (spreadsheet/CSV safety escapes are reversible export encodings, not source edits).

## Independent QA — current read-only evidence (2026-11-06)

Original uploaded workbook `INVOICE MEGHRAJ EXPRESS SBI(1).xlsx`: 14,374 invoice rows, 35 physical source fields, plus `PAYMNENT` and `Credit Note` worksheets. SHA-256: `cae074720d0098ac9f9e3847e3e8edfa4b49cbba21ea755efb5833c91019f665`.

Supplied `sbi-ok-v1.4.2.csv`: 10,560 model/report rows, exact 53 approved headings. SHA-256: `2a85c1873a61ea38441bb2516536c84b147d3f13f3d0016d179a5a22d6f57fe3`.

Previously independently checked: 10,560/10,560 rows linked to **distinct original rows**; all 35 positional original data fields agree after reversible Excel/CSV formatting normalization.

New read-only audit:
- All 14,374 protected source rows retained in a separate private 53-column *analysis-only* projection; the 18 model columns were carried over for 10,560 independently linked source rows only. Remaining 3,814 have **no supplied OK-model evidence**, so model cells remain blank and a separate private audit row states PENDING_REVIEW.
- All 14,374 original source invoice column S cells are nonblank; no source payment may be overwritten and no new bank-credit allocation is permitted.
- Primary SOL+amount/TDS candidate screening used PAYMNENT Credit I and 0/1/2/3% modeled TDS (Decimal HALF_UP), with ±₹0.01 amount hypothesis: 11,841 positive bank credits; 2,808 bank rows have one *possible* original invoice row and 451 have multiple candidate invoice rows; 8,582 have none. **Not settlement proof**: service periods, prior payments, bank ownership, SBISA/GST exceptions, matching waterfall and finance signoff NOT verified.
- Supplemental explicit MXP narration-reference screen is **not the primary matching method** and no bank candidate has been marked OK.
- Error Report ERR-01..ERR-12 remains REVIEW_REQUIRED; source mismatch, duplicate, invalid-number and evidence gaps are flagged without source edits.

## Permanent controls and next process

1. First 35 original physical fields are immutable invoice evidence; attach and refresh the 18 model fields only against a **verified invoice source row**, with invoice number as a referent and never as the sole matching criterion.
2. Do not auto-populate monetary allocation, bank row, SOL name or OK status from the filename `sbi-ok`, from a model remark or from a single matching TDS scenario.
3. If duplicate invoice numbers or placeholder IDs occur, require row-level disambiguation; leave unsupported fields unfilled and issue ERR flags rather than guess.
4. Preserve `PAYMNENT` A:L, Credit I only, and original Invoice Details payment column S (nonblank = protect from new allocation). Other source sheets/formulas remain unchanged.
5. Keep real invoice/payment files **private**. Only sanitized schema/aggregate evidence may be committed to this GitHub repository.
6. Independent bank reconciliation, approved separate 18-column Credit Note parity, immutable backup restore, live auth and production cutover remain BLOCKED until independently verified and separately authorized.

**SOURCE_FILES_MODIFIED=NO** | **FINANCIAL_DB_WRITES=0** | **MODEL_FIELDS_UNSUPPORTED=BLANK_NOT_GUESSED** | **PRODUCTION=BLOCKED**
