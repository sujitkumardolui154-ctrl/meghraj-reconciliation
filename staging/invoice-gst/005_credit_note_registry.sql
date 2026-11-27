-- 005: CREDIT NOTE REGISTRY (QA ONLY). NO ALTERATION TO ORIGINAL INVOICES.
-- The existing sbi_invoice_gst schema is retained. Do NOT execute against
-- financial production until historical invoices, credits, GST filing and
-- reconciliation data have been independently linked and owner-approved.
CREATE TABLE IF NOT EXISTS sbi_invoice_gst.credit_notes (
    credit_note_no text PRIMARY KEY
        CHECK (credit_note_no ~ '^MXP/[0-9]{4}-[0-9]{4}/[0-9]{1,6}$' AND length(credit_note_no) <= 16),
    credit_note_date date NOT NULL,
    fy text NOT NULL CHECK (fy ~ '^[0-9]{4}-[0-9]{4}$'),
    customer_gstin text NOT NULL,
    customer_class text NOT NULL CHECK (customer_class IN ('SBI_BANK','SBI_FUND')),
    customer_name text NOT NULL,
    state_code text NOT NULL DEFAULT '19' CHECK (state_code='19'),
    sac_code text NOT NULL DEFAULT '996812' CHECK (sac_code='996812'),
    reason text NOT NULL CHECK (length(btrim(reason)) BETWEEN 10 AND 1000),
    taxable numeric(14,2) NOT NULL CHECK (taxable>0),
    cgst numeric(14,2) NOT NULL CHECK (cgst>=0),
    sgst numeric(14,2) NOT NULL CHECK (sgst>=0),
    total numeric(14,2) NOT NULL CHECK (total=taxable+cgst+sgst),
    line_count integer NOT NULL CHECK (line_count BETWEEN 1 AND 1000),
    status text NOT NULL DEFAULT 'FINALIZED' CHECK (status='FINALIZED'),
    source_scope text NOT NULL DEFAULT 'ISOLATED_INVOICE_QA'
        CHECK (source_scope='ISOLATED_INVOICE_QA'),
    created_by_uid text NOT NULL CHECK (length(btrim(created_by_uid))>0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sbi_invoice_gst.credit_note_lines (
    credit_note_no text NOT NULL
        REFERENCES sbi_invoice_gst.credit_notes(credit_note_no),
    line_no integer NOT NULL CHECK (line_no BETWEEN 1 AND 1000),
    invoice_no text NOT NULL REFERENCES sbi_invoice_gst.invoices(invoice_no),
    invoice_date date NOT NULL,
    service_month text NOT NULL,
    branch_key text NOT NULL,
    client_name text NOT NULL,
    sol_id text NOT NULL,
    gstin text NOT NULL,
    sac_code text NOT NULL DEFAULT '996812',
    original_taxable numeric(14,2) NOT NULL CHECK (original_taxable>0),
    credited_taxable numeric(14,2) NOT NULL
        CHECK (credited_taxable>0 AND credited_taxable<=original_taxable),
    invoice_snapshot jsonb NOT NULL,
    PRIMARY KEY (credit_note_no,line_no),
    UNIQUE (credit_note_no,invoice_no)
);
CREATE INDEX IF NOT EXISTS ix_sbi_credit_note_invoice
    ON sbi_invoice_gst.credit_note_lines(invoice_no);
CREATE INDEX IF NOT EXISTS ix_sbi_credit_note_date
    ON sbi_invoice_gst.credit_notes(credit_note_date DESC,credit_note_no);

-- Original financial records AND credit-note evidence are append-only.
DROP TRIGGER IF EXISTS trg_block_credit_note_mutation
  ON sbi_invoice_gst.credit_notes;
CREATE TRIGGER trg_block_credit_note_mutation
BEFORE UPDATE OR DELETE ON sbi_invoice_gst.credit_notes
FOR EACH ROW EXECUTE FUNCTION sbi_invoice_gst.block_invoice_mutation();
DROP TRIGGER IF EXISTS trg_block_credit_note_line_mutation
  ON sbi_invoice_gst.credit_note_lines;
CREATE TRIGGER trg_block_credit_note_line_mutation
BEFORE UPDATE OR DELETE ON sbi_invoice_gst.credit_note_lines
FOR EACH ROW EXECUTE FUNCTION sbi_invoice_gst.block_invoice_mutation();

-- Reporting-only view, no automatic adjustment to invoice/payments/filings.
CREATE OR REPLACE VIEW sbi_invoice_gst.credit_note_invoice_credits AS
SELECT l.invoice_no, sum(l.credited_taxable) AS credited_taxable,
       count(*) AS credit_note_count
FROM sbi_invoice_gst.credit_note_lines l
JOIN sbi_invoice_gst.credit_notes n USING (credit_note_no)
WHERE n.status='FINALIZED'
GROUP BY l.invoice_no;
