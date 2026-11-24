-- DB-R31.1: single read-only catalog for existing central sbi_reconciliation_main.
-- Metadata only. Never retrieve customer/payment/invoice values.
\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned
\pset pager off
BEGIN READ ONLY;
SET LOCAL statement_timeout='15s';
SET LOCAL lock_timeout='2s';
SELECT 'DB_R31_CATALOG_BEGIN|'||current_database();
SELECT 'SCHEMA|'||n.nspname||'|'||c.relname||'|'||c.relkind::text||'|RLS='||c.relrowsecurity::text
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='sbi' AND
(c.relname IN ('import_batches','invoice_source_rows','payment_source_rows','invoices','payments','branch_master')
 OR c.relname ~* '(allocat|reconcil|branch.*master|payment.*summary|invoice.*summary|receipt|credit.*note)')
AND c.relkind IN ('r','p','v','m')
ORDER BY c.relname;
SELECT 'COLUMN|'||t.table_name||'|'||t.ordinal_position::text||'|'||t.column_name||'|'||t.udt_name||'|NULLABLE='||t.is_nullable||'|DEFAULT='||
CASE WHEN t.column_default IS NULL THEN 'NONE' ELSE 'YES' END
FROM information_schema.columns t
WHERE t.table_schema='sbi' AND t.table_name IN
('import_batches','invoice_source_rows','payment_source_rows','invoices','payments','branch_master')
ORDER BY t.table_name,t.ordinal_position;
SELECT 'CONSTRAINT|'||c.conrelid::regclass::text||'|'||c.conname||'|'||pg_get_constraintdef(c.oid)
FROM pg_constraint c
WHERE c.conrelid IN (
 SELECT rel.oid FROM pg_class rel JOIN pg_namespace n ON n.oid=rel.relnamespace
 WHERE n.nspname='sbi' AND rel.relname IN
 ('import_batches','invoice_source_rows','payment_source_rows','invoices','payments','branch_master')
) AND c.contype IN ('p','f','u','c')
ORDER BY c.conrelid::regclass::text,c.conname;
SELECT 'INDEX|'||t.relname||'|'||idx.relname||'|UNIQUE='||i.indisunique::text||'|DEFINITION='||pg_get_indexdef(i.indexrelid)
FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
JOIN pg_class idx ON idx.oid=i.indexrelid
JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='sbi' AND t.relname IN ('import_batches','payment_source_rows','payments','branch_master')
ORDER BY t.relname,idx.relname;
SELECT 'ROLE|'||r.rolname||'|LOGIN='||r.rolcanlogin::text||'|SUPERUSER='||r.rolsuper::text
FROM pg_roles r WHERE r.rolname ~* '(sbi.*(report|read|ingest|engine)|pr129)'
ORDER BY r.rolname;
SELECT 'REPORT_ROLE|'||rel.relname||'|SELECT='||
CASE WHEN to_regrole('sbi_pr129_report_login') IS NULL THEN 'ROLE_MISSING'
 ELSE has_table_privilege('sbi_pr129_report_login',rel.oid,'SELECT')::text END||
'|INSERT='||CASE WHEN to_regrole('sbi_pr129_report_login') IS NULL THEN 'ROLE_MISSING'
 ELSE has_table_privilege('sbi_pr129_report_login',rel.oid,'INSERT')::text END||
'|UPDATE='||CASE WHEN to_regrole('sbi_pr129_report_login') IS NULL THEN 'ROLE_MISSING'
 ELSE has_table_privilege('sbi_pr129_report_login',rel.oid,'UPDATE')::text END||
'|DELETE='||CASE WHEN to_regrole('sbi_pr129_report_login') IS NULL THEN 'ROLE_MISSING'
 ELSE has_table_privilege('sbi_pr129_report_login',rel.oid,'DELETE')::text END
FROM pg_class rel JOIN pg_namespace n ON n.oid=rel.relnamespace
WHERE n.nspname='sbi' AND rel.relname IN ('import_batches','payment_source_rows','payments','invoices')
AND rel.relkind IN ('r','p') ORDER BY rel.relname;
SELECT 'OWNER_FIELD|'||t.table_name||'|owner_uid='||
CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns c WHERE c.table_schema='sbi' AND c.table_name=t.table_name AND c.column_name='owner_uid') THEN 'PRESENT' ELSE 'MISSING' END||
'|tenant_id='||CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns c WHERE c.table_schema='sbi' AND c.table_name=t.table_name AND c.column_name='tenant_id') THEN 'PRESENT' ELSE 'MISSING' END
FROM (VALUES ('import_batches'),('payment_source_rows'),('payments')) AS t(table_name);
SELECT 'GLOBAL_FILE_SHA_UNIQUE|'||CASE WHEN EXISTS(
 SELECT 1 FROM pg_constraint c
 WHERE c.conrelid=to_regclass('sbi.import_batches') AND c.contype='u'
 AND pg_get_constraintdef(c.oid) LIKE 'UNIQUE (source_system, source_kind, source_sha256)%'
) THEN 'PRESENT_REVIEW_REQUIRED_FOR_MULTITENANT'
ELSE 'NOT_OBSERVED_IN_CONSTRAINTS_CHECK_INDEXES' END;
SELECT 'DB_R31_CATALOG_END|READ_ONLY';
COMMIT;
