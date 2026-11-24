"""Offline R31 read-only report query tests; no real DB or Firebase session."""
import csv
import io
import unittest
from types import SimpleNamespace
from db_r31_owner_report_adapter import (
    sol_summary, payment_details, payment_details_csv, QA_DB, QA_REPORT_ROLE,
)


class Cursor:
    def __init__(self, identity=None):
        self.identity = identity or (QA_DB, QA_REPORT_ROLE, False, False, False)
        self.calls=[]
        self.description=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,query,args=None):
        self.calls.append((query,args))
        if "current_database()" in query:
            self.response=[self.identity]
        elif "FROM sbi.payment_received_source_v1" in query:
            if "reason_codes::text" in query:
                self.description=[("description",),("raw_sol",),("source_row_number",)]
                self.response=[("=cmd",'001505',2)]
            else:
                self.description=[("raw_sol",),("received_credit_paise",),("reconciliation_status",)]
                self.response=[("001505",11800,"NOT_CALCULATED")]
        else:
            self.response=[]
    def fetchone(self): return self.response.pop(0)
    def fetchall(self): return list(self.response)


class Connection:
    def __init__(self, identity=None):
        self.cur=Cursor(identity)
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur


class ReportingTests(unittest.TestCase):
    def test_sol_tally_owner_filter_and_no_match(self):
        conn=Connection()
        rows=sol_summary(conn,SimpleNamespace(uid="authorized-owner"),limit=20,offset=0)
        self.assertEqual(rows,[{
            'raw_sol':'001505','received_credit_paise':11800,
            'reconciliation_status':'NOT_CALCULATED'}])
        q=[x for x in conn.cur.calls if 'FROM sbi.payment_received_source_v1' in x[0]]
        self.assertEqual(len(q),1)
        self.assertEqual(q[0][1],('authorized-owner',20,0))
        self.assertIn("WHERE owner_uid = %s",q[0][0])

    def test_report_role_has_no_write_grants(self):
        conn=Connection((QA_DB,QA_REPORT_ROLE,False,True,False))
        with self.assertRaisesRegex(RuntimeError,"R31_QA_REPORT_ROLE_MISMATCH"):
            sol_summary(conn,SimpleNamespace(uid="approved"))
        self.assertFalse(any('FROM sbi.payment_received_source_v1' in x[0] for x in conn.cur.calls))

    def test_owner_required(self):
        with self.assertRaises(ValueError):
            payment_details(Connection(),SimpleNamespace(uid=""))

    def test_report_csv_escapes_formula(self):
        conn=Connection()
        raw=payment_details_csv(conn,SimpleNamespace(uid="authorized-owner"))
        rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        self.assertIn('description', rows[0])
        idx=rows[0].index('description')
        self.assertEqual(rows[1][idx],"'=cmd")

    def test_report_is_read_only_transaction(self):
        conn=Connection()
        payment_details(conn,SimpleNamespace(uid="authorized-owner"))
        self.assertIn("SET TRANSACTION READ ONLY",conn.cur.calls[0][0])

if __name__=="__main__":
    unittest.main(verbosity=2)
