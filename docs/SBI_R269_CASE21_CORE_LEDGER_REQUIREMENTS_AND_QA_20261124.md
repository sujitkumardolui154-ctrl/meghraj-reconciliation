# R26.9 — Case 2.1: Master-owned core cash ledger (development only)

## Authoritative owner rules carried forward
- Master v2.51 owns one global allocation register; Matrix Agent v2.39 proposes candidates only.
- Historical files are reference/testing inputs, never a requirement to match fresh invoice/payment row counts or copy previous OK statuses. Case 1 approved semantic payment header normalization remains intact.
- Selected 27 Oct SOL master is a development reference; unapproved aliases and the 149 historical excluded rows are **not** automatically restored or joined.
- Original invoice S nonblank and original bank K nonblank are protected, including numeric 0. No financial Apply, database writes or production release.

## Case 2.1 new component
- `scripts/ci/sbi_r269_core_cash_ledger_dry_run.py` is a standalone deterministic pure in-memory cash reservation core. InvoiceCapacity (invoice/no, original row, gross, S), BankCapacity (bank id/source row/credit/K), MatrixProposal (bank, invoice, amount, method, evidence), and GlobalAdjudicationBoundary (explicit waterfall-last gate).
- Rejects duplicate invoice/payment IDs and source rows, inconsistent money representation, nonpositive/sub-paise amounts, protected S/K markers, unknown references, unapproved methods, DNM provisional reservation, missing evidence, overuse of any bank credit, over-reservation of invoice cash capacity, duplicate bank-to-invoice edges, waterfall before boundary and earlier matching after boundary.
- Reserves only shadow cash and returns bank-by-bank unused credits, invoice-by-invoice **cash coverage gaps (not certified receivables)**, ordered provenance edges and three distinct SHA256 manifest strings. Input SHA strings are declarations from the caller, NOT verification of external bank origin or Finance signatures.
- Enforces `sum(bank cash)=sum(shadow reserved)+sum(unassigned)` and `sum(invoice gross)=sum(shadow reserved)+sum(invoice cash gaps)`; no tolerance-based writeoffs or ambiguous float amounts. All records are immutable and the ledger does not write files.
- The method catalogue is provisional: exact MXP, same-SOL, partial, GST component, SBISA, cross-SOL, waterfall. It checks only **cash capacity** here; independent eligibility, double-counted TDS/GST/credit notes, payment duplicate adjudication and true settled status are NOT implemented by this primitive.

## QA
48 adversarial synthetic-only unit tests cover atomic global conservation, multiple payments per invoice, a single payment spanning two invoices, over-credit, over-invoice, protected source rows, SHA/plan hash failure, illegal method order, provisional DNM hold, no status or source mutation.
Combined GitHub workflow reruns the existing 755 synthetic/offline/disposable PostgreSQL tests plus 48 new tests. GitHub contains no original SBI customer financial rows, authorizing master or credentials.

## Remaining Case 2 completion sequence
**2.2** Connect approved Master and Matrix candidate/eligibility decision interfaces to this ledger; do not let self-asserted evidence_ref authorize settlement.
**2.3** Integrate approved method priority and single global adjudicator.
**2.4** Derive tested payment classifications (`OK`, `SUSPENSE`, `Duplicate Payment`) ONLY from a complete independently verified financial ledger; preview remains locked.
**2.5** Exact per-bank/per-invoice forensic allocation receipts with TDS/GST/credit-note components and document proofs.
**2.6** Independent oracle on same synthetic controlled source and an authorized isolated real-shape dataset; exact source hashes and complete method coverage.

**Case 2.1 status is development component only, not complete Master v2.51/Matrix v2.39 certification.** `FINANCIAL_APPLY=LOCKED` and production unchanged.
