\set ON_ERROR_STOP on
-- CI DISPOSABLE POSTGRES ONLY. The passwords below are public test strings,
-- NOT secrets and MUST NOT be used outside ephemeral CI. Never apply to AWS.
DO $guard$
BEGIN
 IF current_database()<>'sbi_r31_11_tenant_clone_20261125' THEN
   RAISE EXCEPTION 'CI_DISPOSABLE_DB_REQUIRED';
 END IF;
END $guard$;

CREATE ROLE r3113_login_a LOGIN INHERIT NOSUPERUSER NOCREATEDB
 NOCREATEROLE NOBYPASSRLS PASSWORD 'ci-r3113-A-disposable-password';
CREATE ROLE r3113_login_b LOGIN INHERIT NOSUPERUSER NOCREATEDB
 NOCREATEROLE NOBYPASSRLS PASSWORD 'ci-r3113-B-disposable-password';
-- Existing group roles stay NOLOGIN, NOINHERIT, NOBYPASSRLS.
-- A restricted login inherits ONLY its own restricted read group rights.
GRANT r311_qa_tenant_a TO r3113_login_a WITH INHERIT TRUE, SET FALSE;
GRANT r311_qa_tenant_b TO r3113_login_b WITH INHERIT TRUE, SET FALSE;
INSERT INTO r311_auth.role_owner_map(db_role,owner_uid) VALUES
 ('r3113_login_a','r3113-firebase-a'),
 ('r3113_login_b','r3113-firebase-b');

INSERT INTO sbi.import_batches(
 id,source_system,source_kind,original_file_name,source_sha256,
 owner_uid,source_receipt_id,source_sheet_name,source_parser_version
) VALUES
 ('88888888-8888-4888-8888-888888888888','excel','payment',
  'qa-r3113-a.xlsx',repeat('8',64),'r3113-firebase-a',
  repeat('8',32),'PAYMENT EVIDENCE','R31_SOURCE_EVIDENCE_V1'),
 ('99999999-9999-4999-8999-999999999999','excel','payment',
  'qa-r3113-b.xlsx',repeat('9',64),'r3113-firebase-b',
  repeat('9',32),'PAYMENT EVIDENCE','R31_SOURCE_EVIDENCE_V1');
INSERT INTO sbi.payment_source_rows(id,batch_id,source_row_number,original_values,row_sha256)
 VALUES
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  '88888888-8888-4888-8888-888888888888',2,
  '{"Description":"CI A","SOL ID":"001505","Credit Amount":"118.00"}'::jsonb,
  repeat('a',64)),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  '99999999-9999-4999-8999-999999999999',2,
  '{"Description":"CI B","SOL ID":"001506","Credit Amount":"357.00"}'::jsonb,
  repeat('b',64));
INSERT INTO sbi.payments(id,source_row_id,description,sol_id,credit_paise)
 VALUES
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','CI A','001505',11800),
 ('dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','CI B','001506',35700);
INSERT INTO sbi.payment_source_status_v1(
 source_row_id,source_status,reason_codes,parser_version
) VALUES
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  'PENDING_RECONCILIATION','[]'::jsonb,'R31_SOURCE_EVIDENCE_V1'),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  'PENDING_RECONCILIATION','[]'::jsonb,'R31_SOURCE_EVIDENCE_V1');

SELECT 'DB_R31_11_3_EPHEMERAL_LOGIN_ROLES_PROVISIONED=PASS';
