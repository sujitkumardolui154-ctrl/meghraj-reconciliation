# D-027 — New Payment Evidence Intake: future-only, synthetic-only source contract
Date: 2026-11-21 · SBI Reconciliation Workspace, Workstream D

**Owner-mandated invariant:** Deploy approved rules/logic only. Do not read, recalculate, reconcile, migrate, backfill or modify earlier/existing invoice, bank-payment, credit-note, GST, allocation or suspense records. Regression QA uses fabricated input only.

## What has been coded
- `synthetic_payment_evidence.py` adds a strict **in-memory PREVIEW** for fabricated new payment evidence, not a functioning AWS upload feature.
- The modeled bank source is the `PAYMNENT` original A–L cells, exactly 12 immutable strings; **Column I** (index 8) is the only valid bank credit field. Amount must be strictly positive decimal with up to two fractional places, no formulas, negatives, zero, NaN, grouping separators or implicit rounding.
- Required synthetic metadata: mock payment identifier and UTR, explicit SOL (or blank SOL with explicit SBISA marker), bank credit date, narration, optional synthetic invoice reference, and optional supporting-file *name + declared SHA256 only*; proof files are not opened or stored.
- An explicit fabricated activation date and submission date are required. Payment credit dated earlier than activation, or later than submission, is rejected. In the real application, **these dates and the actor role MUST come from trusted server/auth context**, never from a browser or upload field.
- Detect duplicates and UTR conflicts within the incoming synthetic batch and against a supplied fabricated preview receipt index; duplicate/conflicting rows are held, not imported. Generates an **ephemeral SYNTH-RCPT** fingerprint/receipt for approved preview rows only. In production this would require private durable storage and transactional uniqueness, not an in-memory dictionary.
- Output contains row ordinal and reason codes, without original bank fields, narration, credit values or UTR. No file reads, uploads, financial calculations, invoice matching, posting, persistent receipts or other database operations occur.
- All callable input paths require `synthetic_mode=True`, `SYNTH-*` identifiers and a mock-only role. Live account identifiers and older bank records are rejected.
- D-027 is packaged into the allowlisted source-only archive and exercised by the isolated `--synthetic-selftest` smoke probe.

## Planned real Workspace experience (NOT deployed)
A new **Payment Evidence** tab would let an authorized user submit fresh bank evidence after activation; show original A–L / Credit-I mapping preview, per-row error/duplicate status, source hash, signed receipt and a review queue. Bank uploads must not use the existing invoice `Database Update` route. Uploaded evidence would be stored in an append-only evidence store **separate from prior financial ledger and allocations**. Only owner-approved future finance flows may operate on new evidence; historical entries are out of scope forever without a new owner instruction.

## Missing release prerequisites
1. An authenticated, server-controlled acceptance timestamp, source-file parser and anti-malware/type validation for new bank evidence.
2. Private append-only evidence store, verified idempotency, transactional UTR uniqueness, retention and per-role authorization/audit trail.
3. Explicit approval/rejection workflow and documented rollback that never touches earlier records.
4. Complete canonical reconciler rule precedence, not merely synthetic reference matching.
5. Host isolation and signed immutable code package, no legacy data mounts, DB permissions, startup backfill, old source access, or application traffic switch without owner approval.

## QA
`python -m unittest discover -s staging/combined-financial-engine/tests -p 'test_*.py' -v`

`python staging/combined-financial-engine/synthetic_only_probe.py --synthetic-selftest`

**D027_SOURCE_INTAKE=PREVIEW_CONTRACT_ONLY; REAL_PAYMENT_FILE_UPLOAD=NOT_IMPLEMENTED; HISTORICAL_PROCESSING=PROHIBITED; LIVE_FINANCIAL_WRITES=DISABLED; AWS_DEPLOYMENT=NOT_PERFORMED.**
