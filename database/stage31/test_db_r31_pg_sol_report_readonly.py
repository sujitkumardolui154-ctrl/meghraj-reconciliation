"""R31.4: read-only owner/role and canonical SOL reporting (synthetic)."""
import io
import csv
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).parent))
from db_r31_pg_sol_report_readonly import (
    DB_PRODUCTION,DB_QA,ROLE_PRODUCTION,ROLE_QA,
    ReportAccessRefused,SOL_WISE_SUMMARY_SQL,PAYMENT_ROW_DETAILS_SQL,
    SUMMARY_FIELDS,DETAIL_FIELDS,sol_summary,payment_details,safe_csv,
)


class Col:
    def __init__(self,name): self.name=name


class Cursor:
    def __init__(self,identity=(DB_QA,ROLE_QA),fields=SUMMARY_FIELDS,rows=()):
        self.identity=identity
        self.fields=fields
        self.rows=rows
        self.commands=[]
        self.description=None
        self.latest=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,params=None):
        self.commands.append((sql,params))
        if "SELECT current_database()" in sql:
            self.latest=[self.identity]
        elif "FROM sbi.payment_received_source_v1" in sql:
            self.description=[Col(x) for x in self.fields]
            self.latest=self.rows
        else:
            self.latest=[]
    def fetchone(self):return self.latest[0]
    def fetchall(self):return list(self.latest)


class Db:
    def __init__(self,**kwargs):
        self.cur=Cursor(**kwargs)
    def transaction(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur


def row(**updates):
    base={"sol_id":"1505","branch_name":"SYNTHETIC APPROVED OFFICE",
          "payment_rows":3,"valid_payment_rows":2,"credit_paise":13000,
          "excluded":1,"held_for_review":1,"not_calculated":2,
          "available_for_future_matching":1,"legacy_unclassified":0,
          "matched":None,"verified_allocated_paise":None}
    base.update(updates)
    return tuple(base[x] for x in SUMMARY_FIELDS)


class SourceOnlySOLReport(unittest.TestCase):
    def test_01_one_normalized_sol_not_one_group_per_raw_sol(self):
        self.assertIn("COALESCE(NULLIF(canonical_sol,'')",SOL_WISE_SUMMARY_SQL)
        self.assertIn("ltrim(raw_sol,'0')",SOL_WISE_SUMMARY_SQL)
        self.assertIn("GROUP BY sol_id",SOL_WISE_SUMMARY_SQL)

    def test_02_unverified_branch_group_not_guessed(self):
        self.assertIn("PENDING_SOL_MASTER_REVIEW",SOL_WISE_SUMMARY_SQL)
        self.assertIn("count(DISTINCT sol_master_sha256)=1",SOL_WISE_SUMMARY_SQL)
        self.assertIn("official_branch_name IS NULL",SOL_WISE_SUMMARY_SQL)

    def test_03_no_allocations_or_false_matched_status(self):
        self.assertIn("NULL::bigint AS matched",SOL_WISE_SUMMARY_SQL)
        self.assertIn("NULL::bigint AS verified_allocated_paise",
                      SOL_WISE_SUMMARY_SQL)
        self.assertNotIn("sbi.allocations",SOL_WISE_SUMMARY_SQL)
        self.assertNotIn("sbi.payment_allocations",SOL_WISE_SUMMARY_SQL)

    def test_04_owner_filter_parameterized_for_both_queries(self):
        for sql in (SOL_WISE_SUMMARY_SQL,PAYMENT_ROW_DETAILS_SQL):
            self.assertIn("WHERE owner_uid = %s",sql)
            self.assertIn("LIMIT %s OFFSET %s",sql)
            self.assertNotIn("{owner_uid}",sql)

    def test_05_qa_read_role_works_only_under_read_only_tx(self):
        db=Db(rows=[row()])
        data=sol_summary(db,trusted_owner_uid="synthetic-owner")
        self.assertEqual(data["page_totals"]["payment_rows"],3)
        self.assertEqual(data["page_totals"]["not_calculated"],2)
        self.assertEqual(data["page_totals"]["excluded"],1)
        self.assertIsNone(data["page_totals"]["matched"])
        self.assertFalse(data["financial_writes"])
        cmds=db.cur.commands
        self.assertEqual(cmds[0][0],"SET TRANSACTION READ ONLY")
        self.assertEqual(cmds[-1][1],("synthetic-owner",100,0))
        self.assertIn("statement_timeout",cmds[1][0])

    def test_06_central_read_role_allowed_in_contract_not_verified_live(self):
        db=Db(identity=(DB_PRODUCTION,ROLE_PRODUCTION),rows=[row()])
        self.assertEqual(sol_summary(db,trusted_owner_uid="owner")["page_totals"]["payment_rows"],3)

    def test_07_wrong_database_role_denied(self):
        db=Db(identity=(DB_QA,"sbi_ft04q_ingest"),rows=[row()])
        with self.assertRaisesRegex(ReportAccessRefused,
                                    "REPORT_ONLY_DATABASE_ROLE_REQUIRED"):
            sol_summary(db,trusted_owner_uid="owner")
        self.assertFalse(any("SELECT " in x[0] and "FROM sbi." in x[0]
                             for x in db.cur.commands))

    def test_08_wrong_production_writer_denied(self):
        db=Db(identity=(DB_PRODUCTION,"sbi_engine_runtime"),rows=[row()])
        with self.assertRaises(ReportAccessRefused):
            sol_summary(db,trusted_owner_uid="owner")

    def test_09_cross_owner_report_uid_missing_refused(self):
        db=Db(rows=[row()])
        with self.assertRaises(ValueError):
            sol_summary(db,trusted_owner_uid="")

    def test_10_oversized_page_denied(self):
        with self.assertRaises(ValueError):
            sol_summary(Db(rows=[row()]),trusted_owner_uid="owner",
                        limit=5001)

    def test_11_unexpected_sql_result_schema_denied(self):
        db=Db(fields=("foo",),rows=[("bar",)])
        with self.assertRaisesRegex(ReportAccessRefused,
                                    "REPORT_UNEXPECTED_QUERY_SCHEMA"):
            sol_summary(db,trusted_owner_uid="owner")

    def test_12_safe_csv_injection_guards(self):
        record={f:"" for f in DETAIL_FIELDS}
        record["description"]="=HYPERLINK(\"https://invalid.example\")"
        record["raw_sol"]="001505"
        raw=safe_csv([record],detail=True).decode("utf-8-sig")
        rows=list(csv.reader(io.StringIO(raw)))
        self.assertEqual(tuple(rows[0]),DETAIL_FIELDS)
        self.assertTrue(rows[1][4].startswith("'="))
        self.assertEqual(rows[1][5],"001505")

    def test_13_csv_does_not_add_unapproved_source_fields(self):
        record={f:"" for f in SUMMARY_FIELDS}
        record["sol_id"]="1505"
        record["credit_paise"]=12300
        raw=safe_csv([record]).decode("utf-8-sig")
        vals=list(csv.reader(io.StringIO(raw)))
        self.assertEqual(tuple(vals[0]),SUMMARY_FIELDS)
        self.assertEqual(vals[1][0],"1505")
        self.assertEqual(vals[1][4],"12300")

    def test_14_details_are_source_only(self):
        db=Db(fields=DETAIL_FIELDS,rows=[tuple("x" for _ in DETAIL_FIELDS)])
        data=payment_details(db,trusted_owner_uid="owner",limit=20,offset=4)
        self.assertEqual(len(data["records"]),1)
        self.assertFalse(data["reconciliation_executed"])
        self.assertEqual(db.cur.commands[-1][1],("owner",20,4))

    def test_15_empty_page_not_global_count(self):
        data=sol_summary(Db(rows=[]),trusted_owner_uid="owner",limit=5,offset=10)
        self.assertEqual(data["page_totals"]["payment_rows"],0)
        self.assertEqual(data["limit"],5)
        self.assertEqual(data["offset"],10)
        self.assertNotIn("overall_totals",data)

    def test_16_no_financial_writes_in_report_queries(self):
        sql=SOL_WISE_SUMMARY_SQL+"\n"+PAYMENT_ROW_DETAILS_SQL
        for prohibited in ("INSERT INTO","UPDATE sbi.","DELETE FROM",
                           "TRUNCATE ","GRANT ","CREATE TABLE"):
            self.assertNotIn(prohibited,sql)


if __name__=="__main__":
    unittest.main()
