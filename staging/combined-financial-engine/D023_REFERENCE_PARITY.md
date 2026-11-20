# D-023 — SBI Combined Financial Engine Reference Math and Parity Checks
Date: 2026-11-20 — Workstream D

**This is a stacked review above D-022 PR #116, not a merged settlement engine or AWS deployment.**

## Added calculation, no settlement
- Strictly reads original invoice row layouts 34, 35 or 53 columns via the approved schema; no renumbering, no formula evaluation and no auto-corrections.
- Checks original invoice `Taxable Amount + CGST + SGST == Total Bill Amount`; invalid currency, negative, non-finite, formulas, excess precision and mismatched gross become `REVIEW_REQUIRED` with zero reference payment scenarios.
- Derives four **hypothetical reference** TDS rates 0%, 1%, 2%, 3% against *taxable amount* only, Decimal `ROUND_HALF_UP` to ₹0.01; separately displays with-GST and without-GST expected-credit reference values. These are **not allocated bank receipts, GST settlements or proof of any invoice payment**.
- Composes actual source review from D-022; protects Column S nonblank, duplicates and Credit Note flags as eligibility holds; reports anonymized row ordinals and reason counts only, not bank/invoice money.
- No bank credit assignment or guessing of invoice-specific TDS rates. No amount write-off. Original sources and protected historical allocations remain unchanged. All results continue `REVIEW_REQUIRED` and are not approved for settlement.

## Outstanding release and data gates
- Independently authenticated original workbook `Invoice Details.` and `PAYMNENT` plus private approved historical allocation ledger are **not available** as verifiable inputs in the current connected project context. Approved SBI Clean Branch Master exists privately but has not been attested as the runtime version.
- Complete canonical payment waterfall rules (SOL first, partial/full, SBISA SOL 1, period/date, recency, deductions, DNM-01 and credit note conflicts) are not certified by these financial-reference calculations.
- Live per-source invoice/credit/parity, TDS effect, existing report/53 header and GST 16 header parity, protected allocation/rollback and authenticated AWS staging remain unverified.
- Do not treat GitHub synthetic QA as approval of real financial values or production database access.

## Source QA
`python -m unittest discover -s staging/combined-financial-engine/tests -p 'test_*.py' -v`

**FINANCIAL_ENGINE_COMPLETE=NO; REAL_SOURCE_PARITY=NOT_TESTED; FINANCIAL_ALLOCATIONS=NOT_EXECUTED; AWS_DEPLOYMENT=NOT_PERFORMED; PRODUCTION_CUTOVER=BLOCKED.**
