\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
-- R31.11.2 existing-clone verification. This file is read-only and idempotent.
-- NEVER load fixtures, create roles, apply migrations, or run against production.
-- Auth roles below are synthetic NOLOGIN identities; this is not real Firebase QA.

BEGIN TRANSACTION READ ONLY;

DO $preflight$
DECLARE
  n integer;
BEGIN
  IF current_database() <> 'sbi_r31_11_tenant_clone_20261125'
     OR session_user <> 'postgres'
     OR current_setting('transaction_read_only') <> 'on' THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_WRONG_DATABASE_OR_NOT_READONLY';
  END IF;
  SELECT count(*) INTO n
    FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'sbi'
     AND c.relname IN ('import_batches','payment_source_rows',
                       'payments','payment_source_status_v1')
     AND c.relkind = 'r' AND c.relrowsecurity AND c.relforcerowsecurity;
  IF n <> 4 THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_FORCE_RLS_MISSING';
  END IF;
  SELECT count(*) INTO n
    FROM pg_roles
   WHERE rolname IN ('r311_qa_tenant_a','r311_qa_tenant_b')
     AND NOT rolcanlogin AND NOT rolbypassrls AND NOT rolsuper;
  IF n <> 2 THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_RESTRICTED_TENANT_ROLES_MISSING';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
     WHERE s.nspname = 'sbi' AND c.relname = 'payment_received_source_v1'
       AND c.relkind = 'v'
       AND 'security_invoker=true' = ANY(c.reloptions)
  ) THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_INVOKER_VIEW_MISSING';
  END IF;
  SELECT count(*) INTO n FROM sbi.import_batches;
  IF n <> 2 OR
     (SELECT count(*) FROM sbi.import_batches
       WHERE (id = '11111111-1111-4111-8111-111111111111'::uuid
              AND owner_uid = 'r311-synthetic-owner-a')
          OR (id = '22222222-2222-4222-8222-222222222222'::uuid
              AND owner_uid = 'r311-synthetic-owner-b')) <> 2
     OR (SELECT count(*) FROM sbi.payment_source_rows) <> 2
     OR (SELECT count(*) FROM sbi.payments) <> 2
     OR (SELECT count(*) FROM sbi.payment_source_status_v1) <> 2
     OR (SELECT count(*) FROM sbi.payment_received_source_v1) <> 2 THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_SYNTHETIC_FIXTURES_NOT_VERIFIED';
  END IF;
END $preflight$;

SELECT 'DB_R31_11_2_EXISTING_CLONE_READONLY_PREFLIGHT=PASS';
COMMIT;

-- Role A sees one synthetic owner even after attempting GUC owner spoofing.
SET SESSION AUTHORIZATION r311_qa_tenant_a;
BEGIN TRANSACTION READ ONLY;
SET LOCAL app.owner_uid = 'r311-synthetic-owner-b';
DO $tenant_a$
BEGIN
  IF session_user <> 'r311_qa_tenant_a'
     OR current_user <> 'r311_qa_tenant_a'
     OR NOT row_security_active('sbi.import_batches')
     OR NOT row_security_active('sbi.payment_source_rows')
     OR NOT row_security_active('sbi.payments')
     OR NOT row_security_active('sbi.payment_source_status_v1')
     OR r311_auth.current_tenant_uid() <> 'r311-synthetic-owner-a'
     OR (SELECT count(*) FROM sbi.import_batches) <> 1
     OR (SELECT count(*) FROM sbi.payment_source_rows) <> 1
     OR (SELECT count(*) FROM sbi.payments) <> 1
     OR (SELECT count(*) FROM sbi.payment_source_status_v1) <> 1
     OR (SELECT count(*) FROM sbi.payment_received_source_v1) <> 1
     OR (SELECT count(*) FROM sbi.import_batches
           WHERE owner_uid = 'r311-synthetic-owner-b') <> 0
     OR has_table_privilege(current_user,'sbi.import_batches','INSERT,UPDATE,DELETE')
     THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_TENANT_A_ISOLATION';
  END IF;
END $tenant_a$;
SELECT 'DB_R31_11_2_TENANT_A_ISOLATION=PASS';
COMMIT;
RESET SESSION AUTHORIZATION;

-- Role B must independently see only B, never A.
SET SESSION AUTHORIZATION r311_qa_tenant_b;
BEGIN TRANSACTION READ ONLY;
SET LOCAL app.owner_uid = 'r311-synthetic-owner-a';
DO $tenant_b$
BEGIN
  IF session_user <> 'r311_qa_tenant_b'
     OR current_user <> 'r311_qa_tenant_b'
     OR NOT row_security_active('sbi.import_batches')
     OR NOT row_security_active('sbi.payment_source_rows')
     OR NOT row_security_active('sbi.payments')
     OR NOT row_security_active('sbi.payment_source_status_v1')
     OR r311_auth.current_tenant_uid() <> 'r311-synthetic-owner-b'
     OR (SELECT count(*) FROM sbi.import_batches) <> 1
     OR (SELECT count(*) FROM sbi.payment_source_rows) <> 1
     OR (SELECT count(*) FROM sbi.payments) <> 1
     OR (SELECT count(*) FROM sbi.payment_source_status_v1) <> 1
     OR (SELECT count(*) FROM sbi.payment_received_source_v1) <> 1
     OR (SELECT count(*) FROM sbi.import_batches
           WHERE owner_uid = 'r311-synthetic-owner-a') <> 0
     OR has_table_privilege(current_user,'sbi.import_batches','INSERT,UPDATE,DELETE')
     THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_TENANT_B_ISOLATION';
  END IF;
END $tenant_b$;
SELECT 'DB_R31_11_2_TENANT_B_ISOLATION=PASS';
COMMIT;
RESET SESSION AUTHORIZATION;

-- Existing shared report role must not be able to select the invoker view.
SET SESSION AUTHORIZATION sbi_r31_ownerqa_report;
BEGIN TRANSACTION READ ONLY;
DO $legacy$
BEGIN
  IF has_table_privilege(current_user,
        'sbi.payment_received_source_v1','SELECT') THEN
    RAISE EXCEPTION 'STOP=DB_R31_11_2_SHARED_REPORT_GRANT';
  END IF;
  BEGIN
    PERFORM count(*) FROM sbi.payment_received_source_v1;
    RAISE EXCEPTION 'STOP=DB_R31_11_2_SHARED_REPORT_READ_ALLOWED';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
END $legacy$;
SELECT 'DB_R31_11_2_SHARED_REPORT_ACCESS_DENIED=PASS';
COMMIT;
RESET SESSION AUTHORIZATION;

SELECT 'DB_R31_11_2_READONLY_AWS_TENANT_QA=PASS';
