# NEW engine 21 11 2026 — Stage 4 Integration Foundation

**Build:** Stage 4.0 — signed new-only payment/invoice intake + durable candidate reservation ledger  
**Basis:** Master Rulebook v2.51 / DIL Matrix Agent v2.39 / v2.18 output schema, using verified Stage 3 mock modules for reference.  
**Release status:** DEVELOPMENT-ONLY. **Financial Apply remains disabled.** No user-provided historical records were loaded, edited or reconciled.

## What is implemented

`stage4_ledger.py` is a standalone standard-library Python module, with no HTTP routes or bank/Firestore/Firebase/PostgreSQL connectors. It provides:

- A strictly versioned **server-issued signed evidence envelope** for each new payment and invoice. An HMAC verifies that an internal upstream evidence gateway signed the exact source metadata; changed dates, SOL, amount, UTR, source SHA, source row or invoice are rejected. **This is NOT proof that SBI originated or authenticated the bank record.** The actual bank-source verifier is still absent.
- Exact existing upload shape `Description | SOL ID | Credit Amount`, bound by SHA-256 to the signed evidence and its original `PAYMNENT!I` bank-credit lineage. Never treat `PAYMNENT!H` Debit as credit.
- Server-controlled activation cutoff and as-of date. A historical or future-dated record cannot be staged, and a newly uploaded old payment is never accepted as new.
- Distinct authenticated-adapter roles `INTAKE`, `REVIEWER`, and `CANDIDATE_ENGINE`. These are Python **trust interfaces only**, not proof of a Firebase session; an actual server identity adapter must mint `Principal` after verifying claims.
- Durable, SQLite WAL-backed **candidate records** with UTR and invoice unique indexes, duplicate-source holds, dual-review, controlled candidate reservations, restart durability and SQLite `BEGIN IMMEDIATE` capacity checks under concurrent workers.
- Exact paise arithmetic via Python `Decimal`. No float money, no automatic alias resolution, no auto matching by amount, no approved rule substitution.
- Reserved amounts are **not** paid invoices, settlement status `OK`, a bank posting, or a reduction of the real invoice ledger. `status()` shows all finance permissions explicitly disabled.

## How to test (fabricated inputs only)

```bash
cd staging/fresh_financial_engine/stage4
PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -v
```

All test identifiers, source references, dates, statements and HMAC signing keys are fabricated. Test fixtures create only temporary SQLite files and destroy them afterward.

## Integrating with the existing AWS application — not enabled

The production upload currently accepts **only three columns**, which cannot by itself establish bank UTR, authentic banking source, date, original Column I lineage or client identity. To connect safely:

1. A *trusted server-side bank-evidence connector* must verify the original payment source and supply authenticated bank dates, UTR, file/row SHA and the exact user-upload row digest. The backend signs the canonical envelope with a secret stored in a managed secret store. **Never expose the key to a browser or accept user-provided `verified=true` as authority.**
2. The authenticated Firebase gateway must mint trusted `Principal` objects from verified sessions and roles; dual reviewer must be different from uploader. The current module's Python types alone are not an authentication system.
3. An authoritative invoice gateway must verify actual new-only invoices and original paid-marker S/credit-note holds. Only post-cutoff data should be admitted to the isolated candidate ledger.
4. The **full canonical v2.51 allocation engine** must independently establish allowable TDS/GST/period/SOL exceptions, one-to-one matching and waterfall-last, with signed rule evidence before a candidate is reserved. Here `reserve_candidate` checks only provenance, dates, equality, balance conservation and dual review; it **does not certify the financial matching decision**. Until integrated, reservation is REVIEW-ONLY.
5. Repair and independently test the quarantined v2.18 Excel writer. Preserve original `PAYMNENT` A:L and `Invoice Details.` A:AH, source formulas, duplicate source headers, and `PAYMNENT` model M:W / Invoice model AI:AM; output one workbook only. Never import the known QA-failed writer unchanged.
6. Choose a production-grade database under isolated credentials, encrypted storage, privileged backups and audit retention after an independent architecture/security review. SQLite here is a **development reference** demonstrating durability and concurrency, not a production-ledger approval. No migrations to existing finance tables.
7. Run one consolidated independently reviewed source -> exact matching -> writer -> idempotent ledger -> authorization -> rollback test, then obtain **separate owner approval for financial posting**. Never activate `/api/payment-reconciliation/apply` from a CI pass alone.

**No AWS Stage 4 image deployed.** The confirmed Stage 3 localhost synthetic container stays unchanged at `127.0.0.1:18087` with Apply 403. No historical financial data accessed during this build.