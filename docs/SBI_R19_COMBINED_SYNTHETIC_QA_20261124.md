# SBI R19 — Combined remaining-stage isolation test (2026-11-24)

## Purpose
Combine all **currently accessible, synthetic-only** source→master→financial review→Excel-output safeguards in one execution, without claiming real financial release. It is NOT the Master v2.51 / Matrix v2.39 engine, an approved v2.18 writer, a live authenticated Firebase session, or an AWS/PostgreSQL application test.

**Stacked development review:** R19 branch `review/sbi-r19-combined-isolated-source-to-output-20261124` is based on still-open **R18 draft PR #158**, not yet merged to the development readiness branch. R19 PR must target the R18 review branch first; the approval chain remains R18 → R19 → development review → later production authorization. Main/production branch untouched.

## Combined in-memory pipeline
`scripts/ci/sbi_r19_combined_synthetic_rehearsal.py` creates only fictitious source records and an explicitly fictitious master. It rejects non-synthetic identifiers (no real MXP numbers, original payment row identifiers or real SBI branch names) before further processing.

1. **R15** read original `PAYMNENT` and `Invoice Details.` via SHA256; bank receipt from original I, not H/J; no mutation.
2. **R16** match exact text SOL and official fictitious name to a generated private-in-memory master. Reject missing/mismatching authoritative identity, duplicate invoice keys, protected nonblank invoice S including numeric zero.
3. **R17** compare one exact mathematical 2%-TDS candidate, a negative credit, an unauthorized SOL-1/SBISA transfer, a protected paid invoice, and a bank row with old source `OK`. The exact candidate is for **independent review only**; all four positive-credit rows remain `SUSPENSE`. Demonstrate one capacity-only synthetic edge without allocating even one rupee.
4. **R18** build a **mock in-memory locked review workbook** retaining original source tabs and A:L / A:AH values, formulas and number formats, with v2.18 model M:W / AI:AM headers. All statuses remain SUSPENSE. Verify with the independent R18 structural parity gate. Check the distinct 53-column invoice-report duplicate-header positions against `backend_source/invoice_import_contract.json`.
5. **R19** return SHA hashes, aggregate review counts and a manifest of pending external gates. No real row IDs, customer names, payment descriptions, bank amounts, source sheets, database credentials or Excel files are published by CI.

The synthetic mock Excel writer is intentionally NOT the actual production v2.18 writer and cannot be promoted into it without separate development and signoff. The conservative archived v2.22/v2.10 engine and partial old conservative candidate remain unapproved; this combined test does not execute them.

## Test plan and failures closed
- 16 R15 + 25 R16 + 56 R17 + 41 R18 + 36 new R19 unit checks = **174 tests planned** on the exact final PR head. Also run independently triggered existing GitHub PR safety workflows.
- Negative tests for fake real-bank inputs, malformed master/SOL, duplicate invoice/bank IDs, amount formulas, gross-component mismatch, wrong service period/date, wrong 53-column order, source tampering, incorrect promotion of `OK`, and changes to protected original Excel values.
- A preliminary CI run rejected an original empty-string source cell being reserialized as a different data type, as intended by R18. The synthetic fixture was corrected to leave original blank K cells genuinely empty; rerun status must be verified on the fixed HEAD and the earlier failed run retained as audit evidence.

## Pending real-release stages — NOT passed by synthetic CI
- R14 real signed Firebase token→actual SBI Flask session, gated by owner credentials in `sbi-r9-staging`; PR #154 remains separate and open.
- Verifiable complete Master v2.51 / Matrix v2.39 executable source, authoritative provenance/signature, and independent method-level QA (including waterfall last, TDS, DNM-01, service periods, GST-later, SBISA, cross-SOL approvals, duplicate/credit note and global conservation).
- FFI-001 actual fresh original workbook intake; most recent finance-authorized SOL master; historical invoices/payments must NEVER be loaded to the new production financial database by default.
- Actual v2.18 production writer, financial amount-by-amount workbook parity and 53-column report data parity.
- Isolated PostgreSQL read-only snapshot, transaction rollback proof, actual API integration and final owner Finance/security release.
- No production database writes, no real payment/invoice statuses, no AWS/Firebase cloud mutations in this stage.

**Financial Apply stays LOCKED.** A green synthetic combined test is not authorization to settle SBI receivables.
