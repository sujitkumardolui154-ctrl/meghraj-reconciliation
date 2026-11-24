-- DB-R31 owner-scoped import uniqueness: isolated QA TRANSACTION ONLY.
-- The transaction always rolls back, including synthetic source rows and DDL.
-- Never execute against sbi_reconciliation_main or production sockets.
\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned
\pset pager off

BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='2s';

DO $guard$
DECLARE
 old_count int;
 c_name text;
BEGIN
 IF current_database() <> 'sbi_ft04g_clean_0e858f93' THEN
   RAISE EXCEPTION 'DB_R31_QA_ONLY_WRONG_DATABASE';
 END IF;
 IF to_regclass('sbi.import_batches') IS NULL
    OR to_regclass('sbi.payment_source_rows') IS NULL
    OR to_regclass('sbi.payments') IS NULL
    OR to_regclass('sbi.payment_source_status_v1') IS NULL
    OR to_regclass('sbi.payment_received_source_v1') IS NULL THEN
   RAISE EXCEPTION 'DB_R31_R312_SCHEMA_NOT_APPLIED';
 END IF;
 IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='sbi' AND table_name='import_batches'
      AND column_name='owner_uid'
 ) THEN
   RAISE EXCEPTION 'DB_R31_OWNER_FIELD_MISSING';
 END IF;
 SELECT count(*), min(conname::text) INTO old_count,c_name
 FROM pg_constraint
 WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
   AND pg_get_constraintdef(oid) LIKE
       'UNIQUE (source_system, source_kind, source_sha256)%';
 IF old_count <> 1 THEN
   RAISE EXCEPTION 'DB_R31_LEGACY_GLOBAL_SHA_CONSTRAINT_NOT_EXACTLY_ONE';
 END IF;
 IF to_regclass('sbi.ux_r31_qa_owned_source_sha') IS NOT NULL
    OR to_regclass('sbi.ux_r31_qa_legacy_source_sha') IS NOT NULL THEN
   RAISE EXCEPTION 'DB_R31_OWNED_INDEX_ALREADY_PRESENT';
 END IF;
 IF EXISTS (
    SELECT 1 FROM sbi.import_batches
    WHERE owner_uid IN ('qa-r31-scope-a','qa-r31-scope-b')
       OR source_sha256=repeat('a',64)
 ) THEN
   RAISE EXCEPTION 'DB_R31_SYNTHETIC_TEST_IDENTITY_CONFLICT';
 END IF;
END $guard$;

LOCK TABLE sbi.import_batches IN ACCESS EXCLUSIVE MODE NOWAIT;

-- Maintain uniqueness continuously: build both split indexes BEFORE dropping
-- the old global constraint, all within this single transaction.
CREATE UNIQUE INDEX ux_r31_qa_owned_source_sha ON
  sbi.import_batches(owner_uid,source_system,source_kind,source_sha256)
  WHERE owner_uid IS NOT NULL;
CREATE UNIQUE INDEX ux_r31_qa_legacy_source_sha ON
  sbi.import_batches(source_system,source_kind,source_sha256)
  WHERE owner_uid IS NULL;

DO $constraint$
DECLARE old_name text;
BEGIN
 SELECT conname::text INTO old_name
 FROM pg_constraint
 WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
   AND pg_get_constraintdef(oid) LIKE
       'UNIQUE (source_system, source_kind, source_sha256)%';
 IF old_name IS NULL THEN
   RAISE EXCEPTION 'DB_R31_GLOBAL_UNIQUE_CONSTRAINT_MISSING';
 END IF;
 EXECUTE format('ALTER TABLE sbi.import_batches DROP CONSTRAINT %I',old_name);
END $constraint$;

-- NOT VALID preserves old unowned QA rows, but new payment uploads MUST have
-- trusted owner, receipt, sheet and parser identity. This does not invent a
-- bank transaction ID, UTR, date, SOL branch or verified allocation.
ALTER TABLE sbi.import_batches
  ADD CONSTRAINT ck_r31_qa_new_payment_owner_evidence
  CHECK (
    source_kind <> 'payment'
    OR (
      owner_uid IS NOT NULL AND length(trim(owner_uid)) BETWEEN 1 AND 200
      AND source_receipt_id IS NOT NULL AND length(trim(source_receipt_id)) > 0
      AND source_sheet_name IS NOT NULL AND length(trim(source_sheet_name)) > 0
      AND source_parser_version IS NOT NULL AND length(trim(source_parser_version)) > 0
    )
  ) NOT VALID;

-- Two distinct owner-scoped batches intentionally have the SAME source SHA.
-- Two owner-filtered payment records may share narration/SOL/credit as genuine
-- distinct events. Invalid row evidence is retained without sbi.payments row.
DO $test$
DECLARE
 a uuid := gen_random_uuid();
 b uuid := gen_random_uuid();
 a_ok uuid := gen_random_uuid();
 a_bad uuid := gen_random_uuid();
 b_ok uuid := gen_random_uuid();
 na bigint;
 nb bigint;
 ca bigint;
 cb bigint;
 va bigint;
 vb bigint;
 xa bigint;
 dup_rejected boolean := false;
 unowned_rejected boolean := false;
BEGIN
 INSERT INTO sbi.import_batches
 (id,source_system,source_kind,original_file_name,source_sha256,
  owner_uid,source_receipt_id,source_sheet_name,source_parser_version)
 VALUES
 (a,'excel','payment','synthetic-same.xlsx',repeat('a',64),
  'qa-r31-scope-a','qa-receipt-a','PAYMENT EVIDENCE','QA-R31-v1'),
 (b,'excel','payment','synthetic-same.xlsx',repeat('a',64),
  'qa-r31-scope-b','qa-receipt-b','PAYMENT EVIDENCE','QA-R31-v1');

 BEGIN
  INSERT INTO sbi.import_batches
  (id,source_system,source_kind,original_file_name,source_sha256,
   owner_uid,source_receipt_id,source_sheet_name,source_parser_version)
  VALUES (gen_random_uuid(),'excel','payment','duplicate.xlsx',repeat('a',64),
          'qa-r31-scope-a','qa-receipt-a-duplicate','PAYMENT EVIDENCE','QA-R31-v1');
 EXCEPTION WHEN unique_violation THEN dup_rejected := true;
 END;
 IF NOT dup_rejected THEN
   RAISE EXCEPTION 'DB_R31_SAME_OWNER_DUPLICATE_NOT_REJECTED';
 END IF;

 BEGIN
  INSERT INTO sbi.import_batches
  (id,source_system,source_kind,original_file_name,source_sha256)
  VALUES (gen_random_uuid(),'excel','payment','unowned.xlsx',repeat('e',64));
 EXCEPTION WHEN check_violation THEN unowned_rejected := true;
 END;
 IF NOT unowned_rejected THEN
   RAISE EXCEPTION 'DB_R31_UNOWNED_NEW_PAYMENT_NOT_REJECTED';
 END IF;

 INSERT INTO sbi.payment_source_rows
  (id,batch_id,source_row_number,original_values,row_sha256)
 VALUES
 (a_ok,a,2,'{"Description":"QA CREDIT","SOL ID":"001505","Credit Amount":"118.00"}'::jsonb,repeat('b',64)),
 (a_bad,a,3,'{"Description":"QA INVALID","SOL ID":"001505","Credit Amount":"0"}'::jsonb,repeat('c',64)),
 (b_ok,b,2,'{"Description":"QA CREDIT","SOL ID":"001505","Credit Amount":"118.00"}'::jsonb,repeat('d',64));

 INSERT INTO sbi.payments (id,source_row_id,description,sol_id,credit_paise)
 VALUES
 (gen_random_uuid(),a_ok,'QA CREDIT','001505',11800),
 (gen_random_uuid(),b_ok,'QA CREDIT','001505',11800);

 INSERT INTO sbi.payment_source_status_v1
  (source_row_id,source_status,reason_codes,parser_version,canonical_sol)
 VALUES
 (a_ok,'HOLD_SOL_MASTER','["QA_MASTER_NOT_VERIFIED"]'::jsonb,'QA-R31-v1','1505'),
 (a_bad,'EXCLUDED_INVALID_SOURCE','["CREDIT_MUST_BE_POSITIVE"]'::jsonb,'QA-R31-v1','1505'),
 (b_ok,'HOLD_SOL_MASTER','["QA_MASTER_NOT_VERIFIED"]'::jsonb,'QA-R31-v1','1505');

 SELECT count(*), count(payment_id), COALESCE(sum(credit_paise),0),
        count(*) FILTER (WHERE source_status='EXCLUDED_INVALID_SOURCE')
 INTO na,va,ca,xa
 FROM sbi.payment_received_source_v1 WHERE owner_uid='qa-r31-scope-a';
 SELECT count(*), count(payment_id), COALESCE(sum(credit_paise),0)
 INTO nb,vb,cb
 FROM sbi.payment_received_source_v1 WHERE owner_uid='qa-r31-scope-b';
 IF (na,va,ca,xa) <> (2,1,11800,1) OR (nb,vb,cb) <> (1,1,11800) THEN
   RAISE EXCEPTION 'DB_R31_OWNER_FILTER_OR_AMOUNT_PARITY_FAILURE: %,%,%,%; %,%,%',
     na,va,ca,xa,nb,vb,cb;
 END IF;
 IF EXISTS (
   SELECT 1 FROM sbi.payment_received_source_v1
   WHERE owner_uid IN ('qa-r31-scope-a','qa-r31-scope-b')
     AND (raw_sol <> '001505' OR reconciliation_status <> 'NOT_CALCULATED'
          OR official_branch_name IS NOT NULL)
 ) THEN
   RAISE EXCEPTION 'DB_R31_RAW_SOL_OR_MATCH_STATUS_CHANGED';
 END IF;
 IF EXISTS (
   SELECT 1 FROM sbi.payment_received_source_v1
   WHERE source_row_id=a_bad AND payment_id IS NOT NULL
 ) THEN
   RAISE EXCEPTION 'DB_R31_INVALID_SOURCE_CREATED_FINANCIAL_PAYMENT';
 END IF;
 RAISE NOTICE 'DB_R31_OWNER_SCOPED_DUPLICATE_QA=PASS';
 RAISE NOTICE 'DB_R31_UNOWNED_NEW_PAYMENT_BLOCK_QA=PASS';
 RAISE NOTICE 'DB_R31_TWO_OWNER_SOURCE_SUMMARY_QA=PASS';
 RAISE NOTICE 'DB_R31_INVALID_SOURCE_EVIDENCE_QA=PASS';
 RAISE NOTICE 'DB_R31_RAW_SOL_AND_NOT_CALCULATED_QA=PASS';
END $test$;

-- SQL/schema and synthetic financial changes MUST NOT persist in this stage.
ROLLBACK;
SELECT 'DB_R31_OWNER_SCOPE_QA_TRANSACTION=ROLLED_BACK';
