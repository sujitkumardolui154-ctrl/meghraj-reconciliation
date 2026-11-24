# SBI R15 — Original Financial Source Preflight (Synthetic / Read Only)

Date: 2026-11-24 IST. Separate development review; no production deployment and no financial processing authorization.

## Purpose
The recovered AWS app currently accepts optional 3-column payment evidence, **not** the original financial source needed by Master v2.51 / Matrix v2.39. The historical [approved v2.18 output schema addendum] establishes original `PAYMNENT!A:L` and `Invoice Details.!A:AH` as immutable positions. A source reader must prove these shapes before any matching or database transaction.

This stage adds a **pure in-memory diagnostic reader** at `scripts/ci/sbi_r15_financial_source_preflight.py`. It requires an explicitly passed new workbook `bytes`, verifies SHA256 optionally supplied from a separately recorded source manifest, rejects missing required worksheets, checks PAYMNENT H Debit / I Credit / J Balance / K Record For Me and blank original L header. All source sheets are read-only and never saved. It reads Credit **only from original I**, not Debit H or Balance J. It counts nonblank Invoice Details. S markers as excluded, including numeric zero. It flags invalid/formula or negative credit as review, not as an eligible allocation.

**Not a replacement for FFI-001 user fresh-attachment provenance**: bytes alone do not prove when or by whom a financial file was uploaded. This preflight must never accept historical archive references as new run inputs.

## Synthetic acceptance scope
- 16 synthetic cases for exact sheets, headers, credit location, wrong format, missing source, SHA mismatch, original L, 34-column invoice shape, nonblank S, negative/formula reviews, and lack of output mutations.
- GitHub Actions runs with no Firebase credentials, AWS access, Postgres connection, financial writes or actual bank data.
- The function returns aggregate diagnostic metadata only, never transaction amounts, bank narrations or personally identifiable information.

## Explicit nonclaims
- Does NOT implement Master v2.51; no MATCH, no waterfall, no SBISA/DNM-01, no global allocation, no v2.18 writer.
- Does NOT certify current production source/master hashes, invoice identity indexes or output row parity.
- Does NOT connect to PostgreSQL or execute financial API routes.
- Does NOT supply R14 real Firebase application-session evidence; PR #154 remains independent and gated.
- Financial Apply remains LOCKED. Production main and AWS unchanged.

## Gate sequence
1. R14 live signed-token-to-application session verification in authorized separate `sbi-r9-staging` Cloud Shell: still pending.
2. R15 reader source contract synthetic checks: once CI passes, mark only the **synthetic source preflight** PASS.
3. FFI-001/FFI-002: obtain a genuinely fresh workbook with exact hashes and approved SBI SOL master privately; do not upload bank evidence into public GitHub.
4. Bring in verified full v2.51 candidate and independent QA of allocation, writer and PostgreSQL read-only snapshot; do not treat a recovered report as the engine.
5. Release only on separate Finance authorization after the complete tested implementation, rollback, report parity and human review.
