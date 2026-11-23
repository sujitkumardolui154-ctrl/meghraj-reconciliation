# NEW engine 21 11 2026 — Combined Stage 4.2–4.5 review gate

**22 November 2026 | Offline/synthetic-only development candidate**

## Goal
Check one end-to-end source-validation and review-output path against the recovered **exact nine-tab v2.18** layout, reusing the existing Stage 4 signed new-only candidate ledger and Stage 4.1 writer. This is deliberately a **consolidated test**, not separate repetitive engineering QA stages.

## Implemented

1. Require an invented `SYNTHETIC_*.xlsx` input/output, check full workbook SHA-256 against independently signed internal-gateway bank and invoice envelopes.
2. Verify the HMAC internal-gateway signature, exact upload `Description | SOL ID | Credit Amount`, original `PAYMNENT!I` credit, source row/date/SOL/client, and invoice month/date/SOL/client/invoice no/taxable/CGST/SGST/gross against the original synthetic source cells.
3. Accept **only** the hash-pinned nine-tab v2.18 layout and exactly one synthetic payment/invoice. Duplicate column labels or unapproved newer invoice layouts **fail closed** rather than being automatically converted.
4. Run a temporary isolated Stage 4 SQLite WAL candidate ledger: one intake, a separate reviewer, **zero** reservations and **zero** financial postings.
5. Produce one v2.18 `PAYMNENT` M:W and `Invoice Details.` AI:AM **SUSPENSE-only** review workbook via the corrected writer, then independently verify that all original source cells and formulas are unchanged.
6. Verify 15 integration negatives and 5 source-contract controls. Preserve Stage 4's 41 and Stage 4.1's 24 previously implemented regression tests in the same local command.

### Actual local QA

- 41 Stage 4 persistent ledger tests: **PASS**
- 24 Stage 4.1 output contract/writer tests: **PASS**
- 15 new full synthetic workbook integration tests: **PASS**
- 5 new source-code/manifest tests: **PASS**
- **85/85 in this combined local regression.** All records are fabricated.
- Earlier Stage 3 71-case source CI exists and should run in the GitHub PR combined source gate; distinguish that from independent runtime Excel QA.

## Important limitations

**This is not the complete real financial integration.** HMAC verification proves only an internal signer; it does not independently prove SBI bank origin. `Principal` is a trusted-host interface, not a Firebase session. Historical SBI financial workbooks were not opened or processed. The real new-format source schema has `Invoice No` in **K** and different header sequence, whereas pinned v2.18 has invoice no in **J**; mapping must be independently verified before automatic conversion. `SUSPENSE` means the engine has **not** certified a match; no candidate reservation, `OK`, TDS/GST allocation, paid marker or settlement is written. The code has no AWS route, public posting API or financial credential.

**Still pending before production:** authoritative bank/U​​TR/date source; actual Firebase role and CSRF guard; new invoice/official SOL source; full v2.51 financial method precedence incl GST-later, TDS/partial, SBISA and DNM-01; production ledger/writer; independent artifact_tool runtime integration/security/rollback QA; separate owner production financial release. Existing AWS Stage 3 container remains unchanged, localhost-only and Apply 403.

## Run the combined test from a repo checkout

Requires a Python 3.11+ runtime with `artifact_tool` (installed in the developer runtime) and the source trees `stage4`, `stage41`, `stage42`.

```bash
bash staging/fresh_financial_engine/stage42/run_combined_qa.sh
```

The script refuses to run in a directory missing the expected source modules. It does not accept a spreadsheet path or financial inputs.

**FINANCIAL_APPLY=LOCKED; FINANCIAL_POSTING=NOT_IMPLEMENTED; HISTORICAL_RECORDS=NOT_PROCESSED.**
