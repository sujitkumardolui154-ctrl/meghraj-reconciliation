-- PostgreSQL CI ONLY: minimum structural shape of R31 source tables.
-- This is NOT an AWS migration or replacement for existing approved schema.
\set ON_ERROR_STOP on
CREATE SCHEMA sbi;
CREATE TABLE sbi.import_batches(
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
CREATE UNIQUE INDEX ux_r31_qa_owned_source_sha
 ON sbi.import_batches(owner_uid,source_system,source_kind,source_sha256)
 WHERE owner_uid IS NOT NULL;
CREATE TABLE sbi.payment_source_rows(
 id uuid PRIMARY KEY,
 batch_id uuid NOT NULL REFERENCES sbi.import_batches(id),
 source_row_number integer NOT NULL,
 original_values jsonb NOT NULL,
 row_sha256 text NOT NULL
);
CREATE TABLE sbi.payments(
 id uuid PRIMARY KEY,
 source_row_id uuid NOT NULL REFERENCES sbi.payment_source_rows(id),
 description text,
 sol_id text,
 credit_paise bigint
);
CREATE TABLE sbi.payment_source_status_v1(
 source_row_id uuid PRIMARY KEY REFERENCES sbi.payment_source_rows(id),
 source_status text NOT NULL,
 reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
 parser_version text NOT NULL,
 canonical_sol text,
 official_branch_name text,
 sol_master_sha256 text
);
CREATE VIEW sbi.payment_received_source_v1 AS
SELECT b.owner_uid,b.id AS batch_id,b.source_receipt_id,b.source_sha256,
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
GRANT USAGE ON SCHEMA sbi TO sbi_r31_ownerqa_report;
GRANT SELECT ON sbi.payment_received_source_v1 TO sbi_r31_ownerqa_report;