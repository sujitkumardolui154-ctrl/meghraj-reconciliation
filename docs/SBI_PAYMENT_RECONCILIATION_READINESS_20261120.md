# SBI Payment Reconciliation Receipt-to-Engine Preflight — 2026-11-20

## User intent
On new payment upload, update invoice/payment database according to approved matching and allocation rules.

## Verified blockers
The AWS Login/Payment Evidence app has only an immutable three-column staging receipt
(Description, SOL ID, Credit Amount). No verified approved financial allocation engine,
authentic full original PAYMNENT A:L and Invoice Details. source snapshots, global allocation
ledger, correct outstanding balances, v2.18 writer, financial database migration or release
authorization is present. See the historical private 2026-10-29 recovery audit:
- Only a PARTIAL recovered engine candidate, NOT financial production
- Q218-D01 strict writer proof missing
- SBISA collecting SOL 1 with negative-credit cases missing
- No globally unique, release-approved integrated allocation/waterfall engine.

The three-column convenience template is not an authoritative payment transaction record.
Do not infer bank dates, row identities, original Column I credits or invoice prior payment
statuses solely from these rows. Never modify existing PAYMNENT A:L or invoice source data.

## Implemented
- Authenticated GET /api/payment-reconciliation/status returns immutable release blockers.
- Authenticated same-origin CSRF POST /api/payment-reconciliation/preflight rechecks the
  owner-only immutable receipt, source SHA256 and valid/review counts.
- A flagged row causes 409 REVIEW_REQUIRED; even fully valid evidence causes 503
  APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED. No financial database connection or writes.
- The UI offers an explicit receipt-scoped 'Check Reconciliation Readiness' button.
  The actual 'Apply Reconciliation to Financial Database' button remains locked.
- All finance /api/* routes remain 403 by default; no financial write is added.
- No AWS deployment in this branch without QA and separate release review.

## Remaining work to make real reconciliation possible
1. Recover and independently verify full approved engine source and cumulative rulebook.
2. Read verified, current-run original 'PAYMNENT' and 'Invoice Details.' and approved ledger.
   Credit amounts must come from PAYMNENT!I. Exclude invoices with nonblank S and
   preserve all A:L bank source cells. Catch duplicates, partial allocations and SBISA.
3. Integrate exact-reference, service period, GST/TDS, same-SOL, narration eligibility,
   global unique allocation and waterfall-last matching with Decimal HALF_UP.
4. Perform isolated synthetic and independent reconciliation QA + lineage/parity tests;
   no finance backfills/replays. Explicit Finance authorization and audited atomic
   transactional writer needed BEFORE any database updates.
5. Activate only after specific production cutover approval, which is currently blocked.
