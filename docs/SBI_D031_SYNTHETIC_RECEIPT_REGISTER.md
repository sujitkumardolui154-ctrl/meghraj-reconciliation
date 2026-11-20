# D-031 — Synthetic Mock Receipt Registry and Server-Policy Boundary
Date: 2026-11-21 | SBI Reconciliation Workspace | Workstream D

## Current deployment and authorization (unchanged)
The running AWS application `sbi-source-reports-v1-stage` at source revision `ce3100b176151b6d5446a88be3241971b5ef51f7` already includes the Payment Evidence Upload UI/backend and read-only readiness endpoint. Actual `Apply Reconciliation to Financial Database` stays disabled. Caddy, login, source reports and private staging volumes are not touched by D-031. User forbids reading, scanning, importing, recalculating, replaying or modifying historical financial records, payments, invoices, GST, credit notes or allocation tables.

## D-031 additions (pure mock engineering only)
`staging/aws_login_v150/d031_synthetic_receipt_register.py`:
- Reuses D-030's *pure* synthetic 3-column `Description | SOL ID | Credit Amount` plus a separately fabricated date, UTR and claimed original Credit-I sidecar. **No change to the actual Excel headers and no real file parser.**
- A `MockServerPolicy` captured at test-runtime initialization controls a **fabricated activation date** and submission date. The pretend uploader cannot override this cutoff through row or sidecar arguments.
- `MockPrincipal` allows reserved `SYNTH-USER-*` identifiers and distinct simulated `SYNTHETIC_EVIDENCE_UPLOADER` / `SYNTHETIC_EVIDENCE_REVIEWER` roles. This is **not real Firebase authentication**, and arbitrary test code can create these mock identities. No real customer identity is accepted.
- `SyntheticOnlyReceiptRegister` is a single-process, ephemeral SQLite `:memory:` index. It can never open an on-disk path, live financial database, bank source file or API. Every accepted fake batch is inserted as only an SHA256 digest, fake receipt ID, role identifier and status. SHA256 here is a content checksum, NOT a bank signature.
- A transaction ensures each fabricated UTR reference hash can only be registered once. Replaying the same fake batch is idempotent. A different fake batch with the same mock UTR is held with no partial inserts; failed row checks atomically hold the batch. No real UTR uniqueness claim.
- Independent mock reviewer can advance a fake receipt from `SYNTHETIC_PENDING_REVIEW` to `SYNTHETIC_REVIEWED_NO_ALLOCATION`, never to real allocation, approved financial reconciliation, payment posting or production unlock.
- No Flask route, app blueprint, HTML action, deployment script, Caddy modification or persistent receipt store is added. **Existing real upload and finance locks unchanged.**

Tests cover pre-activation date, role/actor denial, upload spoofing, fake UTR duplicates/replays, simultaneous submissions, content tamper, line-level failure, reviewer separation and no post-review financial posting.

## Remaining production prerequisites
This simulation does **not** verify a bank UTR, original PAYMNENT Column I amount, server-controlled real bank-cutover date, real Firebase permissions, durable transactional uniqueness, bank statement attestation, or live invoice/financial ledger. It cannot be connected to the existing upload path without separate design approval and independent security/financial QA. The historical financial database must never be mounted or used for this stage.

Next possible development: D-032 new-only invoice evidence model and approved canonical allocator integration under fully fabricated data; keep allocation *proposals* only and do not wire a financial writer. A real release would require independently authorized new-only data architecture, trusted evidence, tested canonical rules, release sign-off and verified rollback.

**D031_SYNTHETIC_MOCK_ONLY=YES; ORIGINAL_UPLOAD_UI=UNCHANGED; REAL_SESSION_AUTH=NOT_IMPLEMENTED; DURABLE_RECEIPTS=NOT_IMPLEMENTED; LIVE_AWS_DEPLOYMENT=NONE; HISTORICAL_FINANCIAL_RECORDS=NOT_ACCESSED; FINANCIAL_WRITES=NOT_PERFORMED; FINANCIAL_APPLY=LOCKED.**
