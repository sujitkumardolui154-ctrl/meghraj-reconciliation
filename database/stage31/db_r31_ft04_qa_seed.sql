-- DB-R31.3 synthetic QA baseline ONLY. Not for AWS financial DB.
-- Minimal FT-04 relational layout for isolated ephemeral Docker PostgreSQL.
\set ON_ERROR_STOP on
BEGIN;
DO $gate$
BEGIN
 IF current_database() <> 'sbi_ft04g_clean_0e858f93' THEN
   RAISE EXCEPTION 'DB_R31_QA_ONLY_WRONG_DATABASE';
 END IF;
 IF to_regclass('sbi.import_batches') IS NOT NULL
    OR to_regclass('sbi.payment_source_rows') IS NOT NULL
    OR to_regclass('sbi.payments') IS NOT NULL THEN
   RAISE EXCEPTION 'DB_R31_QA_BASELINE_MUST_BE_EMPTY';
 END IF;
END $gate$;

CREATE SCHEMA IF NOT EXISTS sbi;
CREATE TABLE sbi.import_batches (
 id uuid PRIMARY KEY,
 source_system text NOT NULL,
 source_kind text NOT NULL,
 original_file_name text NOT NULL,
 source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 UNIQUE(source_system,source_kind,source_sha256)
);
CREATE TABLE sbi.payment_source_rows (
 id uuid PRIMARY KEY,
 batch_id uuid NOT NULL REFERENCES sbi.import_batches(id) ON DELETE RESTRICT,
 source_row_number integer NOT NULL CHECK (source_row_number>=2),
 original_values jsonb NOT NULL,
 row_sha256 text NOT NULL CHECK (row_sha256 ~ '^[0-9a-f]{64}$'),
 UNIQUE(batch_id,source_row_number)
);
CREATE TABLE sbi.payments (
 id uuid PRIMARY KEY,
 source_row_id uuid NOT NULL UNIQUE
  REFERENCES sbi.payment_source_rows(id) ON DELETE RESTRICT,
 description text NOT NULL,
 sol_id text NOT NULL,
 credit_paise bigint NOT NULL CHECK (credit_paise>0)
);
-- Existing isolated schema QA script counts invoices also. Only synthetic.
CREATE TABLE sbi.invoices (
 id uuid PRIMARY KEY
);
COMMIT;
SELECT 'DB_R31_SYNTHETIC_QA_BASELINE=PASS';
