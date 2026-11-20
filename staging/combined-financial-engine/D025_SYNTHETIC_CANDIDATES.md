# D-025 — Synthetic-only SBI payment-to-invoice candidate logic

**Owner restriction: do not access, inspect, recalculate, reconcile, import, replay, or modify earlier/existing financial records. Tests use fabricated `SYNTH-INV-*` and `SYNTH-PAY-*` identities only.**

This draft adds a conservative **in-memory candidate** evaluator, not a live financial allocator. It has no database clients, Excel readers, HTTP endpoint, file paths, environment reads, cloud credentials or write functions. It does not update SBI Workspace, historical allocations, payment statuses, suspense balances or production reports.

### Explicitly implemented with fake inputs
- Unique synthetic invoice and payment identifiers and exact SOL IDs, preserving leading zeros.
- SBISA eligible invoices with blank SOL only when expressly marked SBISA, matched solely to SOL `00001` payments that are also marked SBISA.
- Exact service-period month set, including multi-month periods, and contradiction rejection.
- Invoice date versus bank date; payments outside zero-to-180-day window are held.
- 0%, 1%, 2% and 3% taxable-base TDS scenario matching using Decimal `ROUND_HALF_UP`.
- Unique same-SOL matching: an explicit invoice reference or exactly one eligible invoice; multiple eligible invoices, ambiguous rounded TDS rates, partials and conflicting references become review holds.
- Duplicate invoice IDs, duplicate payment IDs, Credit Notes, protected invoices, multiple payments against one invoice, cross-SOL and unknown amounts go to review, never settlement.
- All output candidates say `PROPOSED_FOR_INDEPENDENT_REVIEW`; no payment allocation or post is performed.

### Not yet implemented / not certified
- Full same-SOL chronological waterfall and partial allocation persistence, one-to-many/many-to-one bank credit splits, approved prior allocation protection, DNM-01 dominant nearest rule, controlled cross-SOL human approvals, bank narration parsing, verified role-scoped new evidence ingestion, runtime authentication, independent source provenance and production release.
- No existing financial data may be used to fill these gaps. Additional verification is **synthetic-only**.
- D-025 is stacked on source-only D-024 PR #121 and D-023 PR #117 (both drafts when this stage began). A passing CI is **not** approval to deploy this code to the live Workspace.

### Synthetic QA
`python -m unittest discover -s staging/combined-financial-engine/tests -p 'test_*.py' -v`

`python staging/combined-financial-engine/synthetic_only_probe.py --synthetic-selftest`

**CANONICAL_ENGINE_COMPLETE=NO; LIVE_DATA_ACCESSED=NO; HISTORICAL_RECOMPUTATION=PROHIBITED; FINANCIAL_WRITES=NO; AWS_APPLICATION_DEPLOYMENT=NOT_PERFORMED.**
