# SBI R26.5 — Independent financial parity gate (24 Nov 2026)

## Decision / authority
**User requested R26.5, development-only.** Scope: independent full-engine integration / financial parity readiness checks. **The complete certified v2.51 / Matrix v2.39 executable is STILL ABSENT** from the directly inspected GitHub development tree. Therefore R26.5 cannot certify real bank payment settlements or a signed financial writer. The new tests are an incremental, falsifiable **independent synthetic arithmetic witness**, not a complete real source engine.

Owner-controlled earlier decisions are unchanged:
- October 27, 2026 `SBI_SOL_Branch_Master_FINAL.xlsx` is the selected *development reference*; verified private historical SHA256 `4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388`. The master was NOT loaded or committed in public CI.
- Original and cleaned SBI bank workbooks preserved. **149 excluded rows remain under review** (111 numeric-SOL invoices, 23 invoices in nine duplicate groups, 15 nonnumeric payment Credit entries), no reinstatement/removal.
- `FINANCIAL_APPLY=LOCKED`; zero real financial allocations, real database writes or production deploy.

## What R26.5 adds
- `scripts/ci/sbi_r265_independent_parity_gate.py` separately computes bank-credit utilization, invoice-side illustrative cash + TDS + credit-note effects, and GST-only cash components directly from three SHA-pinned, fictitious SYN-* fixtures.
- The reference arithmetic is **separate from the R26.4 monetary calculation path**. It compares every synthetic invoice/payment value, totals, and global conservation equations against R26.4 candidate output. A mismatch fails closed.
- Tests monkeypatch forged R26.4 results (cash payment balance, invoice gap, TDS total), and assert that the independent witness detects each incorrect result. A candidate cannot self-claim production release, certified full v2.51, real v2.18 writer money parity or database writes.
- When earlier R26.3/4 evidence is contradictory or lacks synthetic proof, the independent gate returns HOLD without claiming monetary parity; it does not reclassify any payment as OK.
- An R20 strictly synthetic Excel writer roundtrip is tested for protected original `Invoice Details.` columns J Invoice No and M SGST, original `PAYMNENT` I Credit and S paid marker preservation. **This remains structural, NOT real v2.18 money/value certification.**
- `release_gate_matrix()` hard-codes each real production readiness gate to false until external authorized evidence exists; synthetic tests cannot set it to true.

## Existing private source check (outside GitHub)
The private, owner-provided `source file.xlsx`, cleaned copy, 149-row audit file, historical v2.18 format reference, and selected Oct27 master are available in this ChatGPT task's private container. Hashes/row counts can be compared **read-only**, without using those real transaction rows in GitHub or for allocating actual bank receipts. These private source checks do not satisfy the fresh-source attestation required for a new production Execute and do not authorize a real money writer.

## Required before actual R26.5 full-engine parity certification
1. Complete **executable** Master v2.51/Matrix v2.39 including all scoped methods and one global allocator, built and source-hash signed.
2. Selected Oct27 master owner review/alias authority and decisions for 10 missing SOL master rows + 3 padded collisions and the 149 excluded source records (105 potentially valid numeric-SOL invoice identities).
3. Identical immutable original bank source snapshot for both candidate and independently developed oracle, owner-proven original Credit I, invoice J/M and protected S/K markers, independent real-finance provenance.
4. Independent correct accounting of real TDS certificates, GST-later and credit-note tax breakdown, same-SOL/partial, SBISA/cross-SOL authority, DNM, parent/child, global uniqueness, waterfall-last and no false OK.
5. Correct real v2.18 writer monetary values while preserving PAYMNENT A:L, Invoice Details. A:AH and writing only model M:W and AI:AM. Independent 53-column report **value** parity, not just heading validation.
6. Real authorized staging Firebase→Flask application proof, actual isolated AWS PostgreSQL read-only role/backup/rollback, Finance and security signed release matrix and explicit user production cutover.

## Conservative completion label
`R265_SYNTHETIC_INDEPENDENT_PARITY_QA=SCOPED_ONLY`; `FULL_ENGINE_REAL_SOURCE_PARITY=BLOCKED_EXTERNAL_EVIDENCE`; `FINANCIAL_APPLY=LOCKED`; `PRODUCTION_WRITES=0`.

GitHub branch under review and CI tests do not certify live reconciliation. No private SBI customer data, names or amounts were committed.
