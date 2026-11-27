-- 004: APPEND-ONLY INVOICE CANCELLATION / VOID REGISTER (ISOLATED QA ONLY).
-- Do not run on main/prod until cross-ledger controls, GST filing and payment
-- reconciliation validations are integrated and a separate owner release is signed.
-- The existing finalized invoice and annexure evidence is never updated/deleted.
CREATE TABLE IF NOT EXISTS sbi_invoice_gst.invoice_number_cancellations (
    invoice_no text PRIMARY KEY CHECK (invoice_no ~ '^MXP[0-9]{4,10}$'),
    cancellation_kind text NOT NULL CHECK (
        cancellation_kind IN ('VOID_UNUSED','CANCEL_FINALIZED')
    ),
    finalized_invoice_no text REFERENCES sbi_invoice_gst.invoices(invoice_no),
    reason_code text NOT NULL CHECK (
        reason_code IN ('NUMBER_UNUSED','ENTRY_ERROR','CUSTOMER_REQUEST','DUPLICATE_REQUEST','OTHER')
    ),
    reason_text text NOT NULL CHECK (length(btrim(reason_text)) BETWEEN 10 AND 1000),
    review_reference text,
    cancelled_by_uid text NOT NULL CHECK (length(btrim(cancelled_by_uid)) > 0),
    cancelled_at timestamptz NOT NULL DEFAULT now(),
    source_financial_snapshot jsonb,
    CHECK (
        (cancellation_kind='VOID_UNUSED'
          AND finalized_invoice_no IS NULL
          AND source_financial_snapshot IS NULL)
        OR
        (cancellation_kind='CANCEL_FINALIZED'
          AND finalized_invoice_no=invoice_no
          AND review_reference IS NOT NULL AND length(btrim(review_reference)) >= 6
          AND source_financial_snapshot IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_invoice_cancellation_time
    ON sbi_invoice_gst.invoice_number_cancellations (cancelled_at DESC);

-- A cancellation is a permanent audit event. Neither cancellation nor the
-- historical invoice can be silently reactivated, altered, or deleted.
DROP TRIGGER IF EXISTS trg_block_invoice_cancellation_mutation
  ON sbi_invoice_gst.invoice_number_cancellations;
CREATE TRIGGER trg_block_invoice_cancellation_mutation
BEFORE UPDATE OR DELETE ON sbi_invoice_gst.invoice_number_cancellations
FOR EACH ROW EXECUTE FUNCTION sbi_invoice_gst.block_invoice_mutation();

-- The effective status is computed without changing financial invoice rows.
CREATE OR REPLACE VIEW sbi_invoice_gst.invoice_effective_status AS
SELECT i.invoice_no,
       CASE WHEN c.invoice_no IS NOT NULL THEN 'CANCELLED' ELSE i.status END AS effective_status,
       c.cancellation_kind,
       c.cancelled_at,
       c.cancelled_by_uid,
       c.reason_code,
       c.review_reference
FROM sbi_invoice_gst.invoices AS i
LEFT JOIN sbi_invoice_gst.invoice_number_cancellations AS c
  ON c.invoice_no = i.invoice_no;
