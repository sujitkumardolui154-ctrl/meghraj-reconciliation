-- DB-R31.2 QA-only rollback. Refuse destructive rollback if new
-- owner/receipt/status evidence exists. Never run on production.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';
DO $guard$
BEGIN
  IF current_database() <> 'sbi_ft04g_clean_0e858f93' THEN
    RAISE EXCEPTION 'DB_R31_QA_ONLY_WRONG_DATABASE';
  END IF;
  IF EXISTS (SELECT 1 FROM sbi.payment_source_status_v1) THEN
    RAISE EXCEPTION 'DB_R31_ROLLBACK_BLOCKED_STATUS_EVIDENCE_PRESENT';
  END IF;
  IF EXISTS (SELECT 1 FROM sbi.import_batches
    WHERE owner_uid IS NOT NULL OR source_receipt_id IS NOT NULL
       OR source_sheet_name IS NOT NULL OR source_parser_version IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'DB_R31_ROLLBACK_BLOCKED_OWNER_OR_SOURCE_EVIDENCE_PRESENT';
  END IF;
END $guard$;
DROP VIEW IF EXISTS sbi.payment_received_source_v1;
DROP TABLE IF EXISTS sbi.payment_source_status_v1;
DROP INDEX IF EXISTS sbi.ix_sbi_r31_batch_owner_receipt;
ALTER TABLE sbi.import_batches DROP COLUMN IF EXISTS owner_uid;
ALTER TABLE sbi.import_batches DROP COLUMN IF EXISTS source_receipt_id;
ALTER TABLE sbi.import_batches DROP COLUMN IF EXISTS source_sheet_name;
ALTER TABLE sbi.import_batches DROP COLUMN IF EXISTS source_parser_version;
COMMIT;
SELECT 'DB_R31_ISOLATED_SAFE_ROLLBACK=PASS';
