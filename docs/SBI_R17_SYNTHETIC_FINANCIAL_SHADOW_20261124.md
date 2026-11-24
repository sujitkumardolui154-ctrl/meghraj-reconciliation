# R17 — Independent synthetic financial matching & global conservation QA (2026-11-24)

## Verified current state
- R15 original financial-source preflight merged into development.
- R16 branch/SOL and duplicate-invoice identity shadow merged into development.
- R14 live Firebase-signed token to SBI Flask application session still **NOT TESTED**; separate PR #154 remains gated.
- Recovered archive source was reviewed locally from the connected private Google Drive recovery folder. The historical review-only `reconciliation_engine.py` is labelled **Master v2.22 / Matrix v2.10** (SHA256 `72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf`), and `conservative_engine.py` is a partial earlier working candidate (SHA256 `6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3`). **Neither is a signed Master v2.51 / Matrix v2.39 implementation**.
- 30/30 existing archived review-only unit tests executed locally and passed against historical code. This is independent of the new R17 test suite; no actual bank source or production service was accessed.
- Archived-source synthetic gap probes demonstrated: older conservative engine can carry forward existing `OK` source status on a **negative** bank credit (without new allocation); it treats numeric-zero invoice S marker as receipt-eligible; the v2.22 review scorer normalizes leading zeros from SOLs for comparison. All three conflicts remain relevant production-blocking review cases. Do not import this recovered source as the approved v2.51 settlement engine.

## R17 scoped implementation

`scripts/ci/sbi_r17_synthetic_financial_shadow.py`: a standalone standard-library-only **review hypothesis** and **global capacity diagnostic** with deliberately synthetic identifiers and clients. No Firebase, cloud, AWS, PostgreSQL, financial database, workbook writer, original bank data or real master in CI.

Contracts independently tested by `tests/test_sbi_r17_synthetic_financial_shadow.py`:
- Decimal HALF_UP gross less 0/1/2/3% of taxable; zero-taxable multiple-rate conflict and no arbitrary near-amount OK
- Exact textual SOL and client guard (leading zeros not normalized), protected nonblank Invoice Details. S including numerical zero, negative/zero credit and prior bank statuses remain blocked
- Explicit synthetic MXP reference contradictions, bank/invoice date chronology, service-month and multi-month conflicts, GST-only requiring verified component ledger
- SBISA collection SOL 1 or missing invoice SOL always documentary review (no unauthorized cross-SOL)
- DNM-01 isolated amount/runner-up/180-day review thresholds, no claims of full DNM settlement evidence
- Global synthetic payment-row/invoice-ID uniqueness, proposed-edge uniqueness, per-payment credit ceilings and per-invoice outstanding ceilings; no debit/credit post, no invoice `OK` or `Duplicate Payment` status ever written
- Privacy: return only reason codes, review outcomes and aggregate counts, never real values or identifiers

All hypothetical reservation edges are **intentionally not matched, executed or persisted**. Even a numerically valid capacity check is not proof of approved matching, previous payment protection, SBISA exception, partial-waterfall correctness or an authoritative ledger.

## Release gate and next work
1. Pin and independently verify complete **Master v2.51 / Matrix v2.39** candidate source hash and approved branch master, not the historical v2.22 recovered scorer.
2. Obtain fresh verified `PAYMNENT` and `Invoice Details.` source snapshots privately with original A:L and A:AH unchanged; not by reusing old v2.18 output or 3-column evidence.
3. Run actual certified engine methods, SBISA, DNM, multi-month, GST-later, same-SOL waterfall-last, duplicate and global ledger cases against a separately approved private holdout oracle. Any method gap is a BLOCKER, not a silent fallback.
4. Verify v2.18 writer and financial DB read-only connection/transaction rollback and true report parity in isolated staging.
5. Complete R14 real Firebase application-session proof, human financial/security signoff, and explicit production cutover decision before financial writes. Current **Financial Apply LOCKED**.

## Safety and authority
The new code is a **synthetic-only test oracle**, not a production engine, backend API, payment status generator or final v2.51 integration. Never label a synthetic pass as complete financial reconciliation. No historical financial records, private master rows, test credentials or passwords enter GitHub CI.
