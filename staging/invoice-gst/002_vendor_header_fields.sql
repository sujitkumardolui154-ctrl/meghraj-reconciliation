-- ADDITIVE QA-ONLY VENDOR HEADER MIGRATION (screenshot correction 2026-11-24).
-- Do not run in financial production. Existing invoice/payment tables untouched.
-- The original Excel contains two header objects: the Meghraj logo LEFT,
-- and the registered office/head office/contact panel RIGHT.
-- Fields are private vendor profile evidence, never hardcoded in public code.
ALTER TABLE sbi_invoice_gst.vendor_profiles
    ADD COLUMN IF NOT EXISTS registered_office text,
    ADD COLUMN IF NOT EXISTS registered_phone text,
    ADD COLUMN IF NOT EXISTS registered_email text,
    ADD COLUMN IF NOT EXISTS head_office text,
    ADD COLUMN IF NOT EXISTS head_phone text,
    ADD COLUMN IF NOT EXISTS website text;
