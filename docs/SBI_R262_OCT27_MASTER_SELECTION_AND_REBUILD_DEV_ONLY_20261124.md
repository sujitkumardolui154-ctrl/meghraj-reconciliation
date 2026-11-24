# SBI Stage R26.2 — Owner-selected October master, controlled engine rebuild (24 Nov 2026)

## Owner decisions recorded
- **SOL master:** Owner selected historical **27 October 2026** \`SBI_SOL_Branch_Master_FINAL.xlsx\` as the **development reference**. Exact verified file SHA-256: \`4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388\`. Connected Drive file ID: \`1BVacBQCjElvDUBusB0yBPjnjOltEb2wp\`.
- **Engine approach:** Controlled **rebuild**, not promotion of archived v2.22/v2.10 partial code and not recognition of a blueprint as runnable v2.51.
- **Excluded 149 source records:** **REVIEW ONLY**, no restoration, deletion, or reinterpretation by this stage.
- **Permission:** Development-only source/tests and read-only source review. Never enable Finance Apply; no production AWS/Firebase/PostgreSQL writes; no production deployment.

## Verification
Private read-only source inventory verified the October 27 master with the exact historical SHA and compared it to the November 20 copy. The \`Clean Branch Master\` official SOL/name mapping is the same in both available files, but **November-specific extra content and suggestions are not imported into the selected October version**.

October 27 master still contains:
- 1,493 exact valid SOL identifiers across 1,503 master identity rows
- 10 master rows with blank/invalid SOL identifiers, **including an SBI Fund Management Krishnanagar row** whose SOL must not be guessed from another copy
- 3 distinct text-SOL numeric-equivalence collision groups
- 16 official name keys that appear under multiple distinct SOL identifiers

The owner selection pins a **reference version**, not automatic individual-row approval, independent signed authority, or exception waiver. No leading-zero collision can be numerically merged.

## Private 149-row owner decision register

Private XLSX: \`SBI_R262_Oct27_Master_149_Exclusion_Owner_Review_2026-11-24.xlsx\`, **not uploaded to public GitHub**. It includes original source Excel row numbers, source invoice/SOL/name values and unresolved owner-decision columns:
- 111 originally removed numeric-format SOL invoice rows (95 exact master-key candidates, 10 unique padded official-name candidates, 6 padded-name mismatch holds)
- 23 duplicate-invoice-group source rows across 9 groups
- 15 original nonnumeric bank-credit entries (bank source should verify headers/notes)
- 10 unapproved blank-SOL master rows, 3 padded collision groups, 16 repeated official-name-to-different-SOL groups

**No original or cleaned user financial file has been rewritten**. The original, cleaned and 149-row audit snapshots were independently SHA-verified in the private runtime, with no source changes.

## Rebuild sprint R26.2 — implemented scoped planner

Source: \`scripts/ci/sbi_r262_rebuild_candidate_planner.py\` under \`scripts/ci/\`, imported only by *synthetic unit tests*. It is explicitly **not** a production module or complete v2.51 settlement engine.

- Inputs restricted to \`SYN-MXP-*\` / \`SYN-PAY-*\` identifiers, a small synthetic-only official-master fixture, explicit fixture digest and forced \`financial_apply=LOCKED\`.
- Strict exact original textual SOL and synthetic official name; no padded remap, aliases, live master import, external source, role escalation or financial database connection.
- MXP exact-reference + independent R26 TDS/gross/period/date/paid-marker review; incorrect or contradictory references held.
- Provisional review-only DNM-01 hypothesis: same SOL, name, chronology, complete service period, ≤180 days, candidates within ₹10, best ≤₹1, second ≥₹2 separated; no automatic OK.
- Separate global capacity review of exact-reference hypothetical edges; if multiple payments exceed one invoice or original source row IDs conflict, proposals are held. No actual reservations persist.
- \`FINANCIAL_APPLY=LOCKED\` is mandatory and cannot be overridden by caller. No status writer, v2.18 Excel financial writer, real ledger, API, AWS, Firebase, production DB, cloud, or external connector.
- 30 new synthetic test cases plus R15–R26 existing independent safety suites. Only exact GitHub CI logs can confirm total pass.

## Explicitly NOT implemented or certified

Full partial payment allocation; approved SBISA and cross-SOL relationship handling; GST-only/later ledger adjudication; priority-controlled DNM integration into one certified master ledger; finalized waterfall-LAST actual allocation; duplicate **payment** final decision; linked credit-note and financial reporter; production-grade v2.18 monetary Excel writer; live staging Firebase→Flask signed session, real PostgreSQL authorized staging/rollback; signed Finance/security and owner cutover.

Actual R26.2 phase completion condition is **synthetic scoped unit tests passed, no writes, and correct owner version pinned**. It cannot certify the full Master v2.51 / Matrix v2.39 until complete implemented source, actual financial parity, independent verification and signed release authority exist.

**Status:** \`R262_REBUILD_DEVELOPMENT_SCOPED_ONLY\`; \`FULL_V251_CERTIFICATION=BLOCKED\`; \`FINANCIAL_APPLY=LOCKED\`; \`PRODUCTION_DATABASE_WRITES=0\`.
