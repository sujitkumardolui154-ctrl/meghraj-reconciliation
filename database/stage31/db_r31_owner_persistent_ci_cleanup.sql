-- Cleanup solely of synthetic rows in a disposable, isolated CI database.
-- Never run against any AWS or shared QA server. No real source rows here.
\set ON_ERROR_STOP on
BEGIN;
DO $guard$
DECLARE n integer;
BEGIN
 IF current_database()<>'sbi_ft04g_clean_0e858f93'
    OR current_setting('sbi_r31.disposable_ci',true)
       IS DISTINCT FROM 'verified-disposable-container'
    OR EXISTS (SELECT 1 FROM pg_database WHERE datname='sbi_reconciliation_main')
 THEN RAISE EXCEPTION 'DB_R31_DISPOSABLE_CI_ONLY'; END IF;
 SELECT count(*) INTO n FROM sbi.import_batches;
 IF n<>2 THEN RAISE EXCEPTION 'DB_R31_CI_SOURCE_ROWS_NOT_EXACTLY_TWO'; END IF;
 IF EXISTS (
     SELECT 1 FROM sbi.import_batches
     WHERE owner_uid NOT IN ('R31-ci-owner-a','R31-ci-owner-b')
        OR source_sha256<>repeat('a',64)
 ) THEN RAISE EXCEPTION 'DB_R31_NON_SYNTHETIC_RECORD_PRESENCE'; END IF;
 IF (SELECT count(*) FROM sbi.payment_source_rows)<>0
    OR (SELECT count(*) FROM sbi.payments)<>0
    OR (SELECT count(*) FROM sbi.invoices)<>0
 THEN RAISE EXCEPTION 'DB_R31_NONEMPTY_RELATED_SOURCE_TABLES'; END IF;
END $guard$;
DELETE FROM sbi.import_batches WHERE source_sha256=repeat('a',64)
  AND owner_uid IN ('R31-ci-owner-a','R31-ci-owner-b');
COMMIT;
SELECT 'DB_R31_DISPOSABLE_CI_SYNTHETIC_CLEANUP=PASS';
