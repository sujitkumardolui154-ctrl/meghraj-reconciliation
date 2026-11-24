# SBI R26.4 — Financial accounting and synthetic v2.18 writer parity (24 Nov 2026)

## Scope and source approval boundary

**User authorization:** Continue the controlled development rebuild only. Owner-selected 27 October 2026 SBI SOL master remains the development reference (historical SHA-256 `4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388`). All **149 excluded financial source rows** remain on owner-review hold, with no restore, deletion or actual allocation. No actual SBI bank rows/master contents are committed to GitHub or used in public GitHub CI.

**Status:** `R264_SYNTHETIC_ACCOUNTING_QA_SCOPED_ONLY`, `COMPLETE_MASTER_V251_MATRIX_V239_CERTIFIED=NO`, `FINANCIAL_APPLY=LOCKED`, `PRODUCTION_WRITES=0`.

## Source contract and verified predecessor

- R26.3 `scripts/ci/sbi_r263_global_allocation_shadow.py` atomically validates global cash reservations and waterfall-last ordering. It is a synthetic-only shadow, **not** a settlement engine. The illustrative gross-minus-cash gap does not automatically recognize TDS.
- R18 `scripts/ci/sbi_r18_output_parity_gate.py` enforces source-protected workbook A:L and A:AH, schema M:W and AI:AM, and 53-column header contract **structurally only**.
- R20 `scripts/ci/sbi_r20_synthetic_review_writer.py` serializes actual XLSX bytes for strictly synthetic fixture and leaves every modeled bank status **SUSPENSE**. It cannot establish real financial writer accuracy.

## R26.4 implementation

New pure module `scripts/ci/sbi_r264_financial_accounting_shadow.py` with `tests/test_sbi_r264_financial_accounting_shadow.py`:

1. **Cash**: Use the R26.3 validated in-memory candidate edges; require source and plan SHA-256 and 3rd accounting-evidence SHA. Never change original or cleaned Excel bytes.
2. **Withheld TDS**: Track independently from cash. Synthetic evidence binds *exactly* one TDS hypothesis to an invoice/payment and a STANDARD or PARTIAL edge carrying an exact MXP reference. Only 0/1/2/3% taxable with `Decimal ROUND_HALF_UP`, including half-cent boundaries; repeated claims against one invoice or incorrect amount fail closed. Without separate evidence, bank cash does not imply withheld TDS.
3. **Credit notes**: Synthetic gross credit-note evidence carries a unique synthetic reference, invoice ID and issue date. Invalid duplicate/negative/over-gross notes, source-protected invoices and notes dated before invoice are blocked. Does not claim approved credit-note tax distribution or real credit-note source validity.
4. **GST later**: Separate observed GST-only candidate cash from regular cash; require the R26.3 SYN-PROOF+GST narration test, and block combined GST component cash above original invoice CGST+SGST. No real GST settlement authorization is inferred.
5. **Partial, waterfall, duplicate and conservation**: Preserve R26.3 gate, check global bank cash invariant, and require that (cash + hypothetical withheld TDS + hypothetical credit notes + illustrative residual) exactly equals the invoice's opening amount; if any source/ledger conflict, **all proposed accounting rows vanish**.
6. **v2.18 writer check**: Cross-test the R20 synthetic output's original J invoice number / M SGST and payment I credit preservation. Financial status remains SUSPENSE in the writer. This **does NOT certify real v2.18 monetary writer/output or 53-column report financial values**.

### Example (illustration, not an actual SBI settlement)

A synthetic invoice with gross/opening 1180.00 and a matching cash receipt of 1160.00 yields a **cash-only gap of 20.00**. If an independent fictitious TDS proof states 2% × taxable 1000.00 = 20.00, the **illustrative balance becomes 0.00**. Both cases return `financial_status=None`; neither is an approved bank settlement, a verified TDS certificate, nor an outstanding-balance write.

## Explicit incomplete work

- Cannot execute **Master v2.51 / Matrix v2.39** on real inputs, cannot independently verify approved SOL aliases/cross-SOL/SBISA/GST, and cannot decide real Duplicate Payment or invoice paid status.
- Real TDS certificates, customer ledger opening balance, carried-forward prior allocations, tax-specific credit-note adjustments, independent GST-paid components, and reconciliation against bank source K / invoice S still require signed provenance.
- Full real-source same-hash independent matching oracle, real v2.18 writer monetary parity, 53-column reporting value parity, staging Firebase authenticated Flask session, actual AWS PostgreSQL read-only staging/rollback, Finance/security and user cutover authorization remain pending.
- Zero private customer rows, production writes or financial Apply are included in this development-only PR.

**Release gate:** Synthetic-only CI PASS is not full engine certification and cannot lift Finance Apply.
