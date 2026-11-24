# SBI Stage R25 — Private Source & SOL Master Combined QA (24 Nov 2026)

**Decision:** `R25_READONLY_SOURCE_MASTER_QA=PASS_WITH_OWNER_EXCEPTIONS`  
**Production:** `FINANCIAL_APPLY=LOCKED`; **NO** payment allocation; **NO** production writes; **NO** source mutation.

## Scope and evidence treatment

R25 audited the user's newly uploaded SBI original workbook, the previously cleaned working copy, the separate 149-row exclusion register, and **two distinct existing Google Drive copies** of `SBI_SOL_Branch_Master_FINAL.xlsx`. All private source workbooks, full invoice/payment lines, invoice identifiers, bank narration, monetary amounts, source SHA fingerprints, and 12,000+ row-specific exception entries remain **in private conversation artifacts only**, **not** in the GitHub repo or CI.

The personal R25 eight-tab evidence workbook is named `SBI_R25_Combined_Source_SOL_Master_QA_2026-11-24.xlsx`. GitHub has **no** original bank or customer data from this audit. The QA workbook can be independently verified by its private manifest.

## Read-only workbook integrity

- Original source invoice rows: 14,007; cleaned invoice rows: **13,873**; excluded 134.
- Original source payment rows: 14,898; cleaned payment rows: **14,883**; excluded 15.
- Exclusion register: **149** rows = 23 rows from 9 duplicate-invoice groups + 111 numerically typed SOL invoice rows + 15 nonnumeric payment-credit rows.
- Every retained **nonformula** source value was checked in source sequence; **0** cell-value mismatches.
- **124,567** retained invoice formulas, **0** disappeared or added, **0** cached result differences, and **0** literal `#REF!` formula references in the private audit. Row-based references have changed because rows were deleted. This is a structural comparison, **not** independent invoice GST recalculation or approved tax parity.
- Cleaned data show **0** repeated invoice number groups; original repeated groups remain in the immutable exclusion register.
- All cleaned invoice original S paid-marker/date cells are blank. Blank original S does **not** establish that all invoices are unpaid; prior financial allocations require an independently verified authoritative ledger.

## Two available masters (NOT owner-approved)

- Newer version: Drive ID `1BWLwiISc3IMcG6uEgkzptyPODNgu2hTj`, modified **2026-11-20**, 189,014 bytes, includes extra `Sheet1` with review suggestions.
- Older version: Drive ID `1BVacBQCjElvDUBusB0yBPjnjOltEb2wp`, modified **2026-10-27**, 180,325 bytes.
- The `Clean Branch Master` official SOL/name records are identical in both versions. Each has 1,503 identity rows, **1,493** valid unique SOL keys, **10** missing/nontext SOL rows, **3** zero-padded/equivalent SOL collision groups and **16** cases where one normalized official name maps to multiple SOL keys. No same-exact-SOL conflicting official name in the examined rows.
- The newer copy's extra review worksheet is **not** automatically approved; no owner-approved master authority supplied.

## Strict source-to-master QA (exact text SOL; official name only)

| Input population | Count | Condition |
|---|---:|---|
| Cleaned invoices | 13,873 | Total |
| Exact SOL and official client name | 6,535 | Identity candidate only, never financial paid |
| No exact SOL but unique zero-padded SOL and official name | 6,596 | **REVIEW ONLY** |
| No exact SOL but padded name differs | 111 | HOLD for client/alias |
| No padded SOL candidate | 41 | HOLD |
| Exact SOL with different client name | 482 | HOLD; 309 match a whole master alias field, 173 require other review |
| Invalid/non-digit text invoice SOL | 108 | HOLD; non-SBI/credit-note routing needs verification |
| Cleaned payment rows | 14,883 | Total |
| Exact SOL exists in master | 9,618 | 8,540 exact official names; 581 blank bank client name; 497 differ |
| Missing exact SOL but unique padded and name exact | 4,956 | **REVIEW ONLY** |
| Unique padded SOL but name differs | 120 | HOLD |
| No padded SOL candidate | 189 | HOLD |

These are **evidence categories**, not disjoint financial settlement batches across invoice and payment. The financial engine is not run.

**Critical exception from prior cleaning:** 111 numerically typed invoice SOL rows had been removed. Of those, **95** have an exact master key, **10** have a unique padded master SOL plus exact official name, and **6** require additional name review. Thus **105** excluded rows may have fully valid master identities; deleting those solely because Excel stored SOL numerically is not a sufficient financial validity judgment. The user must decide restoration after original evidence review; R25 did **not** restore them.

## Review-only development guard

New pure `scripts/ci/sbi_r25_sol_identity_review.py` and synthetic `tests/test_sbi_r25_sol_identity_review.py` cover text SOL identity, unique leading-zero proposals, ambiguous collisions, generic names, source numeric SOL refusal, conflicting master entries, and immutable original SOL. No real bank source, Master v2.51, approved alias engine or payment allocation is wired into that helper. All outputs state that master authority and financial release are **not** verified.

## Remaining external approvals

1. Master owner must select/verify latest authoritative master and resolve 10 blank-SOL rows.
2. Approve/reject zero-padding proposals without overwriting source SOL or merging 3 padded-collision groups; approve exact aliases via documented source.
3. Review 111 excluded numeric-format SOL invoice rows and potential restoration from immutable source; review 23 duplicate-invoice rows and 15 nonnumeric-credit rows.
4. Resolve remaining name mismatches and unrecognized SOL, including non-SBI and protected historical allocations.
5. Independently certify **complete executable v2.51 / Matrix v2.39**, approved financial source, full rule/ledger oracle, v2.18 financial writer with amount parity, authorized real staging Firebase→Flask session, actual AWS staging role permissions and rollback, Finance/security user signoff.
6. Any production cutover needs a separate explicit approval. **FINANCIAL APPLY REMAINS LOCKED.**
