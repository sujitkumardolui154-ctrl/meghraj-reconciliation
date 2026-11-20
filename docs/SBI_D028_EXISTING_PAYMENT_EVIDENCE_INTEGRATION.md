# D-028 — Reuse existing Payment Reconciliation → Payment Evidence Upload
Date: 2026-11-21 | SBI Reconciliation Workspace

## Owner correction / actual source discovery
**Do NOT create another Payment Evidence tab.** The existing upload interface and backend were implemented earlier in:
- PR #118: Database Update → Payment Reconciliation navigation and disabled reconciliation action
- PR #119: existing three-column fixed XLSX form, template, source validation, receipt history, Firebase session and same-origin CSRF guards.

The canonical existing UI source in the PR #119 branch is `dashboard_source/index.html` with `id="dil-payment-upload-form"`, `id="dil-payment-evidence-file"` and disabled `id="dil-payment-reconcile"`.
The existing backend is `staging/aws_login_v150/payment_evidence_upload.py`, registered from `staging/aws_login_v150/app.py`, with routes:
- `GET /api/payment-evidence/template` — downloadable fixed 3-column workbook
- `POST /api/payment-evidence/upload` — staged .xlsx upload, CSRF, owner-scoped receipt
- `GET /api/payment-evidence/uploads` — owner-scoped receipt history
- `GET /api/payment-evidence/uploads/<receipt_id>` — digest-verified owner receipt preview.

The actual XLSX sheet is `PAYMENT EVIDENCE`. **Exactly three headers:**
`Description | SOL ID | Credit Amount` (columns A/B/C).
This is NOT the legacy full `PAYMNENT` worksheet A–L. The original source `PAYMNENT` Credit is column I, but a user copies each fresh transaction's description, SOL and credit into the 3-column upload template; original source A–L must remain untouched.

## D-028 completed
- Adds a pure source-level `d028_existing_payment_contract.py` and synthetic-only test suite. They check a single existing UI, unchanged upload route names, fixed 3-column header schema, disabled reconciliation action, blueprint registration, session/CSRF source hooks, per-owner receipt scope and separate staging receipt store.
- No extra UI routes, new menu item, financial engine connection, actual bank data or AWS deployment.
- The D-027 pure in-memory synthetic 12-column intake model **must NOT be plugged directly into the 3-column live UI**. Its mock dates/UTR fields and synthetic user roles are not verified real API controls. An explicit, tested versioned adapter would be required if extra fields are approved.
- PR #119 original synthetic/unit CI previously passed. D-028 source-only tests are separate and must pass before review.

## Critical owner policy / release gates
- **Deploy logic and rules only; test exclusively with synthetic fabricated data.** No scan, calculate, recalculate, replay, backfill or modify earlier invoice/payment/Credit Note/GST/allocations.
- The 3-column template **has no payment date or UTR column**. Duplicate checking currently covers repeated source rows and identical uploaded workbook hash per authenticated owner, NOT universal bank UTR deduplication or proof that payment date is after activation. Do not claim stronger evidence uniqueness than this contract provides.
- The upload route stages private nonfinancial files and calculates a preview-only credit total from *explicitly submitted* data; it does not reconcile prior balances. However source-level checks alone cannot enforce that an uploader never submits old payments. Keep actual financial processing disabled until a separately approved trusted new-evidence cutoff and duplicate policy exists.
- The PR #119 deployment script `deploy_payment_evidence_v1.sh` requires an exact previously staged `sbi-database-update-nav-stage` container and baseline Caddy config. **These host prerequisites have NOT been verified**; do not invoke `activate` or force replacement. The source PR's successful CI does NOT mean its image is running on AWS.
- AWS live image/route identity, authenticated browser session, access control, private evidence mount, owner-approved activation and rollback require independent stage QA; no production financial write is authorized.

## Next minimal host verification
Use a single targeted, read-only check for the exact two expected candidate containers and source revision before staging; no raw Caddyfile, secrets, financial data or hosted endpoints. If the baseline is absent, report BLOCKED_HOST_BASELINE and prepare a new isolated stage plan; DO NOT bypass Caddy safety locks.

**D028_EXISTING_UI_CONTRACT=SOURCE_QA; DUPLICATE_UI=PROHIBITED; LIVE_UPLOAD_STATUS=NOT_VERIFIED; HISTORICAL_FINANCIAL_DATA=OUT_OF_SCOPE; PRODUCTION_RECONCILIATION=BLOCKED.**
