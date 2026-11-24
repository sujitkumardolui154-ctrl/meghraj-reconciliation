# R16 — Source-to-SOL master identity shadow preflight | 24 November 2026

**Environment**: GitHub development only; private financial execution remains BLOCKED. The purpose is to pin exact original workbook and master-byte hashes, identify identity conflicts and duplicates, and **never** perform an allocation or write.

## Source basis and approved limits

- Previous R15 original-workbook source preflight (16 synthetic tests) has been merged to development. This R16 code composes R15 via an in-memory read-only function.
- Historic SBI_SOL_Branch_Master_FINAL.xlsx inspected privately for **column structure only**, without copying values to GitHub: sheet `Clean Branch Master` has `Official Branch Name` and `SOL ID`; legacy file has other search-alias columns. **Historic archive file is not an automatically approved latest master**.
- `Invoice Details.` confirmed source contract: G `Branch Code`, H `Client Name`, M `Invoice No`, and S nonblank protected. Payment credit is only `PAYMNENT!I`. Source preserves original `PAYMNENT!A:L` and `Invoice Details.!A:AH`.
- The correct master and original source must be provided privately by an authorized host with separately approved SHA-256 provenance. Exact digest equality does not itself prove owner approval, freshness, or bank authenticity.
- SOL is compared as **exact text**. Numerical SOL cells, padded numerical equivalence and conflicting official names trigger holds; leading zeros are never stripped or auto-matched.
- Proper client names must match a single verified official branch name exactly in this *shadow*. Legacy aliases do not grant automatic status. Generic `SBI`/`STATE BANK OF INDIA` is never an auto-approved branch identity.
- Duplicate invoice numbers are quarantined and a nonblank S stays protected. A matching SOL/name is NOT payment evidence or a posting decision.

## Implementation

`scripts/ci/sbi_r16_master_identity_shadow.py` provides:
`shadow_identity_preflight(source_bytes, master_bytes, expected_source_sha256=..., expected_master_sha256=...)`.

Purely diagnostic response: source/master hashes, master ambiguity counts, invoice number duplicate groups, text SOL and official-name exact-shadow counts, protected-S counts, and safety flags. No raw branch names, invoice numbers, account/bank narrations or amounts are returned.

Independent synthetic tests validate refusal for missing/incorrect hashes, exact master sheet/header, type-safe SOL, collision/zero-padding, client mismatch, duplicates, formulas, missing invoice data and protected S.

## Guarded continuation

1. **R14** real signed Firebase token accepted by actual Flask session in authorized staging: NOT YET VERIFIED. Draft PR #154 is separate.
2. **R16** source/master identity shadow synthetic QA may PASS without R14, but live financial processing still BLOCKED.
3. Approve an exact branch master version and provenance digest; do not adopt the historical library workbook implicitly or commit actual bank/branch records publicly.
4. Require fresh user-submitted `PAYMNENT` and `Invoice Details.` financial source with original bank row I credit, immutable A:L/A:AH, and signed/current run source attestation.
5. Recover complete version-pinned v2.51 allocation rules and audit source from private archive. Independently test SBISA, DNM-01, period parsing, TDS, cross-SOL approvals, one global uniqueness ledger, waterfall LAST, GST/duplicate final gate.
6. Separately integrate and QA exact v2.18 output writer and read-only database snapshot before any financial writer.
7. Obtain independent Finance/security approval and explicit cutover release. **Financial Apply LOCKED** throughout R16.

**Do not confuse R16 identity shadow counts with MATCH, OK, settlement or database synchronization.**
