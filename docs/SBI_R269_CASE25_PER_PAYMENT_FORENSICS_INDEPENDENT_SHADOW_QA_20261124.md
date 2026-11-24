# R26.9 Case 2.5 — per-payment forensic evidence and independent shadow allocation QA

**24 November 2026. Development-only. Owner Option B (each newly uploaded workbook separately scoped).**

## Exact scope
This case independently recomputes *cash-only hypothetical reservation math* for the already integrated Case 2.1 → 2.2 → 2.3 → 2.4 chain. It does **not** claim full executable Master v2.51 / Matrix v2.39 settlement. No public SBI rows, no real private workbooks, no production database, no Excel writer and no financial status assignment. All successful findings describe only a caller-supplied normalized review snapshot with declared source/master SHA-256.

- `scripts/ci/sbi_r269_case25_forensic_independent_shadow_oracle.py` does **not** call the Case 2.1 allocator or Case 2.3 planner to calculate totals. It independently sums each source bank amount, each bank-to-invoice proposed edge and invoice capacity using exact Decimal paise.
- Verifies exact one-workbook scope, original protected bank K and invoice S, individual source row and invoice identity, SHA-pinned Case 2.3 Matrix evidence, normalized workbook digest, deterministic plan digest, method, bank/invoice row projections, per-payment unused cash and global two-sided cash conservation.
- Refuses duplicate/repeated edges, cross-upload evidence, phantom invoice/bank references, overdrawn credits, sub-paise money, non-reviewed methods, provisional DNM reservations and held/contested/quarantined allocations. Reconciles all independent sums to Case 2.3 output.
- Confirms Case 2.4 every source bank row gets exactly one `*_CANDIDATE` or `REVIEW_REQUIRED`; forbids any actual Column M value and any status/cash contradiction. A candidate from caller-supplied `StatusEvidence` remains **uncertified**, even when caller sets all booleans true.
- Emits immutable-input-derived per-edge and per-payment SHA-256 audit fingerprints and a whole-batch forensic manifest. **These hashes are integrity fingerprints, not digitally signed independent financial approvals.**
- Records `shadow_invoice_cash_gap_not_receivable`; never treat a TDS-related gross-minus-cash difference as a verified receivable or write-off. No approved history is imported from other workbooks; no actual prior-settlement ledger is reconstructed.

## Required forensic evidence for a later *real* payment release
Before any final `PAYMNENT!M` classification or allocation, authorized private operators must independently verify original XLSX bytes and storage custody, original bank credit/transaction UTR and duplicate-event uniqueness, approved SOL client identity and service period, invoice outstanding and protected K/S prior ledger, actual TDS certificate and taxable base (0/1/2/3% HALF_UP where approved), GST receipt and credit-note accounting, SBISA/cross-SOL documentary authority, multi-invoice waterfall/partial ledger, dispute/duplicate holds, exact v2.18 original A:L and status output parity, and recorded Finance/security approval plus a tested rollback. Original 53-column headers remain frozen.

**Case 2.5 independent math does not verify any of those external documents by itself.** Successful development QA can close the synthetic forensic-method milestone only, not real-source reconciliation parity, outstanding final status, signed financial release or production deployment.

## Synthetic QA receipt
42 Case 2.5 adversarial tests added; the combined workflow includes existing 962 Case 2.1–2.4/offline/disposable database tests, so **1004 expected**, subject to actual exact-head GitHub Actions evidence. Reject any CI receipt that self-declares real-money certification. Synthetic tests are hosted only on the isolated development PR; use run ID/commit SHA from Actions rather than an invented pass.

`FINANCIAL_APPLY=LOCKED`; `PAYMNENT!M=NOT_ASSIGNED`; `REAL_DB_WRITES=0`; `PRODUCTION_RELEASE_AUTHORIZED=False`.
