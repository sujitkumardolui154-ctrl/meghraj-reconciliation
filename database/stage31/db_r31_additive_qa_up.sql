-- DB-R31.2 CANDIDATE. QA ONLY. Source evidence fields, not settlement.
-- Requires physically isolated PostgreSQL DB; never run on central main.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
DO $guard$
BEGIN
 IF current_database() <> 'sbi_ft04g_clean_0e858f93' THEN
   RAISE EXCEPTION 'DB_R31_QA_ONLY_WRONG_DATABASE';
 END IF;
 IF to_regclass('sbi.import_batches') IS NULL
    OR to_regclass('sbi.payment_source_rows') IS NULL
    OR to_regclass('sbi.payments') IS NULL THEN
   RAISE EXCEPTION 'DB_R31_REQUIRED_SOURCE_TABLES_MISSING';
 END IF;
 -- The guarded down migration must never drop a pre-existing column/table.
 IF EXISTS (
   SELECT 1 FROM information_schema.columns
   WHERE table_schema='sbi' AND table_name='import_batches'
     AND column_name IN ('owner_uid','source_receipt_id',
                         'source_sheet_name','source_parser_version')
 ) OR to_regclass('sbi.payment_source_status_v1') IS NOT NULL
   OR to_regclass('sbi.payment_received_source_v1') IS NOT NULL
   OR to_regclass('sbi.ix_sbi_r31_batch_owner_receipt') IS NOT NULL THEN
   RAISE EXCEPTION 'DB_R31_QA_CANDIDATE_OBJECT_ALREADY_PRESENT_REVIEW';
 END IF;
 IF NOT EXISTS (
   SELECT 1 FROM pg_attribute
   WHERE attrelid='sbi.payment_source_rows'::regclass
     AND attname='original_values' AND atttypid='jsonb'::regtype
     AND NOT attisdropped
 ) THEN RAISE EXCEPTION 'DB_R31_SOURCE_VALUES_JSONB_REQUIRED'; END IF;
END $guard$;

-- Old records retain NULL owner and are NOT implicitly reclassified.
-- Legacy global source SHA uniqueness is deliberately retained in this QA
-- candidate; multi-owner identical-source support remains BLOCKED.
ALTER TABLE sbi.import_batches
  ADD COLUMN IF NOT EXISTS owner_uid text;
ALTER TABLE sbi.import_batches
  ADD COLUMN IF NOT EXISTS source_receipt_id text;
ALTER TABLE sbi.import_batches
  ADD COLUMN IF NOT EXISTS source_sheet_name text;
ALTER TABLE sbi.import_batches
  ADD COLUMN IF NOT EXISTS source_parser_version text;

-- Supplemental, versioned SOURCE review only. Financial payments remain
-- exclusively in sbi.payments; rejected source rows live in the existing
-- sbi.payment_source_rows with no corresponding payments row.
CREATE TABLE IF NOT EXISTS sbi.payment_source_status_v1 (
  source_row_id uuid PRIMARY KEY
    REFERENCES sbi.payment_source_rows(id) ON DELETE RESTRICT,
  -- Owner is derived solely from the linked import batch, never copied into
  -- a second mutable column that might disagree with the source owner.
  source_status text NOT NULL CHECK (
    source_status IN (
      'PENDING_RECONCILIATION',
      'HOLD_SOL_MASTER',
      'HOLD_DUPLICATE_CANDIDATE',
      'EXCLUDED_INVALID_SOURCE',
      'REVIEW_REQUIRED'
    )
  ),
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(reason_codes)='array'),
  parser_version text NOT NULL,
  canonical_sol text,
  official_branch_name text,
  sol_master_sha256 text
    CHECK (sol_master_sha256 IS NULL OR
           sol_master_sha256 ~ '^[0-9a-f]{64}$'),
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (official_branch_name IS NULL OR sol_master_sha256 IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_sbi_r31_source_status_owner
  ON sbi.payment_source_status_v1(source_status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sbi_r31_batch_owner_receipt
  ON sbi.import_batches(owner_uid,source_receipt_id)
  WHERE owner_uid IS NOT NULL AND source_receipt_id IS NOT NULL;

-- No allocation join: each physical source row is represented once.
-- View has NO public or web-user grants; authenticated application must
-- filter owner_uid with a server-derived parameter before exposure.
CREATE OR REPLACE VIEW sbi.payment_received_source_v1 AS
SELECT
  b.owner_uid,
  b.id AS batch_id,
  b.source_receipt_id,
  b.source_sha256,
  b.source_sheet_name,
  r.id AS source_row_id,
  r.source_row_number,
  r.row_sha256,
  r.original_values,
  r.original_values->>'Description' AS description,
  r.original_values->>'SOL ID' AS raw_sol,
  r.original_values->>'Credit Amount' AS raw_credit_amount,
  p.id AS payment_id,
  p.credit_paise,
  COALESCE(st.source_status,'UNCLASSIFIED_LEGACY') AS source_status,
  COALESCE(st.reason_codes,'[]'::jsonb) AS reason_codes,
  st.canonical_sol,
  st.official_branch_name,
  st.sol_master_sha256,
  st.parser_version,
  'NOT_CALCULATED'::text AS reconciliation_status
FROM sbi.import_batches b
JOIN sbi.payment_source_rows r ON r.batch_id=b.id
LEFT JOIN sbi.payments p ON p.source_row_id=r.id
LEFT JOIN sbi.payment_source_status_v1 st ON st.source_row_id=r.id
WHERE b.source_kind='payment';

REVOKE ALL ON sbi.payment_source_status_v1 FROM PUBLIC;
REVOKE ALL ON sbi.payment_received_source_v1 FROM PUBLIC;
-- No new financial table grants or production roles in this migration.
COMMIT;
SELECT 'DB_R31_ISOLATED_ADDITIVE_MIGRATION=PASS';
