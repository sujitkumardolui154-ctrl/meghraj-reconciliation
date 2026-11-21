# NEW engine 21 11 2026

**Project:** SBI Financial Reconciliation  
**Build revision:** v0.1 — synthetic-only

**Build date:** 21 November 2026  
**Specification basis:** Master Rulebook v2.51 / DIL Matrix Agent v2.39, OUT-SCHEMA-V218-001.  
**Financial permissions:** NONE. This package cannot read real banking data, access historical data, write reconciliation statuses, or post financial allocations.

## Execute the standalone fabricated demonstration

Requires Python 3.11 or newer; zero third-party dependencies.

```sh
python demo.py
python -m unittest discover -s tests -v
```

Everything is contained in memory. There is **no CLI option to open an XLSX, database, historical register, live bank feed or uploaded evidence**. The only accepted source tag is `SYNTHETIC`; invoice IDs must be `SYNTH-INV-*` and bank identifiers `SYNTH-UTR-*`. All dates are explicitly checked against a supplied simulated activation cutoff. All actual financial writes are impossible from this module.

## Implemented decisions (proposals, NEVER settlements)

- Original invoice gross = taxable + CGST + SGST, exact 2-place Decimal validation.
- TDS percent is an explicit approved synthetic fixture input: 0/1/2/3%, computed on taxable with `ROUND_HALF_UP`; no TDS rate inference or writeoff.
- Exact literal SOL strings and client-name equality. No unapproved branch normalization or unsupported parent/child cross-SOL.
- SBISA collection payment under SOL literal `1` can match a blank-SOL invoice only when both are explicitly SBISA, the verified client matches, and all other eligibility rules pass.
- Source/master/bank proof flags must be explicit booleans. **These fabricated flags are not real-world authentication.**
- Protected prior allocations, populated original invoice paid marker (including numeric zero), duplicate invoice numbers, Credit Note review, contradictory invoice references and service periods are held.
- Payment and invoice must both be dated on/after the simulated cutoff; invoice cannot post-date bank credit; interval <=180 days.
- `AUG-26`, `August 2026`, `08-2026`, `Mar-May 2026` and `March to May2026` narration formats supported as bounded evidence. Unknown/multiple narration periods fail closed or hold.
- Explicit invoice reference: may generate full or partial proposals; explicit multi-invoice ordered references support atomic in-memory waterfall.
- Unreferenced payment: only a **unique exact remaining-net** candidate can be proposed; ambiguous or approximate DNM-01 candidates are **held for review**, not automatically allocated.
- Same synthetic invoice may receive multiple distinct partial payments in the same simulation. Repeated UTRs are held. One payment is applied to the temporary balance only after its entire proposed amount fits.
- GST narration is not automatically invalid; GST-only/baselined-excluding-GST deduction scenarios require additional rule-source and authority verification before automatic proposals.

## Direct API

```python
from sbi_engine import evaluate
report = evaluate(fake_invoices, fake_payments,
                  activation_cutoff='2026-11-21',synthetic_only=True)
```

`report` is a JSON-compatible dictionary with `proposals`, `holds`, `remaining_net`, source/date flags and explicit `financial_writes=False`, `production_approved=False`, `actual_financial_status=NOT_ASSIGNED`.

## Production integration still MISSING (do not bypass)

1. **FFI-001 trusted current-run upload** and **FFI-002 exact two-sheet structure** before any real data read; the existing three-column AWS Payment Evidence upload is *not* the authoritative bank statement.
2. Trusted bank date, unique UTR, server-enforced activation cutoff, bank posting authority, approved SBI master and client provenance, verified invoice source, and permitted new-only invoice population. Boolean flags in synthetic fixtures are not substitutes.
3. Source-level implementation of all approved GST-later/base-only methods, conditional parent-child exception evidence, exact MXP reference policy and DNM-01 adjudication; any unresolved method must remain review.
4. Separate durable **new-only** transactional ledger with unique UTR, source hash, allocation conservation, protected previous settlements, idempotency under concurrency, immutable audit events and role approval. No historical ledger must be scanned or migrated to initialize it; a complete new-only opening boundary requires separate approved governance.
5. Corrected OUT-SCHEMA-V218-001 workbook writer: the archived candidate with main code SHA256 `85606f226ebb7b6555a648386021b3df2765d29c9f37312d499029b335b0719b` was QA-failed over numeric/text identifier fidelity and must not be reused unchanged.
6. Existing AWS login/CSRF, upload and report integration, one mandatory independently verified synthetic end-to-end QA + rollback gate, and explicit owner Finance approval **before** enabling Apply.

**This is a fresh working core, not a production-ready engine. No real source or financial values were processed.**

## References actually reviewed

- User-uploaded `FINANCIAL_ENGINE_FIX_PLAN_2026-10-28.md` and `DIL Financial Engine — Step-by-Step Repair Blueprint (v2.51, staging).docx` (specifications; not executable).
- Uploaded `ENGINE_BUILDER_SB18_PRE_BC_CHAIN_REMEDIATION_20261028_1939IST.zip` (SBISA review-only reference).
- Uploaded `OUT_SCHEMA_V218_STAGING_BUILDER_20261028_1932IST.zip` (schema and known writer QA failure; no writer code copied into this build).
- Library `ENGINE_BUILDER_GLOBAL01_W13_20261031_101756IST.zip` (synthetic-only TDS, period, SOL, DNM-01 and global competition review reference).
- Uploaded `SBI-Reconciliation-v2.51-20261121T135552Z-1-001.zip`: only documentation and ZIP file names inspected; **the four financial XLSX members were never opened**.

Existing real `.xlsx` files in the working directory or archive are intentionally outside this build's inputs and tests.