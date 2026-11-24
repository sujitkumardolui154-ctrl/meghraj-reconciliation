\set ON_ERROR_STOP on
-- R31.10: transaction-scoped synthetic RLS demonstration ONLY.
-- NEVER modify existing sbi schema, production database or financial rows.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $guard$
BEGIN
  IF current_database() <> 'sbi_r31_owner_qa_20261125'
     OR session_user <> 'postgres'
     OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'DB_R31_10_NOT_ISOLATED_QA_POSTGRES';
  END IF;
  IF current_setting('server_version_num')::integer < 150000 THEN
    RAISE EXCEPTION 'DB_R31_10_SECURITY_INVOKER_REQUIRES_PG15';
  END IF;
  IF to_regclass('sbi.import_batches') IS NULL
     OR to_regclass('sbi.payments') IS NULL
     OR to_regclass('sbi.payment_source_rows') IS NULL THEN
    RAISE EXCEPTION 'DB_R31_10_APPROVED_QA_SCHEMA_MISSING';
  END IF;
  IF to_regnamespace('r31_10_shadow') IS NOT NULL
     OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN
        ('r31_10_tenant_a','r31_10_tenant_b')) THEN
    RAISE EXCEPTION 'DB_R31_10_EXISTING_SHADOW_OBJECTS';
  END IF;
END $guard$;

CREATE ROLE r31_10_tenant_a NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE r31_10_tenant_b NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE SCHEMA r31_10_shadow AUTHORIZATION postgres;

CREATE TABLE r31_10_shadow.import_batches (
  id text PRIMARY KEY,
  owner_role name NOT NULL,
  UNIQUE (id, owner_role)
);
CREATE TABLE r31_10_shadow.payment_source_rows (
  id text PRIMARY KEY,
  batch_id text NOT NULL,
  owner_role name NOT NULL,
  FOREIGN KEY (batch_id, owner_role)
    REFERENCES r31_10_shadow.import_batches(id,owner_role),
  UNIQUE (id, owner_role)
);
CREATE TABLE r31_10_shadow.payments (
  id text PRIMARY KEY,
  source_row_id text NOT NULL,
  owner_role name NOT NULL,
  credit_paise bigint NOT NULL,
  FOREIGN KEY (source_row_id, owner_role)
    REFERENCES r31_10_shadow.payment_source_rows(id,owner_role)
);

ALTER TABLE r31_10_shadow.import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE r31_10_shadow.payment_source_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE r31_10_shadow.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE r31_10_shadow.import_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE r31_10_shadow.payment_source_rows FORCE ROW LEVEL SECURITY;
ALTER TABLE r31_10_shadow.payments FORCE ROW LEVEL SECURITY;

CREATE POLICY r31_tenant_batch_policy ON r31_10_shadow.import_batches
  USING (owner_role = current_user) WITH CHECK (owner_role = current_user);
CREATE POLICY r31_tenant_source_policy ON r31_10_shadow.payment_source_rows
  USING (owner_role = current_user) WITH CHECK (owner_role = current_user);
CREATE POLICY r31_tenant_payment_policy ON r31_10_shadow.payments
  USING (owner_role = current_user) WITH CHECK (owner_role = current_user);

-- Invoker view is essential: default definer views can bypass underlying RLS.
CREATE VIEW r31_10_shadow.received_source_v1
  WITH (security_invoker = true) AS
SELECT b.owner_role, b.id AS batch_id, r.id AS source_row_id,
       p.id AS payment_id, p.credit_paise
FROM r31_10_shadow.import_batches b
JOIN r31_10_shadow.payment_source_rows r
  ON r.batch_id = b.id AND r.owner_role = b.owner_role
JOIN r31_10_shadow.payments p
  ON p.source_row_id = r.id AND p.owner_role = r.owner_role;

GRANT USAGE ON SCHEMA r31_10_shadow TO r31_10_tenant_a,r31_10_tenant_b;
GRANT SELECT ON ALL TABLES IN SCHEMA r31_10_shadow
  TO r31_10_tenant_a,r31_10_tenant_b;
-- Separate synthetic write-negative test; does NOT grant INSERT to real QA roles.
GRANT INSERT ON r31_10_shadow.import_batches
  TO r31_10_tenant_a,r31_10_tenant_b;

INSERT INTO r31_10_shadow.import_batches VALUES
  ('batch-a','r31_10_tenant_a'),('batch-b','r31_10_tenant_b');
INSERT INTO r31_10_shadow.payment_source_rows VALUES
  ('source-a','batch-a','r31_10_tenant_a'),
  ('source-b','batch-b','r31_10_tenant_b');
INSERT INTO r31_10_shadow.payments VALUES
  ('payment-a','source-a','r31_10_tenant_a',11800),
  ('payment-b','source-b','r31_10_tenant_b',35700);

SET ROLE r31_10_tenant_a;
DO $test_a$
DECLARE c int;
BEGIN
 IF current_user <> 'r31_10_tenant_a' THEN
   RAISE EXCEPTION 'DB_R31_10_A_ROLE_NOT_ACTIVE';
 END IF;
 SELECT count(*) INTO c FROM r31_10_shadow.received_source_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R31_10_A_VIEW_CROSS_TENANT'; END IF;
 SELECT count(*) INTO c FROM r31_10_shadow.payments
   WHERE owner_role='r31_10_tenant_b';
 IF c <> 0 THEN RAISE EXCEPTION 'DB_R31_10_A_RAW_CROSS_TENANT'; END IF;
 BEGIN
   INSERT INTO r31_10_shadow.import_batches VALUES
     ('forbidden-a','r31_10_tenant_b');
   RAISE EXCEPTION 'DB_R31_10_A_FOREIGN_WRITE_NOT_REJECTED';
 EXCEPTION
   WHEN insufficient_privilege THEN NULL;
 END;
END $test_a$;
RESET ROLE;

SET ROLE r31_10_tenant_b;
DO $test_b$
DECLARE c int;
BEGIN
 IF current_user <> 'r31_10_tenant_b' THEN
   RAISE EXCEPTION 'DB_R31_10_B_ROLE_NOT_ACTIVE';
 END IF;
 SELECT count(*) INTO c FROM r31_10_shadow.received_source_v1;
 IF c <> 1 THEN RAISE EXCEPTION 'DB_R31_10_B_VIEW_CROSS_TENANT'; END IF;
 SELECT count(*) INTO c FROM r31_10_shadow.payments
   WHERE owner_role='r31_10_tenant_a';
 IF c <> 0 THEN RAISE EXCEPTION 'DB_R31_10_B_RAW_CROSS_TENANT'; END IF;
 BEGIN
   INSERT INTO r31_10_shadow.import_batches VALUES
     ('forbidden-b','r31_10_tenant_a');
   RAISE EXCEPTION 'DB_R31_10_B_FOREIGN_WRITE_NOT_REJECTED';
 EXCEPTION
   WHEN insufficient_privilege THEN NULL;
 END;
END $test_b$;
RESET ROLE;

-- Everything (including CREATE ROLE/SCHEMA) is discarded on successful run.
ROLLBACK;
DO $verify$
BEGIN
 IF to_regnamespace('r31_10_shadow') IS NOT NULL
    OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN
        ('r31_10_tenant_a','r31_10_tenant_b')) THEN
   RAISE EXCEPTION 'DB_R31_10_SHADOW_ROLLBACK_INCOMPLETE';
 END IF;
END $verify$;
SELECT 'DB_R31_10_SHADOW_RLS_BIDIRECTIONAL=PASS';
SELECT 'DB_R31_10_SHADOW_RLS_CLEANUP=PASS';
