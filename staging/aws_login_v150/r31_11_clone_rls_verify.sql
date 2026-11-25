\set ON_ERROR_STOP on
-- R31.11 synthetic-only fixture in the isolated SCHEMA-ONLY clone.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'sbi_r31_11_tenant_clone_20261125'
    OR current_user <> 'postgres' THEN
   RAISE EXCEPTION 'DB_R3111_VERIFY_NOT_ISOLATED_SUPERUSER';
 END IF;
 IF EXISTS (SELECT 1 FROM sbi.import_batches)
    OR EXISTS (SELECT 1 FROM sbi.payment_source_rows)
    OR EXISTS (SELECT 1 FROM sbi.payments)
    OR EXISTS (SELECT 1 FROM sbi.payment_source_status_v1) THEN
   RAISE EXCEPTION 'DB_R3111_VERIFY_CLONE_ALREADY_HAS_ROWS';
 END IF;
END $guard$;

INSERT INTO sbi.import_batches (
 id,source_system,source_kind,original_file_name,source_sha256,
 owner_uid,source_receipt_id,source_sheet_name,source_parser_version
) VALUES
 ('11111111-1111-4111-8111-111111111111','excel','payment','qa-a.xlsx',
  repeat('a',64),'r311-synthetic-owner-a',repeat('a',32),'PAYMENT EVIDENCE','R31_SOURCE_EVIDENCE_V1'),
 ('22222222-2222-4222-8222-222222222222','excel','payment','qa-b.xlsx',
  repeat('b',64),'r311-synthetic-owner-b',repeat('b',32),'PAYMENT EVIDENCE','R31_SOURCE_EVIDENCE_V1');

INSERT INTO sbi.payment_source_rows (
 id,batch_id,source_row_number,original_values,row_sha256
) VALUES
 ('33333333-3333-4333-8333-333333333333',
  '11111111-1111-4111-8111-111111111111',2,
  '{"Description":"R311 synthetic A","SOL ID":"001505","Credit Amount":"118.00"}'::jsonb,
  repeat('c',64)),
 ('44444444-4444-4444-8444-444444444444',
  '22222222-2222-4222-8222-222222222222',2,
  '{"Description":"R311 synthetic B","SOL ID":"001506","Credit Amount":"357.00"}'::jsonb,
  repeat('d',64));

INSERT INTO sbi.payments (
 id,source_row_id,description,sol_id,credit_paise
) VALUES
 ('55555555-5555-4555-8555-555555555555',
  '33333333-3333-4333-8333-333333333333','R311 synthetic A','001505',11800),
 ('66666666-6666-4666-8666-666666666666',
  '44444444-4444-4444-8444-444444444444','R311 synthetic B','001506',35700);

INSERT INTO sbi.payment_source_status_v1(
 source_row_id,source_status,reason_codes,parser_version
) VALUES
 ('33333333-3333-4333-8333-333333333333','PENDING_RECONCILIATION','[]','R31_SOURCE_EVIDENCE_V1'),
 ('44444444-4444-4444-8444-444444444444','PENDING_RECONCILIATION','[]','R31_SOURCE_EVIDENCE_V1');
COMMIT;

-- Role A: verify all four raw tables and security-invoker view fail closed.
SET SESSION AUTHORIZATION r311_qa_tenant_a;
DO $role_a$
DECLARE c bigint;
BEGIN
 IF session_user <> 'r311_qa_tenant_a'
    OR current_user <> 'r311_qa_tenant_a'
    OR r311_auth.current_tenant_uid() <> 'r311-synthetic-owner-a' THEN
   RAISE EXCEPTION 'DB_R3111_TENANT_A_IDENTITY';
 END IF;
 IF NOT row_security_active('sbi.import_batches')
    OR NOT row_security_active('sbi.payment_source_rows')
    OR NOT row_security_active('sbi.payments')
    OR NOT row_security_active('sbi.payment_source_status_v1') THEN
   RAISE EXCEPTION 'DB_R3111_TENANT_A_RLS_NOT_ACTIVE';
 END IF;
 SELECT count(*) INTO c FROM sbi.payment_received_source_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_A_VIEW_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.import_batches;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_A_BATCH_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payment_source_rows;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_A_ROW_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payments;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_A_PAYMENT_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payment_source_status_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_A_STATUS_LEAK'; END IF;
 PERFORM set_config('app.owner_uid','r311-synthetic-owner-b',false);
 SELECT count(*) INTO c FROM sbi.import_batches
   WHERE owner_uid='r311-synthetic-owner-b';
 IF c <> 0 THEN RAISE EXCEPTION 'DB_R3111_USER_SETTABLE_OWNER_ESCAPED_RLS'; END IF;
 BEGIN
   INSERT INTO sbi.import_batches (
      id,source_system,source_kind,source_sha256,owner_uid
   ) VALUES (
      '77777777-7777-4777-8777-777777777777','excel','payment',
      repeat('e',64),'r311-synthetic-owner-b');
   RAISE EXCEPTION 'DB_R3111_TENANT_A_FINANCIAL_WRITE_ALLOWED';
 EXCEPTION WHEN insufficient_privilege THEN NULL;
 END;
END $role_a$;
RESET SESSION AUTHORIZATION;

-- Role B: independently verify symmetric visibility boundaries.
SET SESSION AUTHORIZATION r311_qa_tenant_b;
DO $role_b$
DECLARE c bigint;
BEGIN
 IF session_user <> 'r311_qa_tenant_b'
    OR r311_auth.current_tenant_uid() <> 'r311-synthetic-owner-b' THEN
   RAISE EXCEPTION 'DB_R3111_TENANT_B_IDENTITY';
 END IF;
 SELECT count(*) INTO c FROM sbi.payment_received_source_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_VIEW_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.import_batches;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_BATCH_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payment_source_rows;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_ROW_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payments;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_PAYMENT_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.payment_source_status_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_STATUS_LEAK'; END IF;
 SELECT count(*) INTO c FROM sbi.import_batches
   WHERE owner_uid='r311-synthetic-owner-a';
 IF c <> 0 THEN RAISE EXCEPTION 'DB_R3111_TENANT_B_FOREIGN_BATCH'; END IF;
END $role_b$;
RESET SESSION AUTHORIZATION;

-- No shared R31.10 report role may read the clone's global source view.
SET SESSION AUTHORIZATION sbi_r31_ownerqa_report;
DO $legacy$
BEGIN
 BEGIN
   PERFORM count(*) FROM sbi.payment_received_source_v1;
   RAISE EXCEPTION 'DB_R3111_SHARED_REPORT_ROLE_STILL_HAS_ACCESS';
 EXCEPTION WHEN insufficient_privilege THEN NULL;
 END;
END $legacy$;
RESET SESSION AUTHORIZATION;

SELECT 'DB_R31_11_CLONE_TWO_ROLE_RAW_TABLE_RLS=PASS';
SELECT 'DB_R31_11_CLONE_SECURITY_INVOKER_VIEW=PASS';
SELECT 'DB_R31_11_SHARED_REPORT_ROLE_DENIED=PASS';
SELECT 'DB_R31_11_ONLY_SYNTHETIC_CLONE_ROWS=PASS';
