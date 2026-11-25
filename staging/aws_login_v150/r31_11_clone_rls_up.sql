\set ON_ERROR_STOP on
-- R31.11 CANDIDATE. Only a fresh, schema-only R31 QA clone.
-- Never run on the existing R31 QA database or production ledger.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '50s';

DO $guard$
DECLARE count_rows bigint;
BEGIN
 IF current_database() <> 'sbi_r31_11_tenant_clone_20261125'
    OR session_user <> 'postgres' OR current_user <> 'postgres' THEN
   RAISE EXCEPTION 'DB_R3111_WRONG_DATABASE_OR_PRIVILEGE';
 END IF;
 IF current_setting('server_version_num')::integer < 150000 THEN
   RAISE EXCEPTION 'DB_R3111_SECURITY_INVOKER_REQUIRES_PG15';
 END IF;
 IF to_regclass('sbi.import_batches') IS NULL
    OR to_regclass('sbi.payment_source_rows') IS NULL
    OR to_regclass('sbi.payments') IS NULL
    OR to_regclass('sbi.payment_source_status_v1') IS NULL
    OR to_regclass('sbi.payment_received_source_v1') IS NULL THEN
   RAISE EXCEPTION 'DB_R3111_SOURCE_SCHEMA_NOT_CLONED';
 END IF;
 IF to_regnamespace('r311_auth') IS NOT NULL
    OR EXISTS(SELECT 1 FROM pg_roles
      WHERE rolname IN ('r311_qa_tenant_a','r311_qa_tenant_b')) THEN
   RAISE EXCEPTION 'DB_R3111_ALREADY_APPLIED';
 END IF;
 IF EXISTS (
   SELECT 1 FROM pg_policies
   WHERE schemaname = 'sbi'
     AND tablename IN ('import_batches','payment_source_rows',
                       'payments','payment_source_status_v1')
 ) THEN
   RAISE EXCEPTION 'DB_R3111_EXISTING_POLICIES_REQUIRE_REVIEW';
 END IF;
 SELECT (SELECT count(*) FROM sbi.import_batches)
       +(SELECT count(*) FROM sbi.payment_source_rows)
       +(SELECT count(*) FROM sbi.payments)
       +(SELECT count(*) FROM sbi.payment_source_status_v1)
 INTO count_rows;
 IF count_rows <> 0 THEN
   RAISE EXCEPTION 'DB_R3111_CLONE_MUST_CONTAIN_NO_SOURCE_ROWS';
 END IF;
END $guard$;

-- Proof roles are NOLOGIN, NOINHERIT and NOBYPASSRLS.
-- Approved real tenant identities/credentials must be separately provisioned;
-- this change never modifies a Firebase account.
CREATE ROLE r311_qa_tenant_a NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE r311_qa_tenant_b NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE SCHEMA r311_auth AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA r311_auth FROM PUBLIC;
CREATE TABLE r311_auth.role_owner_map(
  db_role name PRIMARY KEY,
  owner_uid text NOT NULL UNIQUE,
  CHECK (length(owner_uid) BETWEEN 1 AND 200)
);
REVOKE ALL ON r311_auth.role_owner_map FROM PUBLIC;
INSERT INTO r311_auth.role_owner_map(db_role,owner_uid) VALUES
 ('r311_qa_tenant_a','r311-synthetic-owner-a'),
 ('r311_qa_tenant_b','r311-synthetic-owner-b');

-- SECURITY DEFINER can read the protected mapping. session_user stays the
-- authenticated database login role even inside this definer function.
-- Ordinary application input and SET app.owner_uid do not influence it.
CREATE FUNCTION r311_auth.current_tenant_uid()
RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, r311_auth
AS $function$
  SELECT m.owner_uid
  FROM r311_auth.role_owner_map AS m
  WHERE m.db_role = session_user::name
    AND EXISTS (
      SELECT 1 FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = session_user
        AND NOT r.rolsuper AND NOT r.rolbypassrls
    )
$function$;
REVOKE ALL ON FUNCTION r311_auth.current_tenant_uid() FROM PUBLIC;
GRANT USAGE ON SCHEMA r311_auth TO r311_qa_tenant_a,r311_qa_tenant_b;
GRANT EXECUTE ON FUNCTION r311_auth.current_tenant_uid()
 TO r311_qa_tenant_a,r311_qa_tenant_b;

-- FORCE RLS on all four source/credit tables. Default deny for other roles.
ALTER TABLE sbi.import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE sbi.import_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE sbi.payment_source_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE sbi.payment_source_rows FORCE ROW LEVEL SECURITY;
ALTER TABLE sbi.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE sbi.payments FORCE ROW LEVEL SECURITY;
ALTER TABLE sbi.payment_source_status_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE sbi.payment_source_status_v1 FORCE ROW LEVEL SECURITY;

CREATE POLICY r311_batch_read ON sbi.import_batches
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (owner_uid = r311_auth.current_tenant_uid());

CREATE POLICY r311_source_read ON sbi.payment_source_rows
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.import_batches AS b
    WHERE b.id = batch_id
      AND b.owner_uid = r311_auth.current_tenant_uid()
 ));

CREATE POLICY r311_payment_read ON sbi.payments
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.payment_source_rows AS r
    JOIN sbi.import_batches AS b ON b.id = r.batch_id
    WHERE r.id = source_row_id
      AND b.owner_uid = r311_auth.current_tenant_uid()
 ));

CREATE POLICY r311_status_read ON sbi.payment_source_status_v1
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.payment_source_rows AS r
    JOIN sbi.import_batches AS b ON b.id = r.batch_id
    WHERE r.id = source_row_id
      AND b.owner_uid = r311_auth.current_tenant_uid()
 ));

-- Default owner-rights views can bypass RLS. Use invoker security.
ALTER VIEW sbi.payment_received_source_v1 SET (security_invoker=true);
REVOKE ALL ON sbi.payment_received_source_v1
 FROM PUBLIC,sbi_r31_ownerqa_report;
GRANT USAGE ON SCHEMA sbi TO r311_qa_tenant_a,r311_qa_tenant_b;
GRANT SELECT ON sbi.import_batches,sbi.payment_source_rows,
 sbi.payments,sbi.payment_source_status_v1,
 sbi.payment_received_source_v1
 TO r311_qa_tenant_a,r311_qa_tenant_b;

COMMIT;
SELECT 'DB_R31_11_CLONE_TENANT_RLS_MIGRATION=PASS';