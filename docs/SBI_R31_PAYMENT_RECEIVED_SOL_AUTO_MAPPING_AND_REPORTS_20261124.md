# R31 — Payment Received source database, automatic SOL branch lookup and SOL-wise report

**Owner feature request, 24 November 2026.**
Scope: improve the existing **Database Update → Payment Reconciliation → Upload New Payment Evidence** and **Reports**. This is a protected source-ledger/report integration, **not** a claim that all Master v2.51/Matrix v2.39 matching methods are operational in AWS.

## Approved upload format unchanged

| Excel column | EXACT approved header | Type |
|---|---|---|
| A | `Description` | Bank narration, original string |
| B | `SOL ID` | TEXT; preserve leading zeros (e.g. `001505`) |
| C | `Credit Amount` | INR positive decimal; 2 places |

The current private authenticated payment-evidence upload endpoint handles `.xlsx`, max 8 MiB, and retains its exact immutable receipt and SHA. Original `PAYMNENT!A:L` and `Invoice Details.!S` are not edited. Existing invoice upload is not silently changed.

## New database behavior

**On new successful payment uploads**, all original source rows are appended inside the SAME receipt database transaction to `payment_received_evidence_v1` in the existing private `/var/lib/sbi-payment-evidence-staging/receipts.sqlite3` database. The original file also remains intact. Each record contains owner UID, receipt ID, source SHA, Excel row, narration, original text SOL, normalized SOL, branch from approved private master when unique, decimal credit, per-row reasons and source status.

Possible statuses: `PENDING_RECONCILIATION` (source available for later engine), `HOLD_SOL_MASTER` (unavailable/conflicting/unknown branch), `HOLD_DUPLICATE_CANDIDATE` (possible repeated payment source across receipts, no invented UTR) or `EXCLUDED_INVALID_SOURCE`. An invalid record NEVER blocks the independent valid records from storage. File reupload with identical SHA under the same account returns 409. No actual invoice payment allocation or financial status changes are performed.

The private function `source_payment_rows(conn,owner_uid,eligible_only=True)` is the bounded, owner-scoped read adapter for a future fresh-invoice reconciliation job. It does not automatically trigger the full financial engine: that engine remains disconnected. Future integration must still verify fresh invoice upload, method evidence and no duplicate use before marking any payment matched. Three-column payment input lacks bank posting date/UTR: never invent these facts.

## Official branch name automatic lookup

A private master JSON in `sbi-private-approved-sol-master/v1` schema is loaded with two runtime values:

- `SBI_PAYMENT_SOL_MASTER_FILE`: **absolute in-container private path** to mounted JSON, e.g. `/run/sbi-master/approved-sol.json`
- `SBI_PAYMENT_SOL_MASTER_SHA256`: 64-lowercase-character SHA256 of those exact JSON bytes

No private master is committed to public GitHub. The loader checks file size, path, expected SHA and exact row schemas. Unique approved SOL identity maps automatically; conflicting/unknown/unapproved SOL IDs are held with `SOL_MASTER_MAPPING_PENDING_OR_AMBIGUOUS`. Leading zeros are preserved in the source field and stripped **only for the lookup key**, not rewritten.

To prepare the pinned private JSON from the owner-provided approved SOL Excel workbook **on an authorized private machine**:

```bash
# Never run inside the public source GitHub repository or upload bank data to Actions.
python staging/aws_login_v150/prepare_private_sol_master.py \
  /private/SBI_SOL_Branch_Master_FINAL.xlsx \
  /private/approved-sol.json
sha256sum /private/approved-sol.json
chmod 600 /private/approved-sol.json
```

The generator looks for sheet `Clean Branch Master`, columns `SOL ID` and `Official Branch Name`. It auto-approves unambiguous source master codes and keeps known identity correction codes `3970`, `6884`, `6928`, `99922` under private master review until a uniquely resolved owner-approved source is installed. No separate Finance *certificate* is required to deploy the application; this is ordinary accurate data integrity, not certification.

The existing AWS login/payment image build now copies the R31 modules, but **runtime deployment also requires the administrator to mount the private JSON read-only and set both environment variables**, while keeping the existing private evidence directory mounted. If the master is not configured, receipt rows still persist, but all structurally valid unassigned SOLs are held. If a configured master's hash changes, the upload is rejected atomically; no partial source rows are written.

## New Reports tab

`Payment Received — SOL-wise Reconciliation Tally` includes `SOL ID`, mapped branch, uploaded payment rows, total credit (exact Python Decimal), verified matched, not calculated, excluded invalid records and held-for-review. It also exposes a branch/SOL summary CSV and an individual payment row CSV with source receipt,row,credit,narration,status and remarks.

GET endpoints are authenticated and scoped by the saved Firebase session identity:
- `/api/payment-received/sol-report`
- `/api/payment-received/sol-report.csv`
- `/api/payment-received/payment-details.csv`

The CSV exports guard against Excel formula injection. Previous invoice `OK` classification is **not** considered an independently reconciled payment. Until the financial engine is connected, genuinely verified `matched=0` and new payment rows are `not_calculated` or `excluded`. The report does not label unknown payments as `unmatched`: a payment is only unmatched *after a real calculation*.

## Deployment/next integration

1. **R31 source tests** on synthetic private payment workbooks, unique/conflicting SOLs, real SHA pin, duplicate detection, owner isolation, report totals, CSV escaping, original receipt and no financial writes.
2. Package as an isolated AWS Firebase login/payment container, separate staging SHA and private SOL master mount.
3. Operator-run AWS staging test: authenticated upload, saved rows after restart, SOL summary/read-only report, bad-master SHA rejection and source SHA unchanged.
4. Connect the future fresh invoice uploaded source to the **complete** v2.51/v2.39 calculation runner and v2.18 output writer. Only that verified runner can populate the reserved `payment_reconciliation_verified_v1` table after independent bank-event checks. R31 never does.
5. Production dashboard promotion only after actual AWS staging response and private volume backup. No standalone formal Finance certification required to ship the source-ledger/report software; financial settlement writes remain explicitly separate.

**Source development and GitHub CI alone are not an AWS deployment.** No real bank customer rows or private SOL master payload are checked into GitHub.
