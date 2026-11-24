# SBI R26.9 Case 2.6 — Synthetic method coverage and independent release-evidence gate

**24 November 2026 • Development only • Owner Option B: independent ledger per fresh workbook.**

## Scope completed in development

- `scripts/ci/sbi_r269_case26_method_coverage_rehearsal.py` exercises typed same-upload invoice/bank data against explicit proposed settlement methods, conserves real-valued *synthetic* cash in the Case 2.2 ledger and independently recomputes totals.
- Supports **simulation**, not real payment settlement: exact MXP reference and 0/1/2/3% taxable TDS HALF_UP; documentary GST component; partial amounts; SBI Staff Association (SBISA) SOL 1 vs blank-SOL; explicitly paired cross-SOL master proof; unreferenced unique same-SOL match; multi-invoice oldest-first waterfall **after global adjudication**; and non-reserving DNM-01 provisional holds.
- Source invoice gross must equal taxable + CGST + SGST. Period coverage supports a textual multi-month span expressed as multiple normalized months. Bank issue dates are checked within 180 days, with protected original payment K and invoice S blocked.
- Every proposed method edge is bounded by source bank credit and invoice gross, source and model evidence hashes, one-upload scope, source row identity and immutable report input. The independent comparison is a *cash capacity check*, **not a certified receivable/outstanding or actual TDS/GST/credit-note accounting check**.
- `scripts/ci/sbi_r269_case26_external_release_gate.py` lists twelve required separately authenticated source, identity, rulebook, UTR, prior ledger, tax, method, independent oracle, Excel writer, Firebase, database restore and signed Finance/security release gates. The module **cannot** mark any gate externally verified from a string, hash, self-declared proof, or test result.

## Explicit limitations / outstanding real work

This is not complete Master v2.51 / Matrix v2.39 financial settlement. Full real-world standalone same-SOL and DNM winner adjudication, multi-invoice partial and waterfall sequence on real original bank rows, carried-forward balances *within the same fresh workbook*, documentary GST-later, actual TDS withholding certificates and source-accounting parity, disputed credit notes, immutable bank-event/UTR uniqueness, and protected prior settlement checks remain unverified. No real bank data, SOL master contents, AWS financial databases or live authenticated Firebase session are supplied to GitHub CI. The v2.18 original workbook writer and full 53-column value parity are still not certified.

**Release-gate categories (all blocked):**

1. Original private XLSX bytes SHA/custody
2. Latest owner-approved SOL master, including identity/aliases
3. Complete signed v2.51/v2.39 rulebook and executable source
4. Real SBI bank event UTR/duplicate uniqueness
5. Same-upload verified outstanding and protected prior K/S markers
6. Independent TDS, GST and Credit Note accounting
7. Complete real same-SOL / DNM / SBISA / cross-SOL / waterfall method parity
8. Independent real row-level allocation oracle
9. Original v2.18 writer and 53-column report parity
10. Authenticated real Firebase role-positive and role-negative E2E
11. Real staging database atomic rollback/restore evidence
12. Recorded authorized Finance/security/owner release certification

## QA contract

The existing combined workflow covers 1,004 prior synthetic/disposable QA tests; Case 2.6 adds 62 method and release-gate adversarial tests, **1,066 expected** pending exact-head GitHub Actions confirmation. Tests intentionally cover falsified authority, malformed source, cross-SOL identities, period conflicts, protected prior settlement markers, TDS rounding, DNM provisional refusal, waterfall order, independent cash conservation and replay determinism.

**The implementation must remain fail-closed**: `FINANCIAL_APPLY=LOCKED`, `PAYMNENT!M=NOT_ASSIGNED`, zero real financial allocations/writes, no production `main` merge and no AWS/GCP traffic changes.

After development CI acceptance: retain Case 2.6 as synthetic engineering completion only; do not label complete real financial certification or enable payments until all twelve independent real-evidence gates pass outside this source-only lane.
