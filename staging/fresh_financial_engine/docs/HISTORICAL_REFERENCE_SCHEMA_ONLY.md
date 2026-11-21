# SBI v2.51 Historical Reference — Header Metadata Only (21 November 2026)

## Authorization scope
The owner permits using historical SBI financial records **as references for engineering**. The two mounted workbooks were inspected for worksheet names, row-1 headers and used-range dimensions only. **No historical transactions or invoice amounts were output, reconciled, recalculated, migrated, imported into new engine, or committed to GitHub.** This is NOT permission to change any historic settlement, unlock the Apply button, or run historical finance data as a test fixture.

## Read-only source comparison
- `INVOICE MEGHRAJ EXPRESS SBI(2).xlsx`: `Invoice Details.` (A1:AI14775), `PAYMNENT` (A1:Y15020).
- `MEGHRAJ_RECONCILIATION_AS_PER_RULES.xlsx`: has those exact two required sheets with identical 35-column invoice and 12-column payment headers, plus auxiliary tabs that must never be implicitly used as finance sources.
- Source `PAYMNENT` Row 1 A–L: Location, Branch Name, Txn Date, Value Date, Description, Branch Code, Name, Debit, Credit, Balance, Cross Tally, Record For Me. Some original header labels contain extra spaces; the new validator compares whitespace-normalized labels without editing source bytes.
- Source payment coordinates: C=Txn Date, D=Value Date, E=Description, F=Branch Code/SOL, H=Debit (**never payment evidence**), I=Credit (**only incoming bank credit**).
- Source `Invoice Details.` Row 1 A–AI: contains two separate `Client Name` headers (A and H) and two `Branch Code` headers (G and I). **Do not use dictionary lookup by header name**; G=SOL, H=verified client identity in the approved rulebook. Column K=Invoice No, E=Month, F=Invoice Date, L=Taxable, M=CGST, N=SGST, O=Gross, S=paid-marker. Nonblank S is protected and disqualifies a new invoice allocation.
- Legacy original `PAYMNENT` A:L and `Invoice Details.` A:AH must remain unchanged. Model columns cannot override source.
- New 3-column upload UI `Description | SOL ID | Credit Amount` remains unchanged; these are **not sufficient by themselves** to prove bank date, UTR, bank authenticity or invoice eligibility. An authenticated provenance source must supply that information separately.

## Fresh engine patch
`staging/fresh_financial_engine/sbi_engine/reference_schema.py` encodes the column offsets and row-1 header contract as static metadata; **no XLSX reading methods, database connections or financial calculations**. `tests/test_reference_schema.py` uses fabricated header arrays only and checks six guards.

## Deployment status
The fresh v0.1 engine still accepts only `SYNTH-*` data for proposal analysis. Historical files may inform documentation and edge-case design, but **real payment/settlement execution remains disabled** pending the independent new-only ledger and separate release approval.
