# Invoice Number Cancellation / Void Register — QA implementation

**Owner request:** If any manually entered Meghraj Express MXP invoice number is cancelled, preserve the number and record a permanent, auditable PostgreSQL cancellation log.

**Scope:** SBI Workspace > Reports > Invoice Cancellation / Number Void Register.
**Release status:** Isolated QA only; draft PR #182. Live financial writes and cancellation are NOT enabled.

## Cancellation cases

| Scenario | Register kind | Original invoice row | Invoice number reuse |
|---|---|---|---|
| Assigned MXP number not yet finalized | `VOID_UNUSED` | No invoice row exists; append cancellation record | Blocked |
| Already finalized/issued MXP invoice | `CANCEL_FINALIZED` | Original immutable invoice and shipment evidence preserved | Blocked |
| Already voided/cancelled number | Existing record, HTTP 409 | Preserved | Blocked |
| Historic bank/payment/GST/filed invoice | NOT independently verified | Not automatically reversed | Production blocked |

For finalized invoices, the UI requires a documented reason, an accounting
review reference and a positive accounting confirmation. These are *not*
substitutes for an independent payment, credit note or GSTR filing check.
Until that external ledger validation exists, the API **refuses all live
cancellation requests**, regardless of owner input or environment flag.

## PostgreSQL contract

- In the **existing** `sbi_invoice_gst` schema, migration
  `004_invoice_cancellation_ledger.sql` creates
  `invoice_number_cancellations` and read-only
  `invoice_effective_status` view.
- `invoice_no` is the primary key; one permanent cancellation event only.
- The record stores `cancellation_kind`, `reason_code`, `reason_text`,
  `review_reference`, authenticated `cancelled_by_uid`, server-side
  `cancelled_at` and a financial snapshot for finalized invoices.
- A trigger blocks UPDATE/DELETE of cancellation records; invoice and shipment
  immutability triggers remain in force.
- This is not a new master database and contains no payment allocation writes.

## API / permissions

- `GET /api/invoice-gst/cancellations?invoice_no=MXP...` — view the audit
  register, exact-number filter optional, max 200 latest.
- `POST /api/invoice-gst/cancellations` — append a QA cancellation record.
  Validates MXP syntax, reason length/code, authenticated Firebase actor,
  CSRF, separate `sbi_invoice_canceller` entitlement, feature flag
  `SBI_INVOICE_GST_CANCELLATION_ENABLED=1`, deployment mode
  `ISOLATED_QA` and exact database name `invoice_qa`.
- `invoice_gst_feature.py` finalization takes the same
  `pg_advisory_xact_lock(hashtext(invoice_no))` as cancellation and refuses
  a cancelled number. This prevents racing a VOID against FINALIZE.
- Invoice lookup shows effective status `CANCELLED` without mutating the
  original record. Normal active PDF download returns 409 for cancelled
  invoices. The GST XLSX query excludes cancellation-ledger entries.
  Cancellation register preserves the audit evidence separately.

## Entry form

1. Manually enter an MXP number; click **Check Invoice / Number Status**.
2. If never finalized, select **Allocated invoice number not used** and
   enter at least 10 characters explaining why it is voided.
3. If finalized, select a reason, enter explanatory text, supply the
   accounting reviewer reference, and confirm external accounting review.
4. Click **Confirm Cancellation & Write Permanent Audit Log**.
5. QA writes exactly one append-only cancellation record and returns
   `CANCELLED`; subsequent creation or cancellation attempts fail.

## Required steps before any live enablement

1. Confirm the authoritative global invoice-number registry (including
   historic invoice files and credit notes), so a number shown unused in the
   isolated registry is truly unused across the complete business.
2. Check the reconciliation/payment ledger for partial/complete settlement,
   bank evidence and TDS dependencies, with owner-scoped permissions.
3. Check whether the invoice entered GST returns or a customer ledger and
   decide whether a credit note / tax adjustment, rather than cancellation,
   is legally/accountingly required.
4. Assign separate `sbi_invoice_canceller` Firebase permissions and a
   reviewed production approval workflow (ideally requester + approver).
5. Verify active invoice, GST report, Dashboard, export and full audit register
   agree on effective statuses; preserve historical filings and snapshots.
6. Perform authenticated isolated QA and backup/restore tests; request
   separate owner production approval. **Do not remove the hard-coded QA-only
   fence without the external checks and documented authorization.**

## Test evidence

Automated isolated PostgreSQL tests cover unused-number void, 409 duplicate,
nonreuse at finalization, issued-invoice cancellation with review reference,
immutable log, immutable shipment evidence, GST export exclusion, active PDF
denial and locked live mode. All tests use synthetic records in `invoice_qa`.
