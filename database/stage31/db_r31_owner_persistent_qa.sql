-- DB-R31 isolated owner-scoped PERSISTENT QA migration.
-- THIS IS NOT A PRODUCTION MIGRATION. New disposable QA database ONLY.
-- The original FT-04 QA database and the main ledger are not touched.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='40s';
DO $guard$
DECLARE original_count int;
BEGIN
  IF current_database() <> 'sbi_r31_owner_qa_20261125' THEN
    RAISE EXCEPTION 'DB_R31_PERSISTENT_QA_WRONG_DATABASE';
  END IF;
  IF to_regclass('sbi.import_batches') IS NULL
     OR to_regclass('sbi.payment_source_rows') IS NULL
     OR to_regclass('sbi.payment_source_status_v1') IS NULL
     OR to_regclass('sbi.payment_received_source_v1') IS NULL
     OR to_regclass('sbi.payments') IS NULL THEN
    RAISE EXCEPTION 'DB_R31_CLONED_R312_SCHEMA_MISSING';
  END IF;
  IF EXISTS(SELECT 1 FROM sbi.import_batches)
     OR EXISTS(SELECT 1 FROM sbi.payment_source_rows)
     OR EXISTS(SELECT 1 FROM sbi.payments)
     OR EXISTS(SELECT 1 FROM sbi.payment_source_status_v1) THEN
    RAISE EXCEPTION 'DB_R31_OWNER_MIGRATION_REQUIRES_EMPTY_QA_CLONE';
  END IF;
  IF to_regclass('sbi.ux_r31_qa_owned_source_sha') IS NOT NULL
     OR to_regclass('sbi.ux_r31_qa_legacy_source_sha') IS NOT NULL THEN
    RAISE EXCEPTION 'DB_R31_OWNER_INDEX_ALREADY_PRESENT';
  END IF;
  SELECT count(*) INTO original_count FROM pg_constraint
    WHERE conrelid='sbi.import_batches'::regclass
      AND contype='u'
      AND pg_get_constraintdef(oid) LIKE
        'UNIQUE (source_system, source_kind, source_sha256)%';
  IF original_count <> 1 THEN
    RAISE EXCEPTION 'DB_R31_GLOBAL_SHA_UNIQUE_NOT_EXACTLY_ONE';
  END IF;
END $guard$;

LOCK TABLE sbi.import_batches IN ACCESS EXCLUSIVE MODE NOWAIT;

-- New owner-scoped uploads and old unowned evidence remain separately unique.
CREATE UNIQUE INDEX ux_r31_qa_owned_source_sha ON
  sbi.import_batches(owner_uid,source_system,source_kind,source_sha256)
  WHERE owner_uid IS NOT NULL;

CREATE UNIQUE INDEX ux_r31_qa_legacy_source_sha ON
  sbi.import_batches(source_system,source_kind,source_sha256)
  WHERE owner_uid IS NULL;

DO $drop_old$
DECLARE old_name text;
BEGIN
 SELECT conname::text INTO old_name
 FROM pg_constraint WHERE conrelid='sbi.import_batches'::regclass
 AND contype='u' AND pg_get_constraintdef(oid)
   LIKE 'UNIQUE (source_system, source_kind, source_sha256)%';
 IF old_name IS NULL THEN
   RAISE EXCEPTION 'DB_R31_GLOBAL_SHA_UNIQUE_MISSING';
 END IF;
 EXECUTE format('ALTER TABLE sbi.import_batches DROP CONSTRAINT %I',old_name);
END $drop_old$;

-- Never silently backfill historical unowned records. New payment batches need
-- original receipt, workbook sheet and parser version evidence.
ALTER TABLE sbi.import_batches
 ADD CONSTRAINT ck_r31_qa_new_payment_owner_evidence
 CHECK (
   source_kind <> 'payment'
   OR (
     owner_uid IS NOT NULL
     AND length(btrim(owner_uid)) BETWEEN 1 AND 200
     AND source_receipt_id IS NOT NULL AND length(btrim(source_receipt_id)) > 0
     AND source_sheet_name IS NOT NULL AND length(btrim(source_sheet_name)) > 0
     AND source_parser_version IS NOT NULL AND length(btrim(source_parser_version)) > 0
   )
 ) NOT VALID;

-- No table owner/RLS changes and no public role write grants here. Separate
-- least-privilege QA roles are granted by the isolated-only installer.
COMMIT;
SELECT 'DB_R31_OWNER_QA_SCHEMA_PERSISTED|PASS';
