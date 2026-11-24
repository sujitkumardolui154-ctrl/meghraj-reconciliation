-- SBI Workspace invoice registry: isolated, private PostgreSQL schema.
-- APPLY ONLY TO A NON-PRODUCTION QA DATABASE until owner release approval.
-- Existing reconciliation and payment tables are not modified.
CREATE SCHEMA IF NOT EXISTS sbi_invoice_gst;

-- Integration intake: populate ONLY from the existing approved, verified SBI
-- branch master through a privately reviewed ETL. No guessed SOL/aliases.
CREATE TABLE IF NOT EXISTS sbi_invoice_gst.verified_branches (
    branch_key text PRIMARY KEY,
    client_name text NOT NULL,
    invoice_branch text NOT NULL,
    invoice_generate_location text NOT NULL,
    original_branch_name text NOT NULL,
    sol_id text NOT NULL CHECK (sol_id ~ '^[0-9]{1,6}$'),
    client_class text NOT NULL CHECK (client_class IN ('SBI_BANK','SBI_FUND')),
    gstin text NOT NULL,
    recipient_title text NOT NULL,
    customer_address text NOT NULL,
    state_code text NOT NULL DEFAULT '19',
    verified boolean NOT NULL DEFAULT false,
    verified_by text,
    verified_at timestamptz,
    CHECK (client_name <> ''),
    CHECK ((verified = false) OR (verified_by IS NOT NULL AND verified_at IS NOT NULL))
);

-- Exact original logo and verbatim source statements belong in a private
-- vendor profile; they MUST NOT be committed into this public repository.
CREATE TABLE IF NOT EXISTS sbi_invoice_gst.vendor_profiles (
    vendor_key text PRIMARY KEY,
    legal_name text NOT NULL,
    logo_image bytea,
    logo_mime text,
    exact_logo_verified boolean NOT NULL DEFAULT false,
    declaration_text text NOT NULL,
    bank_instructions text NOT NULL,
    pan text NOT NULL,
    gstin text NOT NULL,
    vendor_id text NOT NULL,
    service_type text NOT NULL,
    sac_code text NOT NULL,
    footer_text text NOT NULL,
    authorized_signature_label text NOT NULL,
    verified_by text,
    verified_at timestamptz
);

CREATE TABLE IF NOT EXISTS sbi_invoice_gst.invoices (
    invoice_no text PRIMARY KEY CHECK (invoice_no ~ '^MXP[0-9]{4,10}$'),
    branch_key text NOT NULL REFERENCES sbi_invoice_gst.verified_branches(branch_key),
    service_from date NOT NULL,
    service_to date NOT NULL,
    invoice_date date NOT NULL,
    service_month text NOT NULL,
    service_month_key text NOT NULL CHECK (service_month_key ~ '^[0-9]{4}-[0-9]{2}$'),
    fy text NOT NULL,
    invoice_branch text NOT NULL,
    invoice_generate_location text NOT NULL,
    original_branch_name text NOT NULL,
    sol_id text NOT NULL,
    client_name text NOT NULL,
    gstin text NOT NULL,
    master_snapshot jsonb NOT NULL,
    taxable numeric(14,2) NOT NULL,
    cgst numeric(14,2) NOT NULL,
    sgst numeric(14,2) NOT NULL,
    total numeric(14,2) NOT NULL,
    shipment_count integer NOT NULL CHECK (shipment_count BETWEEN 1 AND 5000),
    status text NOT NULL DEFAULT 'FINALIZED' CHECK (status = 'FINALIZED'),
    verification_flags text NOT NULL DEFAULT '',
    created_by_uid text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (service_from <= service_to),
    CHECK (taxable + cgst + sgst = total)
);

CREATE TABLE IF NOT EXISTS sbi_invoice_gst.invoice_lines (
    invoice_no text NOT NULL REFERENCES sbi_invoice_gst.invoices(invoice_no),
    line_no integer NOT NULL CHECK (line_no BETWEEN 1 AND 5000),
    dispatch_date date NOT NULL,
    lr_no text NOT NULL,
    packet_ref_no text NOT NULL DEFAULT '',
    consignee text NOT NULL,
    weight_kg numeric(12,3) NOT NULL CHECK (weight_kg > 0),
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    PRIMARY KEY (invoice_no,line_no),
    UNIQUE (invoice_no,dispatch_date,lr_no)
);

CREATE INDEX IF NOT EXISTS ix_sbi_invoice_gst_month
    ON sbi_invoice_gst.invoices(service_month_key,fy,invoice_no);

-- Final invoices and annexures are immutable. Corrections require a separately
-- reviewed credit-note/revision flow; no silent editing of billed evidence.
CREATE OR REPLACE FUNCTION sbi_invoice_gst.block_invoice_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'FINALIZED_INVOICE_IMMUTABLE';
END;
$$;
DROP TRIGGER IF EXISTS trg_block_invoice_update ON sbi_invoice_gst.invoices;
CREATE TRIGGER trg_block_invoice_update
BEFORE UPDATE OR DELETE ON sbi_invoice_gst.invoices
FOR EACH ROW EXECUTE FUNCTION sbi_invoice_gst.block_invoice_mutation();
DROP TRIGGER IF EXISTS trg_block_invoice_line_update ON sbi_invoice_gst.invoice_lines;
CREATE TRIGGER trg_block_invoice_line_update
BEFORE UPDATE OR DELETE ON sbi_invoice_gst.invoice_lines
FOR EACH ROW EXECUTE FUNCTION sbi_invoice_gst.block_invoice_mutation();
