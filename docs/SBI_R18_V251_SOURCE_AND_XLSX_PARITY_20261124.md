# SBI R18 — Full v2.51 source-qualification gate and v2.18 XLSX structural parity QA
**Date:** 24 November 2026 IST  
**Branch:** `review/sbi-r18-v251-source-certification-output-parity-20261124` (development PR, not production)  
**Release:** `FINANCIAL_APPLY=LOCKED`

## Evidence basis inspected directly

1. The private archived `MEGHRAJ_INTEGRATED_ENGINE_RECOVERY_CANDIDATE_2026-10-27` manifest identifies `ENGINE_REFERENCE/reconciliation_engine.py` as SHA256 `72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf`. The module declares **Master v2.22 / Matrix v2.10** and review-only candidate scoring. It is **not** full executable v2.51 / v2.39.
2. The separate recovered `conservative_engine.py` SHA256 `6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3` explicitly describes a partial finance rehearsal, with known false-positive policy hazards. It also is **not** a certified v2.51 engine.
3. Historical `SBI_SOL_Branch_Master_FINAL.xlsx` SHA256 `4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388` is a historical *reference*. Its presence in an archive is **not proof** of current approved master authority or a fresh financial execute.
4. `MASTER_V251_V218_OUTPUT_SCHEMA_LOCK_ADDENDUM_20261028.md` authorizes immutable original `PAYMNENT!A:L`, `Invoice Details.!A:AH` and the model columns below. See [Drive source](https://docs.google.com/document/d/1SPAHhP4K2T1jjAW7goXfUz7J9dtihzpc/edit).
5. The repo's `backend_source/invoice_import_contract.json` defines a distinct **53-column** invoice/report contract. Repeated headings are deliberate: *Client Name* at A and H, *Branch Code* at G and K. It is **not** interchangeable with the payment workbook v2.18 model positions.

## What R18 actually adds
`scripts/ci/sbi_r18_output_parity_gate.py` supplies three pure read-only functions:

### A. `audit_candidate_source(candidate_bytes, source_manifest)`
- Deny known archived/review-only recovered engine hashes.
- Verify exact caller-supplied SHA256 and the claimed v2.51 / v2.39 version pairing.
- **Never** report `master_v251_certified=True` based on a version string, file hash, or unverified `approved`/`qa_signed` JSON.
- Return `BLOCKED_CANDIDATE_SOURCE_OR_MANIFEST_MISSING` if the complete private candidate or its manifest is absent.
- No code import/execution from unknown master source, no automatic source promotion and no financial writer.

### B. `verify_xlsx_output_structure(original_bytes, candidate_bytes, ...)`
- Require exact, caller-supplied SHA256 for both files and use R15 original source preflight.
- Compare sheet names/order/count, row counts, original cell values, formulas and number formats.
- Preserve all original `PAYMNENT` columns A:L (H debit, I incoming credit, J balance, K original status, L original protected position).
- Preserve original `Invoice Details.` A:AH, including original S nonblank markers and original invoice columns.
- Preserve every other original worksheet's cell values, formulas, formats, order and column bounds. Do not require exactly nine old tabs for a legitimately different fresh source.
- Validate exact payment model headers M:W:
  `Model Reconciliation Status`, `Model Reconciliation Remarks`, `Model Invoice No (Candidate if SUSPENSE)`, `Model Invoice Source Row`, `Model Match Method`, `Model TDS Rate % (Inferred)`, `Model Expected Credit (Hypothesis)`, `Model Signed Residual`, `Model Service / Evidence`, `Model SOL ID`, `Model Proper Client Name`.
- Validate exact invoice model AI:AM:
  `Model SOL ID`, `Model Proper Client Name`, `Model Linked Bank Row (Working)`, `Model Linked Bank Credit`, `Model Match Evidence`.
- Require a syntactically valid category M (`OK`, `SUSPENSE`, `Duplicate Payment`) for positive credit rows; block `OK` or `Duplicate Payment` for nonpositive/unverified credits.
- Reject added Overview / auxiliary report tabs, extra X or AN model columns, altered source formulas, source reordering and prior modelled source uploads.
- **This checks only structure, not whether an `OK` classification is true**. No model money, TDS, aggregate financial parity or ledger conservation is certified by the XLSX validator. For full financial logic and signature validation, independent QA is still mandatory.

### C. `verify_53_header_contract(actual_headers, contract_headers)`
- Exact 53 positions and exact order per repo-approved JSON.
- Retain duplicate headings at A/H and G/K. Do not de-duplicate or rename.
- No invoice values or monetary totals evaluated.

## CI coverage
Synthetic-only GitHub Actions workflow executes all 16 R15, 25 R16, 56 R17 and 41 R18 isolated contract tests (**138 total if all pass**). Includes same-input hash/readback, source formula/format protection, previously classified or nonpositive payment safeguards, exact model headers and 53-column duplicate header protections. This is **not real input** and does not call AWS, Firebase, Postgres, bank APIs or any production data store.

## Limits and unverified dependencies
R18 cannot claim complete v2.51 / v2.39 implementation, full-rule parity, certified version release, actual v2.18 writer output, financial amounts parity, database transaction rollback, bank identity, proper finance release, or a real signed Firebase-to-Flask app session. R14 real Firebase session remains a separate pending gate in PR #154.

A **full financial parity run** requires an independently signed/certified exact source candidate and complete method evidence (TDS, DNM-01, service period, GST-later, SBISA, approved cross-SOL, duplicate/credit note, one global ledger, waterfall last), fresh privately supplied source and current approved master, exact-hash output writer, independent line-by-line ledger oracle and isolated PostgreSQL access. Output SHA equality, synthetic status categories or a public CI green check cannot substitute for those dependencies.

**Safety:** No financial Apply, production deployment, write operations, cloud activation, historical data import to new database, or real customer data in GitHub QA. Future production cutover requires separate authenticated approval.
