\set ON_ERROR_STOP on
-- R31.11.4D-2: approved isolated QA database ONLY.
-- One transaction; no COMMIT; synthetic inserts always ROLLBACK.
-- SET LOCAL SESSION AUTHORIZATION checks RLS as each actual LOGIN identity.
-- Prior real password-authenticated private TCP test remains separate.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='40s';
SET LOCAL idle_in_transaction_session_timeout='60s';

DO $guard$
DECLARE n bigint;
BEGIN
 IF current_database()<>'sbi_r31_11_4_auth_qa_20261126'
    OR session_user<>'postgres' OR current_user<>'postgres'
    OR current_setting('server_version_num')::int NOT BETWEEN 160000 AND 169999
 THEN RAISE EXCEPTION 'STOP=R3114D2_WRONG_QA_DATABASE_OR_PRINCIPAL'; END IF;
 SELECT (SELECT count(*) FROM sbi.import_batches)
      +(SELECT count(*) FROM sbi.payment_source_rows)
      +(SELECT count(*) FROM sbi.payments)
      +(SELECT count(*) FROM sbi.payment_source_status_v1) INTO n;
 IF n<>0
    OR (SELECT count(*) FROM r311_auth.role_owner_map)<>2
    OR (SELECT count(DISTINCT owner_uid) FROM r311_auth.role_owner_map)<>2
    OR (SELECT count(*) FROM pg_roles WHERE rolname IN ('r3113_login_a','r3113_login_b')
        AND rolcanlogin AND rolinherit AND NOT rolsuper AND NOT rolbypassrls)<>2
    OR (SELECT count(*) FROM pg_policies WHERE schemaname='sbi'
        AND policyname IN ('r311_batch_read','r311_source_read',
        'r311_payment_read','r311_status_read') AND cmd='SELECT')<>4
    OR (SELECT count(*) FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
        WHERE ns.nspname='sbi' AND c.relname IN ('import_batches',
        'payment_source_rows','payments','payment_source_status_v1')
        AND c.relrowsecurity AND c.relforcerowsecurity)<>4
    OR (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
        JOIN pg_roles g ON g.oid=m.roleid
        WHERE ((r.rolname='r3113_login_a' AND g.rolname='r311_qa_tenant_a')
            OR (r.rolname='r3113_login_b' AND g.rolname='r311_qa_tenant_b'))
        AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option)<>2
 THEN RAISE EXCEPTION 'STOP=R3114D2_PREFLIGHT_NOT_EMPTY_OR_ROLES_CHANGED'; END IF;
END $guard$;
SELECT 'DB_R31_11_4D2_PRECHECK=PASS_EXACT_PRIVATE_QA_EMPTY';

INSERT INTO sbi.import_batches
 (id,source_system,source_kind,original_file_name,source_sha256,owner_uid)
SELECT v.id,'R3114D2_SYNTHETIC','payment',v.fn,v.sha,m.owner_uid
FROM (VALUES
 ('r3113_login_a'::name,'00000000-0000-4000-8000-0000000000a1'::uuid,'QA_ONLY_A','R3114D2_A_SHA'),
 ('r3113_login_b'::name,'00000000-0000-4000-8000-0000000000a2'::uuid,'QA_ONLY_B','R3114D2_B_SHA')
) AS v(role,id,fn,sha)
JOIN r311_auth.role_owner_map m ON m.db_role=v.role;
INSERT INTO sbi.payment_source_rows
 (id,batch_id,source_row_number,original_values,row_sha256)
VALUES
 ('00000000-0000-4000-8000-0000000000b1','00000000-0000-4000-8000-0000000000a1',1,
  '{"Description":"QA_A","SOL ID":"QA-A","Credit Amount":"1.00"}'::jsonb,'R3114D2_ROW_A'),
 ('00000000-0000-4000-8000-0000000000b2','00000000-0000-4000-8000-0000000000a2',1,
  '{"Description":"QA_B","SOL ID":"QA-B","Credit Amount":"2.00"}'::jsonb,'R3114D2_ROW_B');
INSERT INTO sbi.payments (id,source_row_id,description,sol_id,credit_paise)
VALUES
 ('00000000-0000-4000-8000-0000000000c1','00000000-0000-4000-8000-0000000000b1','QA_A','QA-A',100),
 ('00000000-0000-4000-8000-0000000000c2','00000000-0000-4000-8000-0000000000b2','QA_B','QA-B',200);
INSERT INTO sbi.payment_source_status_v1
 (source_row_id,source_status,reason_codes,parser_version)
VALUES
 ('00000000-0000-4000-8000-0000000000b1','QA_SYNTHETIC','[]'::jsonb,'R3114D2_ONLY'),
 ('00000000-0000-4000-8000-0000000000b2','QA_SYNTHETIC','[]'::jsonb,'R3114D2_ONLY');
DO $qa$
BEGIN
 IF (SELECT count(*) FROM sbi.import_batches)<>2
 OR (SELECT count(*) FROM sbi.payment_source_rows)<>2
 OR (SELECT count(*) FROM sbi.payments)<>2
 OR (SELECT count(*) FROM sbi.payment_source_status_v1)<>2
 THEN RAISE EXCEPTION 'STOP=R3114D2_FIXTURE_MISMATCH'; END IF;
END $qa$;
SELECT 'DB_R31_11_4D2_SYNTHETIC_FIXTURES=PASS_TWO_EACH_UNCOMMITTED';

SET LOCAL SESSION AUTHORIZATION 'r3113_login_a';
DO $qa_a$
BEGIN
 IF session_user<>'r3113_login_a' OR current_user<>'r3113_login_a'
    OR r311_auth.current_tenant_uid() IS NULL
    OR (SELECT count(*) FROM sbi.import_batches)<>1
    OR (SELECT count(*) FROM sbi.payment_source_rows)<>1
    OR (SELECT count(*) FROM sbi.payments)<>1
    OR (SELECT count(*) FROM sbi.payment_source_status_v1)<>1
    OR (SELECT count(*) FROM sbi.payment_received_source_v1)<>1
    OR (SELECT count(*) FROM sbi.import_batches WHERE id='00000000-0000-4000-8000-0000000000a1')<>1
    OR (SELECT count(*) FROM sbi.import_batches WHERE id='00000000-0000-4000-8000-0000000000a2')<>0
    OR (SELECT count(*) FROM sbi.payments WHERE source_row_id='00000000-0000-4000-8000-0000000000b2')<>0
    OR (SELECT count(*) FROM sbi.payment_received_source_v1
        WHERE owner_uid<>r311_auth.current_tenant_uid())<>0
 THEN RAISE EXCEPTION 'STOP=R3114D2_TENANT_A_RLS_FAILURE'; END IF;
 BEGIN
  PERFORM count(*) FROM r311_auth.role_owner_map;
  RAISE EXCEPTION 'STOP=R3114D2_A_MAPPING_READ_WAS_ALLOWED';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN
  INSERT INTO sbi.import_batches(id,source_system,source_kind,source_sha256)
   VALUES('00000000-0000-4000-8000-0000000000f1','QA','payment','DENY_A');
  RAISE EXCEPTION 'STOP=R3114D2_A_WRITE_WAS_ALLOWED';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $qa_a$;
SELECT 'DB_R31_11_4D2_TENANT_A_OWN_READ=PASS';
SELECT 'DB_R31_11_4D2_TENANT_A_CROSS_READ=DENIED_PASS';
SELECT 'DB_R31_11_4D2_TENANT_A_MAP_AND_WRITE=DENIED_PASS';
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION 'r3113_login_b';
DO $qa_b$
BEGIN
 IF session_user<>'r3113_login_b' OR current_user<>'r3113_login_b'
    OR r311_auth.current_tenant_uid() IS NULL
    OR (SELECT count(*) FROM sbi.import_batches)<>1
    OR (SELECT count(*) FROM sbi.payment_source_rows)<>1
    OR (SELECT count(*) FROM sbi.payments)<>1
    OR (SELECT count(*) FROM sbi.payment_source_status_v1)<>1
    OR (SELECT count(*) FROM sbi.payment_received_source_v1)<>1
    OR (SELECT count(*) FROM sbi.import_batches WHERE id='00000000-0000-4000-8000-0000000000a2')<>1
    OR (SELECT count(*) FROM sbi.import_batches WHERE id='00000000-0000-4000-8000-0000000000a1')<>0
    OR (SELECT count(*) FROM sbi.payments WHERE source_row_id='00000000-0000-4000-8000-0000000000b1')<>0
    OR (SELECT count(*) FROM sbi.payment_received_source_v1
        WHERE owner_uid<>r311_auth.current_tenant_uid())<>0
 THEN RAISE EXCEPTION 'STOP=R3114D2_TENANT_B_RLS_FAILURE'; END IF;
 BEGIN
  PERFORM count(*) FROM r311_auth.role_owner_map;
  RAISE EXCEPTION 'STOP=R3114D2_B_MAPPING_READ_WAS_ALLOWED';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN
  INSERT INTO sbi.import_batches(id,source_system,source_kind,source_sha256)
   VALUES('00000000-0000-4000-8000-0000000000f2','QA','payment','DENY_B');
  RAISE EXCEPTION 'STOP=R3114D2_B_WRITE_WAS_ALLOWED';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $qa_b$;
SELECT 'DB_R31_11_4D2_TENANT_B_OWN_READ=PASS';
SELECT 'DB_R31_11_4D2_TENANT_B_CROSS_READ=DENIED_PASS';
SELECT 'DB_R31_11_4D2_TENANT_B_MAP_AND_WRITE=DENIED_PASS';
RESET SESSION AUTHORIZATION;
DO $end$
BEGIN
 IF session_user<>'postgres' OR current_user<>'postgres'
  OR (SELECT count(*) FROM sbi.import_batches)<>2
  OR (SELECT count(*) FROM sbi.payment_source_rows)<>2
  OR (SELECT count(*) FROM sbi.payments)<>2
  OR (SELECT count(*) FROM sbi.payment_source_status_v1)<>2
 THEN RAISE EXCEPTION 'STOP=R3114D2_FINAL_STATE_INVALID'; END IF;
END $end$;
-- Critical: no COMMIT. Disconnect/error before this line also rolls back.
ROLLBACK;
SELECT 'DB_R31_11_4D2_TRANSACTION=ROLLBACK_COMPLETE';
