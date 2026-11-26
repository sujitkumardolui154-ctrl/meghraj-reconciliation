\set ON_ERROR_STOP on
-- DB-R31.11.4B: EMPTY, DEDICATED QA DATABASE ONLY.
-- Reviewed structure derived from R31.11 CI source shape + R31.11 RLS
-- principles. No real customer rows, no Firebase users, no LOGIN roles.
-- This file is NOT a financial production migration. One-time only.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '45s';

DO $guard$
DECLARE public_objects bigint;
BEGIN
  IF current_database() <> 'sbi_r31_11_4_auth_qa_20261126'
     OR current_user <> 'postgres' OR session_user <> 'postgres'
     OR current_setting('server_version_num')::int < 160000
     OR current_setting('server_version_num')::int >= 170000
  THEN
    RAISE EXCEPTION 'R3114B_EXACT_NEW_PG16_QA_IDENTITY_REQUIRED';
  END IF;
  IF to_regnamespace('sbi') IS NOT NULL
     OR to_regnamespace('r311_auth') IS NOT NULL
     OR EXISTS (
       SELECT 1 FROM pg_roles WHERE rolname IN (
          'r311_qa_tenant_a','r311_qa_tenant_b',
          'r3113_login_a','r3113_login_b','sbi_r31_ownerqa_report'
       )
     ) THEN
    RAISE EXCEPTION 'R3114B_PREEXISTING_OBJECTS_OR_ROLES_REFUSED';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace
      WHERE nspname NOT IN ('pg_catalog','information_schema','public')
        AND nspname NOT LIKE 'pg_toast%'
        AND nspname NOT LIKE 'pg_temp_%') THEN
    RAISE EXCEPTION 'R3114B_UNEXPECTED_NAMESPACE';
  END IF;
  SELECT count(*) INTO public_objects
  FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
  WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f');
  IF public_objects <> 0 THEN
    RAISE EXCEPTION 'R3114B_DATABASE_MUST_BE_EMPTY';
  END IF;
END $guard$;

-- Initially no LOGIN principals. Future real Firebase UIDs MUST be mapped
-- only in a separately approved R31.11.4C step. Never insert fake UIDs here.
CREATE ROLE r311_qa_tenant_a NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE r311_qa_tenant_b NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOBYPASSRLS;

CREATE SCHEMA sbi AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA sbi FROM PUBLIC;
CREATE TABLE sbi.import_batches (
  id uuid PRIMARY KEY,
  source_system text NOT NULL,
  source_kind text NOT NULL,
  original_file_name text,
  source_sha256 text NOT NULL,
  owner_uid text,
  source_receipt_id text,
  source_sheet_name text,
  source_parser_version text
);
CREATE UNIQUE INDEX ux_r3114b_owned_source_sha
 ON sbi.import_batches(owner_uid,source_system,source_kind,source_sha256)
 WHERE owner_uid IS NOT NULL;

CREATE TABLE sbi.payment_source_rows (
  id uuid PRIMARY KEY,
  batch_id uuid NOT NULL REFERENCES sbi.import_batches(id),
  source_row_number integer NOT NULL,
  original_values jsonb NOT NULL,
  row_sha256 text NOT NULL
);
CREATE TABLE sbi.payments (
  id uuid PRIMARY KEY,
  source_row_id uuid NOT NULL REFERENCES sbi.payment_source_rows(id),
  description text,
  sol_id text,
  credit_paise bigint
);
CREATE TABLE sbi.payment_source_status_v1 (
  source_row_id uuid PRIMARY KEY REFERENCES sbi.payment_source_rows(id),
  source_status text NOT NULL,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  parser_version text NOT NULL,
  canonical_sol text,
  official_branch_name text,
  sol_master_sha256 text
);

CREATE VIEW sbi.payment_received_source_v1
 WITH (security_invoker=true) AS
SELECT
 b.owner_uid,b.id AS batch_id,b.source_receipt_id,b.source_sha256,
 b.source_sheet_name,r.id AS source_row_id,r.source_row_number,
 r.row_sha256,r.original_values,
 r.original_values->>'Description' AS description,
 r.original_values->>'SOL ID' AS raw_sol,
 r.original_values->>'Credit Amount' AS raw_credit_amount,
 p.id AS payment_id,p.credit_paise,
 COALESCE(st.source_status,'UNCLASSIFIED_LEGACY') AS source_status,
 COALESCE(st.reason_codes,'[]'::jsonb) AS reason_codes,
 st.canonical_sol,st.official_branch_name,st.sol_master_sha256,
 st.parser_version,'NOT_CALCULATED'::text AS reconciliation_status
FROM sbi.import_batches b
JOIN sbi.payment_source_rows r ON r.batch_id=b.id
LEFT JOIN sbi.payments p ON p.source_row_id=r.id
LEFT JOIN sbi.payment_source_status_v1 st ON st.source_row_id=r.id
WHERE b.source_kind='payment';

CREATE SCHEMA r311_auth AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA r311_auth FROM PUBLIC;
CREATE TABLE r311_auth.role_owner_map (
  db_role name PRIMARY KEY,
  owner_uid text NOT NULL UNIQUE,
  CONSTRAINT owner_uid_length CHECK (length(owner_uid) BETWEEN 1 AND 200)
);
REVOKE ALL ON TABLE r311_auth.role_owner_map FROM PUBLIC;

CREATE FUNCTION r311_auth.current_tenant_uid()
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, r311_auth
AS $uid$
  SELECT m.owner_uid
  FROM r311_auth.role_owner_map AS m
  WHERE m.db_role = session_user::name
    AND EXISTS (
      SELECT 1 FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = session_user
        AND r.rolcanlogin
        AND NOT r.rolsuper AND NOT r.rolbypassrls
    )
$uid$;
REVOKE ALL ON FUNCTION r311_auth.current_tenant_uid() FROM PUBLIC;
GRANT USAGE ON SCHEMA r311_auth TO r311_qa_tenant_a,r311_qa_tenant_b;
GRANT EXECUTE ON FUNCTION r311_auth.current_tenant_uid()
  TO r311_qa_tenant_a,r311_qa_tenant_b;

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
 USING (owner_uid=r311_auth.current_tenant_uid());

CREATE POLICY r311_source_read ON sbi.payment_source_rows
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.import_batches AS b
    WHERE b.id=batch_id AND b.owner_uid=r311_auth.current_tenant_uid()
 ));
CREATE POLICY r311_payment_read ON sbi.payments
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.payment_source_rows AS r
    JOIN sbi.import_batches AS b ON b.id=r.batch_id
    WHERE r.id=source_row_id
      AND b.owner_uid=r311_auth.current_tenant_uid()
 ));
CREATE POLICY r311_status_read ON sbi.payment_source_status_v1
 FOR SELECT TO r311_qa_tenant_a,r311_qa_tenant_b
 USING (EXISTS (
    SELECT 1 FROM sbi.payment_source_rows AS r
    JOIN sbi.import_batches AS b ON b.id=r.batch_id
    WHERE r.id=source_row_id
      AND b.owner_uid=r311_auth.current_tenant_uid()
 ));

REVOKE ALL ON ALL TABLES IN SCHEMA sbi FROM PUBLIC;
GRANT USAGE ON SCHEMA sbi TO r311_qa_tenant_a,r311_qa_tenant_b;
GRANT SELECT ON sbi.import_batches,sbi.payment_source_rows,
  sbi.payments,sbi.payment_source_status_v1,
  sbi.payment_received_source_v1
 TO r311_qa_tenant_a,r311_qa_tenant_b;

-- Security posture when this transaction commits:
-- (1) four forced-RLS source tables, (2) exactly four SELECT policies,
-- (3) invoker view, (4) two NOLOGIN group roles,
-- (5) ZERO mappings, LOGIN principals or payment evidence rows.
DO $proof$
DECLARE
  group_roles int;
  policies int;
  forced int;
  logins int;
  data_rows bigint;
BEGIN
  SELECT count(*) INTO group_roles FROM pg_roles
  WHERE rolname IN ('r311_qa_tenant_a','r311_qa_tenant_b')
    AND NOT rolcanlogin AND NOT rolinherit
    AND NOT rolsuper AND NOT rolbypassrls
    AND NOT rolcreaterole AND NOT rolcreatedb;
  SELECT count(*) INTO forced FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='sbi' AND c.relname IN (
    'import_batches','payment_source_rows',
    'payments','payment_source_status_v1'
  ) AND c.relrowsecurity AND c.relforcerowsecurity;
  SELECT count(*) INTO policies FROM pg_policies
  WHERE schemaname='sbi' AND policyname IN (
    'r311_batch_read','r311_source_read',
    'r311_payment_read','r311_status_read')
    AND cmd='SELECT';
  SELECT count(*) INTO logins FROM pg_roles
  WHERE rolname IN ('r3113_login_a','r3113_login_b');
  SELECT (SELECT count(*) FROM sbi.import_batches)
    +(SELECT count(*) FROM sbi.payment_source_rows)
    +(SELECT count(*) FROM sbi.payments)
    +(SELECT count(*) FROM sbi.payment_source_status_v1)
    +(SELECT count(*) FROM r311_auth.role_owner_map)
  INTO data_rows;
  IF group_roles<>2 OR forced<>4 OR policies<>4
    OR logins<>0 OR data_rows<>0
    OR NOT EXISTS (
      SELECT 1 FROM pg_class c
      WHERE c.oid=to_regclass('sbi.payment_received_source_v1')
      AND 'security_invoker=true'=ANY(c.reloptions))
  THEN
    RAISE EXCEPTION 'R3114B_IN_TRANSACTION_CATALOG_PROOF_FAILED';
  END IF;
END $proof$;
COMMIT;
SELECT 'DB_R31_11_4B_SCHEMA_RLS_BOOTSTRAP=PASS_NO_REAL_USERS';
