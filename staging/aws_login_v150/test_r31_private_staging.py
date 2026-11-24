"""R31 private Firebase staging routes — offline safety and INR output QA."""
from __future__ import annotations

import csv
from io import StringIO, BytesIO
from openpyxl import Workbook
from payment_evidence_upload import _parse
from r31_stage_blueprint import _extract_original_source
from r31_db_r31_owner_source_adapter import build_plan, exact_paise
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from tempfile import TemporaryDirectory

from flask import Flask

from r31_currency import (
    amount_rupees,amount_display,group_to_public,detail_to_public,public_csv,
)
from r31_stage_blueprint import (
    CREDENTIALS, StageBlocked, stage_r31, _credentials,
    _verified_private_receipt,
)


class R31CurrencyOutputTests(TestCase):
    def test_credit_amount_11800_paise_displays_118_rupees(self):
        self.assertEqual(amount_rupees(11800),"118.00")
        self.assertEqual(amount_display(11800),"₹118.00")
        self.assertEqual(amount_rupees(125050),"1250.50")
        self.assertEqual(amount_display(1),"₹0.01")

    def test_no_implicit_double_conversion(self):
        for wrong in ("11800",118.0,True,118.5):
            with self.assertRaises(ValueError):
                amount_rupees(wrong)

    def test_public_sol_json_has_rupees_not_raw_paise(self):
        row={
            "raw_sol":"001505","official_branch_name":"",
            "uploaded_source_rows":2,"valid_received_rows":1,
            "received_credit_paise":11800,
            "held_rows":1,"excluded_invalid_rows":1,
            "pending_reconciliation_rows":0,
            "legacy_unclassified_rows":0,
            "verified_matched_payment_rows":None,
            "verified_allocated_paise":None,
        }
        public=group_to_public(row)
        self.assertEqual(public["sol_id"],"001505")
        self.assertEqual(public["credit_received_rupees"],"118.00")
        self.assertEqual(public["credit_received_display"],"₹118.00")
        self.assertNotIn("received_credit_paise",public)
        self.assertIsNone(public["verified_allocated_rupees"])
        self.assertEqual(public["reconciliation_status"],"NOT_CALCULATED")

    def test_original_invalid_source_credit_not_invented(self):
        r={"raw_sol":"001505","credit_paise":None,
           "raw_credit_amount":"0","source_status":"EXCLUDED_INVALID_SOURCE"}
        p=detail_to_public(r)
        self.assertEqual(p["sol_id"],"001505")
        self.assertIsNone(p["credit_amount_rupees"])
        self.assertEqual(p["original_credit_amount"],"0")
        self.assertIsNone(p["verified_invoice_refs"])

    def test_sol_csv_rupees_numeric_and_leading_zeros(self):
        row={
            "sol_id":"001505",
            "official_branch_name":"SOUTHERN AVENUE",
            "uploaded_source_rows":2,
            "valid_received_rows":1,
            "credit_received_rupees":"118.00",
            "held_rows":1,"excluded_invalid_rows":1,
            "pending_reconciliation_rows":0,
            "reconciliation_status":"NOT_CALCULATED"
        }
        data=public_csv([row])
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        vals=list(csv.reader(StringIO(data.decode("utf-8-sig"))))
        amount=vals[1][vals[0].index("Credit Received (INR)")]
        self.assertEqual(amount,"118.00")
        self.assertNotEqual(amount,"11800")

    def test_csv_formula_narration_neutralized(self):
        row={
            "source_receipt_id":"abc","source_row_number":2,
            "description":"=HYPERLINK(\"https://example.invalid\")",
            "sol_id":"001505","original_credit_amount":"118.00",
            "credit_amount_rupees":"118.00",
            "official_branch_name":"", "source_status":"HOLD_SOL_MASTER",
            "reconciliation_status":"NOT_CALCULATED",
        }
        data=public_csv([row],detail=True)
        vals=list(csv.reader(StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(vals[1][2][0],"'")
        self.assertEqual(vals[1][5],"118.00")


class R31StagingSecurityTests(TestCase):
    def test_csrf_rejects_unauthenticated_post_before_any_db_write(self):
        app=Flask(__name__)
        app.register_blueprint(stage_r31)
        with app.test_client() as c:
            res=c.post("/api/r31-private-qa/receipts/"+("a"*32)+"/sync",
                       headers={"Origin":"https://sbi-preview.13-232-241-221.sslip.io"})
        self.assertEqual(res.status_code,403)
        self.assertFalse(res.json["production_financial_writes"])

    def test_report_missing_feature_flag_fails_closed(self):
        app=Flask(__name__)
        app.register_blueprint(stage_r31)
        with patch.dict(os.environ,{"SBI_R31_PRIVATE_STAGING_ENABLED":""}):
            with app.test_client() as c:
                res=c.get("/api/r31-private-qa/sol-report")
        self.assertEqual(res.status_code,503)

    def test_secret_must_exist_with_exact_qa_database_and_role(self):
        with self.assertRaises(StageBlocked):
            _credentials("ingest")

    def test_no_untrusted_owner_argument_in_route(self):
        import inspect
        from r31_stage_blueprint import qa_sync_receipt
        src=inspect.getsource(qa_sync_receipt)
        self.assertIn("owner=_valid_user()",src)
        self.assertNotIn("request.form.get(\"owner\")",src)
        self.assertNotIn("request.json.get(\"owner\")",src)
        self.assertIn("csrf_valid()",src)

    def test_runtime_app_rejects_anonymous_by_session_middleware(self):
        from app import app
        with app.test_client() as c:
            res=c.get("/auth/me")
        self.assertEqual(res.status_code,401)

    def test_existing_excel_parser_to_stage_plan_with_inr_notation(self):
        wb=Workbook()
        ws=wb.active
        ws.title="PAYMENT EVIDENCE"
        ws.append(["Description","SOL ID","Credit Amount"])
        ws.append(["QA TEST","001505","₹1,234.50"])
        ws.append(["QA INVALID","001505","0"])
        data=BytesIO()
        wb.save(data)
        source=data.getvalue()
        parsed=_parse(source)
        self.assertEqual((parsed["source_rows"],parsed["valid_rows"],parsed["review_rows"]),(2,1,1))
        name,raw,eligible,review=_extract_original_source(source,parsed)
        self.assertEqual(name,"PAYMENT EVIDENCE")
        self.assertEqual(eligible[0][2],123450)
        self.assertEqual(raw[0][1]["SOL ID"],"001505")
        plan=build_plan(
            trusted_owner="qa-user",trusted_receipt_id="a"*32,
            original_file_name="source.XLSX",source_sheet_name=name,
            raw_file=source,all_source_rows=raw,
            parser_eligible_rows=eligible,parser_review_rows=review,
            approved_master_lookup=None,
        )
        self.assertEqual([x.amount_paise for x in plan.rows],[123450,None])
        self.assertEqual(plan.rows[0].status,"HOLD_SOL_MASTER")

    def test_numerical_credit_input_matches_source_parser(self):
        wb=Workbook()
        ws=wb.active
        ws.title="PAYMENT EVIDENCE"
        ws.append(["Description","SOL ID","Credit Amount"])
        ws.append(["QA NUMERIC","001505",118])
        data=BytesIO()
        wb.save(data)
        parsed=_parse(data.getvalue())
        _,raw,eligible,review=_extract_original_source(data.getvalue(),parsed)
        self.assertEqual((eligible[0][2],len(review)),(11800,0))
        self.assertEqual(raw[0][1]["Credit Amount"],"118")

if __name__=="__main__":
    import unittest
    unittest.main(verbosity=2)
