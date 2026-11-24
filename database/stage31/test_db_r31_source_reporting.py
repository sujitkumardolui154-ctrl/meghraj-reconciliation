"""Offline DB-R31 source report and QA-only migration regression."""
import csv
import io
import unittest
from pathlib import Path
from db_r31_source_report_contract import (
    SOL_SUMMARY_SQL, PAYMENT_DETAILS_SQL, SOL_CSV_FIELDS, DETAIL_CSV_FIELDS,
    query_args, csv_safe, csv_export,
)

ROOT = Path(__file__).parent

class R31ReportingContractTests(unittest.TestCase):
    def test_owner_filter_is_server_parameter(self):
        for query in (SOL_SUMMARY_SQL,PAYMENT_DETAILS_SQL):
            self.assertIn('WHERE owner_uid = %s',query)
            self.assertIn('LIMIT %s OFFSET %s',query)
    def test_no_engine_false_positive(self):
        for query in (SOL_SUMMARY_SQL,PAYMENT_DETAILS_SQL):
            self.assertIn('NOT_CALCULATED',query)
            self.assertNotIn('JOIN sbi.allocations',query)
        self.assertIn('NULL::bigint AS verified_matched_payment_rows',SOL_SUMMARY_SQL)
        self.assertIn('NULL::bigint AS verified_allocated_paise',SOL_SUMMARY_SQL)
    def test_source_count_has_no_join_multiplier(self):
        self.assertIn('FROM sbi.payment_received_source_v1',SOL_SUMMARY_SQL)
        self.assertIn('count(payment_id)',SOL_SUMMARY_SQL)
        self.assertNotIn('JOIN sbi.payment_allocations',SOL_SUMMARY_SQL)
    def test_owner_and_pagination_rejected_without_identity(self):
        self.assertEqual(query_args('owner-1',50,2),('owner-1',50,2))
        for uid,limit,offset in (('',10,0),('owner',0,0),('owner',10,-1),
                                 ('owner',1001,0),('owner',100,10**9)):
            with self.assertRaises(ValueError):
                query_args(uid,limit,offset)
    def test_csv_formula_injection(self):
        for value in ('=SUM(1,2)','+1+2','-3+9','@SUM(A1)','  =SUM(1,2)','\t=cmd','\n+ABC'):
            self.assertTrue(csv_safe(value).startswith("'"),value)
        self.assertEqual(csv_safe('PENDING_RECONCILIATION'),'PENDING_RECONCILIATION')
        self.assertEqual(csv_safe(None),'')
    def test_report_detail_csv_headers_and_formula_protection(self):
        row={key:'' for key in DETAIL_CSV_FIELDS}
        row.update(description='=HYPERLINK("http://invalid.test")',
                   raw_sol='001505',source_row_number=2,
                   credit_paise=11800,source_status='PENDING_RECONCILIATION')
        raw=csv_export([row],DETAIL_CSV_FIELDS).decode('utf-8-sig')
        rows=list(csv.reader(io.StringIO(raw)))
        self.assertEqual(tuple(rows[0]),DETAIL_CSV_FIELDS)
        self.assertEqual(rows[1][4][0],"'")
        self.assertEqual(rows[1][5],'001505')
        self.assertEqual(rows[1][7],'11800')
        with self.assertRaises(ValueError):
            csv_export([row],['unapproved_field'])
    def test_schema_migration_is_qa_only(self):
        up=(ROOT/'db_r31_additive_qa_up.sql').read_text()
        down=(ROOT/'db_r31_additive_qa_down.sql').read_text()
        for sql in (up,down):
            self.assertIn("current_database() <> 'sbi_ft04g_clean_0e858f93'",sql)
            self.assertIn('DB_R31_QA_ONLY_WRONG_DATABASE',sql)
            self.assertNotIn('DROP CONSTRAINT',sql)
            self.assertNotIn('GRANT INSERT',sql)
        self.assertIn('source_row_id uuid PRIMARY KEY',up)
        self.assertIn('EXCLUDED_INVALID_SOURCE',up)
        self.assertIn('ON DELETE RESTRICT',up)
        self.assertIn('DB_R31_ROLLBACK_BLOCKED_STATUS_EVIDENCE_PRESENT',down)

if __name__=='__main__':
    unittest.main(verbosity=2)
