-- DB-R31.6 PERSISTENT CI rollback, guarded for DISPOSABLE Postgres only.
-- If distinct owner rows still share the same SHA, restoring global SHA
-- uniqueness would be impossible; FAIL CLOSED instead of deleting evidence.
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
 IF to_regclass('sbi.ux_r31_ci_owned_source_sha') IS NULL
    OR to_regclass('sbi.ux_r31_ci_legacy_source_sha') IS NULL THEN
   RAISE EXCEPTION 'DB_R31_CI_OWNER_INDEXES_MISSING';
 END IF;
 SELECT count(*) INTO n FROM pg_constraint
 WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
   AND pg_get_constraintdef(oid)
       LIKE 'UNIQUE (source_system, source_kind, source_sha256)%';
 IF n <> 0 THEN
   RAISE EXCEPTION 'DB_R31_GLOBAL_SHA_ALREADY_PRESENT';
 END IF;
 IF EXISTS (
   SELECT 1 FROM sbi.import_batches
   GROUP BY source_system, source_kind, source_sha256
   HAVING count(*) > 1
 ) THEN
   RAISE EXCEPTION 'DB_R31_OWNER_DUPLICATES_PREVENT_GLOBAL_ROLLBACK';
 END IF;
END $guard$;

LOCK TABLE sbi.import_batches IN ACCESS EXCLUSIVE MODE NOWAIT;

ALTER TABLE sbi.import_batches
  ADD CONSTRAINT uq_r31_ci_restored_global_source_sha
  UNIQUE (source_system,source_kind,source_sha256);

ALTER TABLE sbi.import_batches
  DROP CONSTRAINT ck_r31_ci_new_payment_owner_evidence;

DROP INDEX sbi.ux_r31_ci_owned_source_sha;
DROP INDEX sbi.ux_r31_ci_legacy_source_sha;

COMMIT;
SELECT 'DB_R31_OWNER_PERSISTENT_ROLLBACK_QA=PASS';
