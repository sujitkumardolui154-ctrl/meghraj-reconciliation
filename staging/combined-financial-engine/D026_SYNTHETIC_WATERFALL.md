# D-026 — Synthetic full/partial/split payment waterfall simulation
Date: 2026-11-21 · Workstream D · Logic-only owner instruction

## Scope
A purely in-memory simulation of SBI-style full, partial, and multi-invoice bank-credit allocation using fabricated `SYNTH-INV-*` and `SYNTH-PAY-*` records. It cannot read original financial books, load a file, call an API, connect to a bank or database, write existing allocations, or change production reports.

`synthetic_waterfall.py` imports strict D-025 synthetic validators. Every invoice and payment must be tagged `source_kind="SYNTHETIC"` and synthetic-only mode must be explicitly enabled. Other identifiers are rejected. `approved_tds_rate` (0/1/2/3) and `simulation_priority` (positive integer) are mandatory **scenario inputs**; there is no attempt to infer true approved invoice rates or actual branch priority from historical data. Decimal ROUND_HALF_UP calculates net synthetic receivable without write-offs.

The full/partial/split flow is atomic per **fabricated payment**: if a payment would overrun eligible net balances, the whole payment goes to review and no temporary balance is changed. Duplicate invoice and duplicate payment IDs, protected cases, credit notes, cross-SOL, SBISA identity conflicts, contradictory service periods, >180-day or early payments, no reference without express opt-in, ambiguous priority and missing period evidence are held. Multiple payments may reduce a *temporary in-memory* invoice balance until complete. Multiple invoices can be processed in a caller-supplied unique synthetic order only when a no-reference payment explicitly opts into synthetic FIFO and has narration-period evidence.

All outputs remain `SYNTHETIC_WATERFALL_SIMULATION_ONLY` and `SYNTHETIC_SIMULATION_NOT_APPROVED`. No result certifies a payable balance, invoice status, financial posting, settlement or original-record parity.

## Missing for complete production engine
- Authenticated new-payment evidence upload and independent post-activation receipt ledger.
- Approved live precedence and accounting for partial/posting, DNM-01 nearest dominant, prior allocation preservation, TDS rate source provenance, conflict/credit-note evidence, error cases, and role-controlled reconciliation approval. No automatic historical scan or replay is allowed.
- Host runtime isolation, production auth, actual AWS staging/cutover and owner release approval.

## QA commands (synthetic fixtures only)
```
python -m unittest discover -s staging/combined-financial-engine/tests -p 'test_*.py' -v
python -m unittest discover -s staging/mxp-gst/tests -p 'test_*.py' -v
python staging/combined-financial-engine/synthetic_only_probe.py --synthetic-selftest
```

**HISTORICAL_CALCULATIONS=PROHIBITED; SYNTHETIC_SIMULATION=YES; REAL_ALLOCATIONS=NONE; AWS_DEPLOYMENT=NOT_PERFORMED; PRODUCTION_FINANCE_WRITES=BLOCKED.**
