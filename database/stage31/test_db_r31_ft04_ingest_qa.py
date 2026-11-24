"""DB-R31.3 source, owner, replay and QA-write contract tests: synthetic only.

Tests use fake PostgreSQL cursors, not live database or finance data.
"""
import hashlib
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db_r31_ft04_ingest_qa import (
    QA_DB, QA_ROLE, PARSER_VERSION, SOURCE_FIELDS, IngestReviewRequired,
    STATUS_PASS, STATUS_BAD, STATUS_DUP, STATUS_MASTER,
    build_receipt_plan, canonical_sol, write_qa_source_receipt,
)

SHA = "b" * 64
RECEIPT = "a" * 32
OWNER = "synthetic-firebase-uid"


def entry(desc, sol, credit):
    return {"Description": desc, "SOL ID": sol, "Credit Amount": credit}


def fixture():
    # Four original parser-accepted source rows and one invalid amount:
    # 100 + 20 + 10 + 10 = 140 rupees. 100 pending, 20 SOL hold,
    # 10/10 same-file candidate pair both held. Row 4 excluded.
    return [
        (2,entry("BANK POSTAGE AUG-26","001505","100.00"),None),
        (3,entry("BANK POSTAGE SEP-26","99922","20.00"),None),
        (4,entry("INVALID CREDIT","001505","-1.00"),"INVALID_CREDIT_AMOUNT"),
        (5,entry("REPEATED CANDIDATE","001505","10.00"),None),
        (6,entry("REPEATED CANDIDATE","001505","10.00"),None),
    ]


def parser(payload):
    return {"source_rows":5, "valid_rows":4, "review_rows":1,
            "valid_credit_total":"140.00"}


def extract(payload):
    return deepcopy(fixture())


def classify(payload, original_parser):
    items=fixture()
    good=[(n,d,int(d["Credit Amount"].replace(".","")))
          for n,d,reason in items if reason is None]
    bad=[{"source_row":n,"reason":reason}
         for n,d,reason in items if reason]
    return good,bad


def plan(**changes):
    config=dict(
        owner_uid=OWNER,receipt_id=RECEIPT,
        source_sheet_name="PAYMENT EVIDENCE",
        approved_sol_by_key={"1505":"SOUTHERN AVENUE"},
        master_sha256=SHA,filename="approved_payment.xlsx",
    )
    config.update(changes)
    return build_receipt_plan(b"synthetic-XLSX-injected-parser",parser,extract,
                              classify,**config)


class FakeCursor:
    def __init__(self, db=QA_DB, role=QA_ROLE, grants=None,
                 existing=None, replay=None, duplicate=False):
        self.db=db
        self.role=role
        self.grants=grants if grants is not None else (
            True,True,True,True,False,False)
        self.existing=existing if existing is not None else []
        self.replay=replay
        self.duplicate=duplicate
        self.calls=[]
        self._last=[]
        self.insert_statuses=[]
        self.insert_paise=[]
        self.insert_original=[]
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def execute(self, sql, values=None):
        sql=" ".join(sql.split())
        self.calls.append((sql,values))
        if sql.startswith("SELECT current_database()"):
            self._last=[(self.db,self.role)]
        elif "has_table_privilege" in sql:
            self._last=[self.grants]
        elif "SELECT id, owner_uid, source_receipt_id" in sql:
            self._last=self.existing
        elif "SELECT r.source_row_number" in sql:
            self._last=self.replay or []
        elif "SELECT 1 FROM sbi.payments p" in sql:
            self._last=[(1,)] if self.duplicate and values[-1]==10000 else []
        elif "INSERT INTO sbi.payment_source_status_v1" in sql:
            self.insert_statuses.append((values[1],json.loads(values[2]),
                                         values[4],values[5]))
            self._last=[]
        elif "INSERT INTO sbi.payments" in sql:
            self.insert_paise.append(values[-1])
            self._last=[]
        elif "INSERT INTO sbi.payment_source_rows" in sql:
            self.insert_original.append(json.loads(values[3]))
            self._last=[]
        else:
            self._last=[]
    def fetchone(self):
        return self._last[0] if self._last else None
    def fetchall(self):
        return self._last


class FakeConnection:
    def __init__(self, **kwargs):
        self.fake=FakeCursor(**kwargs)
        self.committed=False
        self.rolled_back=False
    def __enter__(self):return self
    def __exit__(self,typ,*_):
        self.rolled_back=typ is not None
        self.committed=typ is None
        return False
    def cursor(self):return self.fake


class R31FT04IngestContract(unittest.TestCase):
    def denied(self,code,callback,*args,**kw):
        with self.assertRaisesRegex(IngestReviewRequired,code):
            callback(*args,**kw)

    def test_01_source_row_count_and_credit_parity(self):
        p=plan()
        self.assertEqual(len(p.rows),5)
        self.assertEqual(p.accepted_credit_paise,14000)
        self.assertEqual(p.parser_version,PARSER_VERSION)

    def test_02_failed_source_row_retained_in_plan_not_payment(self):
        row=plan().rows[2]
        self.assertEqual(row.excel_row,4)
        self.assertEqual(row.status,STATUS_BAD)
        self.assertIsNone(row.credit_paise)
        self.assertIn("INVALID_CREDIT_AMOUNT",row.reasons)

    def test_03_leading_zero_sol_preserved_and_only_canonical_lookup(self):
        row=plan().rows[0]
        self.assertEqual(row.raw_sol,"001505")
        self.assertEqual(row.canonical_sol,"1505")
        self.assertEqual(row.official_branch_name,"SOUTHERN AVENUE")
        self.assertEqual(row.status,STATUS_PASS)

    def test_04_unknown_sol_hold_not_invented(self):
        row=plan().rows[1]
        self.assertEqual(row.raw_sol,"99922")
        self.assertEqual(row.status,STATUS_MASTER)
        self.assertIsNone(row.official_branch_name)

    def test_05_same_file_candidate_duplicate_holds_both(self):
        p=plan()
        self.assertEqual([p.rows[3].status,p.rows[4].status],
                         [STATUS_DUP,STATUS_DUP])

    def test_06_no_master_holds_valid_source_rows(self):
        p=plan(approved_sol_by_key={},master_sha256=None)
        self.assertEqual([r.status for r in p.rows],
                         [STATUS_MASTER,STATUS_MASTER,STATUS_BAD,
                          STATUS_MASTER,STATUS_MASTER])

    def test_07_master_mapping_requires_sha(self):
        self.denied("APPROVED_SOL_MASTER_SHA_REQUIRED",plan,master_sha256=None)

    def test_08_bad_master_map_rejected(self):
        self.denied("APPROVED_SOL_LOOKUP_INVALID",plan,
                    approved_sol_by_key={"001505":"WRONG KEY"})

    def test_09_untrusted_owner_missing_refused(self):
        self.denied("TRUSTED_OWNER_UID_REQUIRED",plan,owner_uid="")

    def test_10_bad_receipt_id_refused(self):
        self.denied("IMMUTABLE_RECEIPT_ID_REQUIRED",plan,receipt_id="not-uuid")

    def test_11_source_workbook_sheet_required(self):
        self.denied("VERIFIED_SOURCE_SHEET_REQUIRED",plan,
                    source_sheet_name="")

    def test_12_filename_path_refused(self):
        self.denied("SOURCE_FILENAME_INVALID",plan,
                    filename="../../bank.xlsx")

    def test_13_no_fictitious_bank_date_or_utr_fields(self):
        p=plan()
        for r in p.rows:
            fields=json.loads(r.original_json)
            self.assertEqual(set(fields),set(SOURCE_FIELDS))
            self.assertNotIn("UTR",fields)
            self.assertNotIn("bank_posting_date",fields)

    def test_14_row_sha_matches_preserved_original_text(self):
        r=plan().rows[0]
        self.assertEqual(r.row_sha256,
                         hashlib.sha256(r.original_json.encode()).hexdigest())
        self.assertEqual(json.loads(r.original_json)["SOL ID"],"001505")

    def test_15_mixed_valid_invalid_source_inserts_individually(self):
        conn=FakeConnection()
        result=write_qa_source_receipt(conn,plan())
        self.assertTrue(conn.committed)
        self.assertEqual(result["status"],"QA_SOURCE_ROWS_COMMITTED")
        self.assertEqual(len(conn.fake.insert_original),5)
        self.assertEqual(len(conn.fake.insert_paise),4)
        self.assertEqual(sum(conn.fake.insert_paise),14000)
        self.assertEqual(len(conn.fake.insert_statuses),5)
        self.assertEqual({x[0] for x in conn.fake.insert_statuses},
                         {STATUS_PASS,STATUS_MASTER,STATUS_BAD,STATUS_DUP})
        self.assertEqual(result["financial_allocations"],0)

    def test_16_stored_source_credit_no_fake_settlement(self):
        conn=FakeConnection()
        write_qa_source_receipt(conn,plan())
        sql="\n".join(c for c,_ in conn.fake.calls)
        self.assertNotIn("INSERT INTO sbi.allocations",sql)
        self.assertNotIn("UPDATE sbi.payments",sql)
        self.assertNotIn("DELETE FROM",sql)
        self.assertNotIn("UPDATE sbi.invoices",sql)

    def test_17_database_identity_mismatch_fails_closed(self):
        conn=FakeConnection(db="sbi_reconciliation_main")
        self.denied("QA_ONLY_DATABASE_AND_ROLE_REQUIRED",
                    write_qa_source_receipt,conn,plan())
        self.assertTrue(conn.rolled_back)
        self.assertEqual(len(conn.fake.insert_original),0)

    def test_18_wrong_role_refused(self):
        conn=FakeConnection(role="sbi_pr129_report_login")
        self.denied("QA_ONLY_DATABASE_AND_ROLE_REQUIRED",
                    write_qa_source_receipt,conn,plan())

    def test_19_missing_status_table_insert_grant_refused(self):
        conn=FakeConnection(grants=(True,True,True,False,False,False))
        self.denied("QA_INSERT_ONLY_STATUS_ROLE_NOT_READY",
                    write_qa_source_receipt,conn,plan())
        self.assertEqual(len(conn.fake.insert_original),0)

    def test_20_existing_payment_update_grant_is_unsafe(self):
        conn=FakeConnection(grants=(True,True,True,True,True,False))
        self.denied("QA_INSERT_ONLY_STATUS_ROLE_NOT_READY",
                    write_qa_source_receipt,conn,plan())

    def test_21_global_sha_owned_by_other_user_requires_review(self):
        conn=FakeConnection(existing=[("qa-batch","some-other-user",RECEIPT)])
        self.denied("GLOBAL_SHA_CROSS_OWNER_REVIEW_REQUIRED",
                    write_qa_source_receipt,conn,plan())
        self.assertTrue(conn.rolled_back)
        self.assertEqual(len(conn.fake.insert_paise),0)

    def test_22_same_sha_other_receipt_cannot_be_silently_merged(self):
        conn=FakeConnection(existing=[("qa-batch",OWNER,"c"*32)])
        self.denied("SAME_FILE_DIFFERENT_RECEIPT_REVIEW_REQUIRED",
                    write_qa_source_receipt,conn,plan())

    def test_23_replay_exact_source_and_status_is_idempotent(self):
        p=plan()
        prior=[(r.excel_row,r.row_sha256,r.credit_paise,r.status)
               for r in p.rows]
        conn=FakeConnection(existing=[("qa-batch",OWNER,RECEIPT)],
                            replay=prior)
        result=write_qa_source_receipt(conn,p)
        self.assertEqual(result["status"],"QA_ALREADY_RECORDED")
        self.assertEqual(len(conn.fake.insert_original),0)
        self.assertTrue(conn.committed)

    def test_24_replay_conflicting_status_fails_without_updates(self):
        p=plan()
        prior=[(r.excel_row,r.row_sha256,r.credit_paise,r.status)
               for r in p.rows]
        prior[0]=(prior[0][0],prior[0][1],prior[0][2],STATUS_MASTER)
        conn=FakeConnection(existing=[("qa-batch",OWNER,RECEIPT)],
                            replay=prior)
        self.denied("PREVIOUS_SOURCE_RECEIPT_DIFFERS",
                    write_qa_source_receipt,conn,p)
        self.assertTrue(conn.rolled_back)

    def test_25_cross_receipt_candidate_does_not_block_other_rows(self):
        conn=FakeConnection(duplicate=True)
        result=write_qa_source_receipt(conn,plan())
        self.assertEqual(result["source_rows"],5)
        statuses=conn.fake.insert_statuses
        self.assertIn((STATUS_DUP,["CROSS_RECEIPT_DUPLICATE_CANDIDATE"],
                       "1505","SOUTHERN AVENUE"),statuses)
        self.assertEqual(len(conn.fake.insert_paise),4)

    def test_26_persisted_status_owner_is_not_repeated_mutably(self):
        conn=FakeConnection()
        write_qa_source_receipt(conn,plan())
        status_sql=next(sql for sql,_ in conn.fake.calls
                        if "INSERT INTO sbi.payment_source_status_v1" in sql)
        self.assertNotIn("owner_uid",status_sql)

    def test_27_duplicate_injected_source_row_refused(self):
        def badextract(payload):
            rows=fixture()
            rows[4]=(5,rows[4][1],None)
            return rows
        self.denied("FT04_SOURCE_ROW_COVERAGE_FAILED",
                    build_receipt_plan,
                    b"file",parser,badextract,classify,
                    owner_uid=OWNER,receipt_id=RECEIPT,
                    source_sheet_name="PAYMENT EVIDENCE",
                    approved_sol_by_key={},master_sha256=None)

    def test_28_bad_accepted_amount_detected(self):
        def badclassify(payload,orig):
            yes,no=classify(payload,orig)
            yes[0]=(yes[0][0],yes[0][1],999)
            return yes,no
        self.denied("FT04_ACCEPTED_CREDIT_PARITY_FAILED",
                    build_receipt_plan,
                    b"file",parser,extract,badclassify,
                    owner_uid=OWNER,receipt_id=RECEIPT,
                    source_sheet_name="PAYMENT EVIDENCE",
                    approved_sol_by_key={},master_sha256=None)

    def test_29_duplicate_review_does_not_delete_valid_row(self):
        conn=FakeConnection(duplicate=True)
        write_qa_source_receipt(conn,plan())
        self.assertEqual(len(conn.fake.insert_original),5)
        self.assertEqual(len(conn.fake.insert_paise),4)

    def test_30_source_parser_success_not_evidence_of_reconciliation(self):
        result=write_qa_source_receipt(FakeConnection(),plan())
        self.assertFalse(result["production_writes"])
        self.assertEqual(result["financial_allocations"],0)


if __name__=="__main__":
    unittest.main()
