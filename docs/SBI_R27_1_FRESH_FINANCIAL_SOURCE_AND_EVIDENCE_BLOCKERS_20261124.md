# R27.1 — Genuine Financial Evidence Certification: Fresh Intake Preflight

**Date: 24 Nov 2026 IST | Financial execution: LOCKED | Development review only**

## Actual source discovery, not executed data

Connected Drive metadata and the previously designated SBI project archive were checked in read-only mode. Multiple historical copies of the SBI invoice/payment workbook, an "original backup", a November 2026 cleaned/flagged candidate, official branch/SOL *reference* master copies, a 23 Nov Master v2.51 / Matrix v2.39 local reconstruction REVIEW workbook, and an R21 required-evidence tracker are available.

**None was submitted as a new current-conversation executable user attachment.** The title `ORIGINAL`, `FINAL`, `MASTER` or `v2.51` is not provenance or owner authorization. Do not choose the newest Drive file; do not silently reuse the 2026-10-28 backup, historical v2.7 executed output, cleaned 149-flagged-row sheet or any historical reconstruction workbook as a new reconciliation source.

This follows the user-approved FFI-001 protected rule: a genuinely new current-run owner-designated workbook must be supplied for a financial reconciliation execution. The run is STOPPED at source-intake level and **0 real financial rows have been processed**.

## Concrete code delivered by R27.1

`scripts/ci/sbi_r27_1_ffi001_fresh_intake_structure_gate.py`:

- Requires a declared current-run *user attachment*, exact `.xlsx` ZIP signature and cryptographic SHA-256 input digest, original `Invoice Details.` and `PAYMNENT` sheet names, visible required sheets, safe XML and package paths, ZIP integrity and bounded uncompressed size.
- Explicitly rejects historical Drive, Library or Project file references as fresh input.
- Returns **structure-only candidate**, not verified bank/UTR, authenticity, header/row parity, Excel financial writer or certified current-run provenance. Host-facing boolean and declared origin are not an authenticated storage attestation.
- No spreadsheet data cells are read; no TDS, payment allocation or business matching calculations are performed. Existing `Invoice Details.` S and `PAYMNENT` A:L remain untouched. No Excel, database, AWS, authentication or financial writer interface.
- 19 synthetic OOXML refusal tests check the protected fresh-file gate, correct tab names, ZIP signature, immutable SHA input, XML entities, source tampering and financial unlock attempts.

## Exact next real-evidence steps (not yet authorized or executed)

1. **Owner fresh user attachment:** supply a newly uploaded source workbook in this exact chat, explicitly identifying it as the current intake, containing `Invoice Details.` and `PAYMNENT`. This can be a fresh re-upload of the same original bytes, but freshness cannot be inferred from a matching SHA.
2. **Byte attestation:** separately capture trusted host-provenance, true original XLSX SHA-256, file size, worksheet/header counts, protected original K and S cell coordinates, `PAYMNENT` Column I Credit, formula state, and deduplicated structural exceptions in private read-only scope. The R27.1 module alone does not verify any header/row financial values.
3. **Authoritative rulebook/master selection:** owner explicitly approve which SOL/alias master and full v2.51 / Matrix v2.39 signed executable specification applies to this intake. The currently discovered reconstruction REVIEW file is not signed executable release evidence.
4. **Private source evidence:** independently corroborate actual bank-transaction UTR uniqueness, invoice source records, service period, TDS taxable base and 0/1/2/3% rounding, GST components/receipts, partial/cross-SOL/SBISA authorizations, credit notes, previous allocations **within current workbook** and duplicate disputes.
5. **Full financial parity:** run the complete independently certified v2.51/2.39 method engine and v2.18 writer in private staging, compare per-row results to an independent Finance-approved oracle, preserve 53-column source/output contract where applicable, and demonstrate rollback, role-denied and role-authorized Firebase/DB paths.
6. **Sign-off:** authenticated independent Finance/security/owner release approvals are required. No production Apply action is present in this development phase.

## Current phase determination

- FFI-001 fresh source user attachment: **NOT RECEIVED**
- Source workbook structure real-data preflight: **NOT EXECUTED** (synthetic only)
- Full Master v2.51 / Matrix v2.39 financial parity: **NOT CERTIFIED**
- Independent real UTR/ledger evidence and 12 release gates: **BLOCKED**
- v2.18 production Excel writer and financial Column M: **NOT AUTHORIZED**
- Financial Apply: **LOCKED**, no real financial allocations or database writes.

The combined CI workflow reruns the previously confirmed **1,067** offline/synthetic/disposable QA tests and adds 19 new FFI-001 tests, so **1,086 expected**, subject to exact-head GitHub Actions verification. A green CI result validates only synthetic development controls, not real payment certification.

**Never copy any real SBI customer, UTR, account number, payment amount or original private workbook into this GitHub repository or GitHub Actions logs.**
