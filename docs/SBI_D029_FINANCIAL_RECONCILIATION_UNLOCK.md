# D-029 — Why Financial Reconciliation Is Locked
Date: 2026-11-21 | Existing SBI Reconciliation Workspace (AWS) | SOURCE ONLY

## Verified deployed application
AWS running `sbi-source-reports-v1-stage` OCI SHA `ce3100b176151b6d5446a88be3241971b5ef51f7` contains existing Payment Evidence Upload, its registered Firebase-protected blueprint, 3-column `Description | SOL ID | Credit Amount` XLSX intake, and `reconciliation_readiness.py` with a read-only status/preflight. Active Caddy routes `/api/*` to `sbi-source-reports-v1:8080`. The financial Apply button is deliberately disabled in HTML and the catch-all financial API returns 403. The protected preflight returns 409 if staged receipt rows have flags and 503 when a clean receipt has no approved allocator/writer.

## Owner policy
**Never access, recalculate, replay, import, alter or migrate historical financial records** (bank receipts, invoices, original PAYMNENT, credit notes, GST, allocation balances). No ledger or database connection for testing. All regression tests are fabricated. No source-only synthetic PASS can grant live financial execution.

## D-029 implemented
- The existing, authenticated `GET /api/payment-reconciliation/status` now explains five concrete **future-only** release prerequisites with `status=BLOCKED` and required work. The response categorically marks `unlock_allowed=False`, historical read/write unauthorized, financial write false and real release not certified.
- The current Payment Reconciliation tab gets one **View Locked Requirements** read-only control. It displays authenticated API requirements via `textContent` (no HTML injection), without uploading a payment or accessing any stored receipts, while the existing `Apply Reconciliation to Financial Database — Locked` remains disabled.
- No new Payment Evidence tab, no Caddy route change, no active AWS deployment, no settlement/writer endpoint.

## Missing engineering to make a future-only reconciliation action possible
1. **New-only evidence provenance**: the current three fields include no bank date or UTR. Design an approved, versioned proof/metadata contract bound to bank date, bank unique reference, SOL, original PAYMNENT Credit-I provenance and trusted activation cutoff; refuse anything pre-activation or unidentifiable.
2. **New-only invoices**: isolated, approved records created after activation; no connection to historical invoice/branch/credit-note ledgers. Use approved SOL branch rules only as nonfinancial reference logic.
3. **Canonical allocator**: implement and certify approved same-SOL matching, service period, GST/TDS, partial/full waterfall, SBISA and duplicate/credit-note holds on synthetic fixtures. Existing D-025/D-026 mock logic is not a certified posting engine.
4. **Independent finance store**: new-only, append-only and transactionally idempotent allocations with separate reviewer approval, audit, no prior balance touching and tested rollback. No direct write to older allocation tables.
5. **Independent QA/release**: synthetic-only end-to-end tests with wrong-file, cross-SOL, duplicate, conflicts, repeated receipt, owner role, no history mounted and frozen production-database credentials, signed/pinned staging, rollback rehearsal and explicit separate owner approval.

Do not flip the HTML `disabled` attribute or add a fake successful `/api/payment-reconciliation/run` endpoint. A runtime flag from the browser is not production authorization.

**D029_SOURCE_DIAGNOSTIC=READY_FOR_SYNTHETIC_QA; D029_LIVE_APPLICATION_CHANGE=NONE; REAL_FINANCIAL_RECONCILIATION=LOCKED; HISTORICAL_DATA=UNTOUCHED.**
