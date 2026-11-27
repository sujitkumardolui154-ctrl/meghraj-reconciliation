-- Additive, isolated invoice_qa only. NOT for production financial schemas.
-- Prevent concurrent or separately reviewed imports from certifying two
-- different SBI branch identities against the same verified SOL ID.
-- Existing duplicates must be manually reconciled before applying the index.
CREATE UNIQUE INDEX IF NOT EXISTS ux_sbi_invoice_verified_unique_sol
    ON sbi_invoice_gst.verified_branches (sol_id)
    WHERE verified = TRUE;
