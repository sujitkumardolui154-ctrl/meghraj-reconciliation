-- DB-R31.6 PERSISTENT owner-scope schema QA: DISPOSABLE CI POSTGRES ONLY.
-- NEVER target AWS, sbi_reconciliation_main, or a shared FT-04 QA instance.
-- No synthetic source rows are inserted here. Unlike the rollback-only
-- db_r31_owner_scope_qa_tx.sql this file commits QA schema changes.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';

DO $guard$
DECLARE n int;
BEGIN
 IF current_database() <> 'sbi_ft04g_clean_0e858f93'
    OR current_setting('sbi_r31.disposable_ci',true)
       IS DISTINCT FROM 'verified-disposable-container' THEN
   RAISE EXCEPTION 'DB_R31_DISPOSABLE_CI_ONLY';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_database
           WHERE datname='sbi_reconciliation_main') THEN
   RAISE EXCEPTION 'DB_R31_PRODUCTION_DATABASE_PRESENT';
 END IF;
 IF to_regclass('sbi.import_batches') IS NULL
    OR to_regclass('sbi.payment_source_rows') IS NULL
    OR to_regclass('sbi.payments') IS NULL
    OR to_regclass('sbi.payment_source_status_v1') IS NULL
    OR to_regclass('sbi.payment_received_source_v1') IS NULL THEN
   RAISE EXCEPTION 'DB_R31_SOURCE_QA_SCHEMA_REQUIRED';
 END IF;
 SELECT count(*) INTO n FROM information_schema.columns
 WHERE table_schema='sbi' AND table_name='import_batches'
   AND column_name IN ('owner_uid','source_receipt_id',
                       'source_sheet_name','source_parser_version');
 IF n <> 4 THEN RAISE EXCEPTION 'DB_R31_OWNER_RECEIPT_FIELDS_MISSING'; END IF;
 SELECT count(*) INTO n FROM pg_constraint
 WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
   AND pg_get_constraintdef(oid)
       LIKE 'UNIQUE (source_system, source_kind, source_sha256)%';
 IF n <> 1 THEN RAISE EXCEPTION 'DB_R31_EXPECT_ONE_LEGACY_GLOBAL_SHA'; END IF;
 IF to_regclass('sbi.ux_r31_ci_owned_source_sha') IS NOT NULL
    OR to_regclass('sbi.ux_r31_ci_legacy_source_sha') IS NOT NULL THEN
   RAISE EXCEPTION 'DB_R31_OLD_QA_OWNER_INDEX_ALREADY_PRESENT';
 END IF;
END $guard$;

-- This lock is permitted only inside the throwaway CI clone.
LOCK TABLE sbi.import_batches IN ACCESS EXCLUSIVE MODE NOWAIT;

CREATE UNIQUE INDEX ux_r31_ci_owned_source_sha ON
  sbi.import_batches(owner_uid,source_system,source_kind,source_sha256)
  WHERE owner_uid IS NOT NULL;

CREATE UNIQUE INDEX ux_r31_ci_legacy_source_sha ON
  sbi.import_batches(source_system,source_kind,source_sha256)
  WHERE owner_uid IS NULL;

DO $drop_original$
DECLARE original text;
BEGIN
 SELECT conname INTO original FROM pg_constraint
 WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
   AND pg_get_constraintdef(oid)
       LIKE 'UNIQUE (source_system, source_kind, source_sha256)%';
 IF original IS NULL THEN
   RAISE EXCEPTION 'DB_R31_OLD_GLOBAL_SHA_NOT_FOUND';
 END IF;
 EXECUTE format('ALTER TABLE sbi.import_batches DROP CONSTRAINT %I',original);
END $drop_original$;

ALTER TABLE sbi.import_batches
  ADD CONSTRAINT ck_r31_ci_new_payment_owner_evidence
  CHECK (
    source_kind <> 'payment'
    OR (
      owner_uid IS NOT NULL
      AND length(trim(owner_uid)) BETWEEN 1 AND 200
      AND source_receipt_id IS NOT NULL
      AND length(trim(source_receipt_id)) > 0
      AND source_sheet_name IS NOT NULL
      AND length(trim(source_sheet_name)) > 0
      AND source_parser_version IS NOT NULL
      AND length(trim(source_parser_version)) > 0
    )
  ) NOT VALID;

COMMIT;
SELECT 'DB_R31_OWNER_PERSISTENT_SCHEMA_QA=PASS';
