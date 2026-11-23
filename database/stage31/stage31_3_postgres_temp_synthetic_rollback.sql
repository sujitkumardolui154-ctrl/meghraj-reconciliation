-- Stage 31.3. Synthetic transaction & rollback QA only, in built-in maintenance
-- database postgres. No modification of sbi_reconciliation_main or its tables.
-- psql must use -X -v ON_ERROR_STOP=1 -d postgres. All created objects are
-- TEMP tables inside BEGIN and explicitly ROLLBACK at the end.
BEGIN;
SET LOCAL statement_timeout = '15000ms';
DO $$
BEGIN
 IF current_database() <> 'postgres' THEN
  RAISE EXCEPTION 'STAGE31_3_WRONG_DATABASE_MUST_USE_MAINTENANCE_POSTGRES';
 END IF;
END
$$;

CREATE TEMP TABLE sbi_stage31_3_synthetic_invoices (
 invoice_number text PRIMARY KEY,
 source_key text NOT NULL UNIQUE,
 taxable_paise bigint NOT NULL CHECK(taxable_paise >= 0),
 cgst_paise bigint NOT NULL CHECK(cgst_paise >= 0),
 sgst_paise bigint NOT NULL CHECK(sgst_paise >= 0),
 gross_paise bigint NOT NULL CHECK(gross_paise =
             taxable_paise + cgst_paise + sgst_paise)
) ON COMMIT DROP;

CREATE TEMP TABLE sbi_stage31_3_synthetic_payments (
 synthetic_bank_ref text PRIMARY KEY,
 source_key text NOT NULL UNIQUE,
 bank_date date NOT NULL,
 sol_id text NOT NULL,
 credit_paise bigint NOT NULL CHECK(credit_paise > 0)
) ON COMMIT DROP;

-- One valid invoice and bank-credit row; values are fabricated for test QA.
INSERT INTO sbi_stage31_3_synthetic_invoices
(invoice_number,source_key,taxable_paise,cgst_paise,sgst_paise,gross_paise)
VALUES ('STAGE31-TEST-001','test-src-row-2',100000,9000,9000,118000);

INSERT INTO sbi_stage31_3_synthetic_payments
(synthetic_bank_ref,source_key,bank_date,sol_id,credit_paise)
VALUES ('STAGE31-TEST-BANK-001','test-bank-src-row-12','2026-11-01',
        '001505',11384);

-- Verify duplicate and source identity constraints fail atomically.
DO $$
DECLARE rejected boolean;
BEGIN
 rejected:=false;
 BEGIN
   INSERT INTO sbi_stage31_3_synthetic_invoices
   VALUES ('STAGE31-TEST-001','test-src-row-3',100000,9000,9000,118000);
 EXCEPTION WHEN unique_violation THEN rejected:=true;
 END;
 IF NOT rejected THEN RAISE EXCEPTION 'DUPLICATE_INVOICE_NOT_REJECTED'; END IF;

 rejected:=false;
 BEGIN
   INSERT INTO sbi_stage31_3_synthetic_invoices
   VALUES ('STAGE31-TEST-002','test-src-row-2',100000,9000,9000,118000);
 EXCEPTION WHEN unique_violation THEN rejected:=true;
 END;
 IF NOT rejected THEN RAISE EXCEPTION 'DUPLICATE_SOURCE_ROW_NOT_REJECTED'; END IF;

 rejected:=false;
 BEGIN
   INSERT INTO sbi_stage31_3_synthetic_payments
   VALUES ('STAGE31-TEST-BANK-002','test-bank-src-row-12',
           '2026-11-01','001505',11384);
 EXCEPTION WHEN unique_violation THEN rejected:=true;
 END;
 IF NOT rejected THEN RAISE EXCEPTION 'DUPLICATE_PAYMENT_SOURCE_NOT_REJECTED'; END IF;

 rejected:=false;
 BEGIN
   INSERT INTO sbi_stage31_3_synthetic_payments
   VALUES ('STAGE31-TEST-BANK-003','test-bank-src-row-13',
           '2026-11-01','001505',0);
 EXCEPTION WHEN check_violation THEN rejected:=true;
 END;
 IF NOT rejected THEN RAISE EXCEPTION 'ZERO_BANK_CREDIT_NOT_REJECTED'; END IF;

 rejected:=false;
 BEGIN
   INSERT INTO sbi_stage31_3_synthetic_invoices
   VALUES ('STAGE31-TEST-003','test-src-row-7',100000,9000,9000,117999);
 EXCEPTION WHEN check_violation THEN rejected:=true;
 END;
 IF NOT rejected THEN RAISE EXCEPTION 'GROSS_MISMATCH_NOT_REJECTED'; END IF;
END
$$;

SELECT 'STAGE31_3_DUPLICATE_AND_AMOUNT_CONSTRAINT_QA=PASS';

-- Transactional rollback rehearsal: synthetic second batch never survives.
SAVEPOINT stage31_synthetic_batch;
INSERT INTO sbi_stage31_3_synthetic_invoices
 VALUES ('STAGE31-TEST-NEW','test-src-new',500,45,45,590);
INSERT INTO sbi_stage31_3_synthetic_payments
 VALUES ('STAGE31-TEST-BANK-NEW','test-bank-new','2026-11-02','001505',590);
ROLLBACK TO SAVEPOINT stage31_synthetic_batch;

DO $$
BEGIN
 IF (SELECT count(*) FROM sbi_stage31_3_synthetic_invoices) <> 1
 OR (SELECT count(*) FROM sbi_stage31_3_synthetic_payments) <> 1 THEN
  RAISE EXCEPTION 'SAVEPOINT_ROLLBACK_FAILED';
 END IF;
 IF EXISTS (SELECT 1 FROM sbi_stage31_3_synthetic_invoices
            WHERE invoice_number='STAGE31-TEST-NEW') THEN
  RAISE EXCEPTION 'ROLLED_BACK_INVOICE_VISIBLE';
 END IF;
END
$$;
SELECT 'STAGE31_3_TRANSACTION_ROLLBACK_QA=PASS';

-- Explicit global rollback (including creation of both temporary tables).
ROLLBACK;
SELECT CASE WHEN to_regclass('pg_temp.sbi_stage31_3_synthetic_invoices') IS NULL
               AND to_regclass('pg_temp.sbi_stage31_3_synthetic_payments') IS NULL
 THEN 'STAGE31_3_TEMP_OBJECT_CLEANUP=PASS'
 ELSE 'STAGE31_3_TEMP_OBJECT_CLEANUP=FAIL'
 END;
SELECT 'STAGE31_3_MAINTENANCE_DB_SYNTHETIC_TEMP_TRANSACTION=PASS';
