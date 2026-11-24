"""Offline source-only R31 adapter regression: no PostgreSQL connections."""
from dataclasses import replace
import unittest
from types import SimpleNamespace
from db_r31_owner_source_adapter import (
    SourceContractError, SourcePlan, build_plan, authenticated_owner,
    canonical_sol, exact_paise, assert_owner_scoped_qa,
)

RAW=b'PK synthetic approved workbook bytes (unit only)'
ONE={"Description":"POSTAGE NOV 2026","SOL ID":"001505","Credit Amount":"118.00"}
BAD={"Description":"POSTAGE INVALID","SOL ID":"001505","Credit Amount":"0"}
SECOND={"Description":"POSTAGE NOV 2026","SOL ID":"001505","Credit Amount":"118.00"}


def plan(rows=None, elig=None, review=None, master=None, owner="approved-owner"):
    if rows is None:
        rows=[(2,ONE,None),(3,BAD,"INVALID_CREDIT_AMOUNT")]
    if elig is None:
        elig=[(2,ONE,11800)]
    if review is None:
        review=[{"source_row":3,"reason":"INVALID_CREDIT_AMOUNT"}]
    return build_plan(
        trusted_owner=owner,
        trusted_receipt_id="a"*32,
        original_file_name="bank-payment.xlsx",
        source_sheet_name="PAYMENT EVIDENCE",
        raw_file=RAW,
        all_source_rows=rows,
        parser_eligible_rows=elig,
        parser_review_rows=review,
        approved_master_lookup=master
    )


class FakeCursor:
    def __init__(self,rows):
        self.rows=list(rows)
        self.queries=[]
    def execute(self,sql,params=None):
        self.queries.append((sql,params))
    def fetchone(self):
        return self.rows.pop(0)


class OwnerSourceAdapterTests(unittest.TestCase):
    def test_authenticated_server_owner_only(self):
        self.assertEqual(authenticated_owner(SimpleNamespace(uid="uid-approved")),"uid-approved")
        for uid in ("",None,0,[], "x"*201):
            with self.assertRaises(SourceContractError):
                authenticated_owner(SimpleNamespace(uid=uid))

    def test_sol_text_and_credit_exact_paise(self):
        self.assertEqual(canonical_sol("001505"),"1505")
        self.assertEqual(canonical_sol("1"),"1")
        self.assertIsNone(canonical_sol("001x"))
        self.assertIsNone(canonical_sol("000000"))
        self.assertEqual(exact_paise("118.00"),11800)
        for amt in ("0","-1","1.234","NaN","1e2","", " 3.00"):
            with self.subTest(amt=amt):
                with self.assertRaises(SourceContractError):
                    exact_paise(amt)

    def test_all_source_rows_preserved_invalid_has_no_payment(self):
        p=plan()
        self.assertEqual(p.owner_uid,"approved-owner")
        self.assertEqual([r.number for r in p.rows],[2,3])
        self.assertEqual([r.amount_paise for r in p.rows],[11800,None])
        self.assertEqual([r.status for r in p.rows],["HOLD_SOL_MASTER","EXCLUDED_INVALID_SOURCE"])
        self.assertEqual(p.rows[0].original["SOL ID"],"001505")
        self.assertEqual(p.rows[1].original["Credit Amount"],"0")

    def test_approved_master_snapshot_pending_not_matched(self):
        p=plan(master=lambda sol:("SOUTHERN AVENUE", "a"*64) if sol=="1505" else None)
        self.assertEqual(p.rows[0].official_branch_name,"SOUTHERN AVENUE")
        self.assertEqual(p.rows[0].status,"PENDING_RECONCILIATION")
        self.assertEqual(p.rows[0].sol_master_sha256,"a"*64)
        self.assertEqual(p.rows[1].status,"EXCLUDED_INVALID_SOURCE")

    def test_invalid_master_response_fails_closed(self):
        with self.assertRaisesRegex(SourceContractError,"APPROVED_MASTER_RESPONSE_UNVERIFIED"):
            plan(master=lambda _:("UNVERIFIED", "not-the-real-hash"))

    def test_identical_narration_sol_and_amount_held_individually(self):
        p=plan(rows=[(2,ONE,None),(3,SECOND,None)],
               elig=[(2,ONE,11800),(3,SECOND,11800)],review=[],
               master=lambda _:("SOUTHERN AVENUE","a"*64))
        self.assertEqual([r.status for r in p.rows],
                         ["HOLD_DUPLICATE_CANDIDATE"]*2)
        self.assertEqual(sum(r.amount_paise for r in p.rows),23600)

    def test_parser_partition_must_cover_all_source_rows(self):
        with self.assertRaisesRegex(SourceContractError,"PARSER_ROW_PARTITION_INCOMPLETE"):
            plan(review=[])
        with self.assertRaisesRegex(SourceContractError,"PARSER_REVIEW_ROW_MISMATCH"):
            plan(review=[{"source_row":2,"reason":"INVALID"}])
        changed=dict(ONE, Description="ALTERED SOURCE ROW")
        with self.assertRaisesRegex(SourceContractError,"PARSER_ELIGIBLE_ROW_MISMATCH"):
            plan(elig=[(2,changed,11800)])
        with self.assertRaisesRegex(SourceContractError,"PARSER_FINANCIAL_TOTAL_MISMATCH"):
            plan(elig=[(2,ONE,11801)])

    def test_bad_receipt_identity_rejected(self):
        with self.assertRaises(SourceContractError):
            build_plan(trusted_owner="owner",trusted_receipt_id="../bad",
                original_file_name="source.xlsx",source_sheet_name="PAYMENT EVIDENCE",
                raw_file=RAW,all_source_rows=[(2,ONE,None)],
                parser_eligible_rows=[(2,ONE,11800)],parser_review_rows=[])

    def test_null_master_does_not_guess_name(self):
        p=plan(master=None)
        self.assertIsNone(p.rows[0].official_branch_name)
        self.assertIsNone(p.rows[0].sol_master_sha256)

    def test_old_global_sha_schema_rejected_even_with_correct_role(self):
        fake=FakeCursor([
            ("sbi_r31_owner_qa_20261125","sbi_r31_ownerqa_ingest",
                True,True,True,True,False,False),
            (0,0,1)
        ])
        with self.assertRaisesRegex(RuntimeError,"R31_OWNER_SCOPE_QA_SCHEMA_NOT_APPROVED"):
            assert_owner_scoped_qa(fake)
        self.assertEqual(len(fake.queries),2)

    def test_production_or_wrong_role_rejected_before_schema_query(self):
        for identity in (
            ("sbi_reconciliation_main","sbi_r31_ownerqa_ingest",
                True,True,True,True,False,False),
            ("sbi_r31_owner_qa_20261125","sbi_pr129_report_login",
                False,False,False,False,False,False)
        ):
            fake=FakeCursor([identity])
            with self.assertRaisesRegex(RuntimeError,"R31_QA_DB_ROLE_MISMATCH"):
                assert_owner_scoped_qa(fake)
            self.assertEqual(len(fake.queries),1)

if __name__=="__main__":
    unittest.main(verbosity=2)
