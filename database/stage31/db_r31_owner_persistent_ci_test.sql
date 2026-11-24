-- Synthetic source rows for the disposable DB-R31 persistent schema trial.
-- This is NOT real bank evidence. Should be deleted ONLY in disposable CI.
\set ON_ERROR_STOP on
BEGIN;
DO $gate$
BEGIN
 IF current_database()<>'sbi_ft04g_clean_0e858f93'
    OR current_setting('sbi_r31.disposable_ci',true)
       IS DISTINCT FROM 'verified-disposable-container'
    OR EXISTS (SELECT 1 FROM pg_database WHERE datname='sbi_reconciliation_main')
 THEN RAISE EXCEPTION 'DB_R31_DISPOSABLE_CI_ONLY'; END IF;
END $gate$;

INSERT INTO sbi.import_batches (
  id,source_system,source_kind,original_file_name,source_sha256,
  owner_uid,source_receipt_id,source_sheet_name,source_parser_version
) VALUES
(gen_random_uuid(),'excel','payment','synthetic-owner-a.xlsx',repeat('a',64),
 'R31-ci-owner-a','ci-owner-receipt-a','PAYMENT EVIDENCE','R31-ci'),
(gen_random_uuid(),'excel','payment','synthetic-owner-b.xlsx',repeat('a',64),
 'R31-ci-owner-b','ci-owner-receipt-b','PAYMENT EVIDENCE','R31-ci');

DO $assert$
DECLARE n integer;
DECLARE denied boolean:=false;
BEGIN
 SELECT count(*) INTO n FROM sbi.import_batches
  WHERE source_sha256=repeat('a',64)
    AND owner_uid IN ('R31-ci-owner-a','R31-ci-owner-b');
 IF n<>2 THEN RAISE EXCEPTION 'DB_R31_OWNER_SAME_SHA_COUNT_FAILURE'; END IF;

 BEGIN
  INSERT INTO sbi.import_batches (
    id,source_system,source_kind,original_file_name,source_sha256,
    owner_uid,source_receipt_id,source_sheet_name,source_parser_version
  ) VALUES (
    gen_random_uuid(),'excel','payment','synthetic-duplicate.xlsx',
    repeat('a',64),'R31-ci-owner-a','ci-duplicate',
    'PAYMENT EVIDENCE','R31-ci'
  );
 EXCEPTION WHEN unique_violation THEN denied:=true; END;
 IF NOT denied THEN
    RAISE EXCEPTION 'DB_R31_SAME_OWNER_DUPLICATE_UNEXPECTEDLY_ACCEPTED';
 END IF;

 denied:=false;
 BEGIN
   INSERT INTO sbi.import_batches (
     id,source_system,source_kind,original_file_name,source_sha256
   ) VALUES (
     gen_random_uuid(),'excel','payment','synthetic-unowned.xlsx',repeat('b',64)
   );
 EXCEPTION WHEN check_violation THEN denied:=true; END;
 IF NOT denied THEN
   RAISE EXCEPTION 'DB_R31_UNOWNED_PAYMENT_UNEXPECTEDLY_ACCEPTED';
 END IF;
END $assert$;
COMMIT;
SELECT 'DB_R31_PERSISTENT_SAME_SHA_TWO_OWNER_QA=PASS';
SELECT 'DB_R31_PERSISTENT_DUPLICATE_AND_UNOWNED_DENIAL_QA=PASS';
