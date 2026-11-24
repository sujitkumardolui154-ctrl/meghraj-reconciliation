"""R31: payment received database and SOL group report integration tests.

Synthetic XLSX and branch identities only. No real SBI bank rows or writes.
"""
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT/"dashboard_source",ROOT/"staging/aws_login_v150",
             ROOT/"staging/railway_public"):
    sys.path.insert(0,str(path))
spec=importlib.util.spec_from_file_location("r31_aws_app",
                                            ROOT/"staging/aws_login_v150/app.py")
app_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
import payment_received_ledger as ledger

USER="r31-test-user"
CSRF="b"*64


def sample(rows=None):
    wb=Workbook()
    sh=wb.active
    sh.title="PAYMENT EVIDENCE"
    sh.append(["Description","SOL ID","Credit Amount"])
    for row in (rows if rows is not None else [
        ("BANK POSTAGE FOR AUG-26","001505",113.84),
        ("BANK POSTAGE FOR SEP-26","0006884",200.00),
        ("BANK POSTAGE FOR NOV-26","99922",85.00),
        ("PAYMENT WITHOUT MASTER","00999999",25.00),
        ("BANK POSTAGE NOVEMBER","001505",15.20),
    ]):
        sh.append(row)
    b=io.BytesIO()
    wb.save(b)
    wb.close()
    return b.getvalue()


class R31PaymentRowsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="r31-ledger-")
        self.addCleanup(self.tmp.cleanup)
        app_module.app.testing=True
        self.client=app_module.app.test_client()
        self.client.set_cookie("__Host-dil_session","offline-synthetic",secure=True)
        self.client.set_cookie("__Host-dil_csrf",CSRF,secure=True)
        self.master_path=Path(self.tmp.name)/"private-sol-master.json"
        self.master={
            "schema":ledger.MASTER_SCHEMA,
            "branches":[
                {"sol_id":"1505","official_branch_name":"SOUTHERN AVENUE","approved":True},
                {"sol_id":"6884","official_branch_name":"ZONAL OFFICE KOLKATA","approved":True},
                {"sol_id":"6884","official_branch_name":"TRANSACTION BANKING HUB","approved":True},
                {"sol_id":"99922","official_branch_name":"FUND KHAGRA","approved":False},
            ],
        }
        self.write_master()

    def write_master(self):
        raw=json.dumps(self.master,sort_keys=True).encode()
        self.master_path.write_bytes(raw)
        self.master_path.chmod(0o600)
        self.master_digest=hashlib.sha256(raw).hexdigest()

    def auth(self,user=USER,master=True):
        stack=ExitStack()
        u=SimpleNamespace(uid=user,email="r31@example.invalid",
                          disabled=False,display_name="QA",
                          custom_claims={"dil_dashboard":True})
        env={"SBI_PAYMENT_EVIDENCE_DIR":self.tmp.name,
             "SBI_PAYMENT_SOL_MASTER_FILE":str(self.master_path) if master else "",
             "SBI_PAYMENT_SOL_MASTER_SHA256":self.master_digest if master else ""}
        stack.enter_context(patch.dict(os.environ,env))
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",
                                  return_value={"uid":user}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=u))
        return stack

    def upload(self,rows=None):
        return self.client.post("/api/payment-evidence/upload",
            data={"file":(io.BytesIO(sample(rows)),"approved_payment.xlsx")},
            headers={"Origin":app_module.SITE_ORIGIN,"X-DIL-CSRF":CSRF},
            content_type="multipart/form-data")

    def groups(self):
        r=self.client.get("/api/payment-received/sol-report")
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        return r.json

    def test_01_payment_upload_persists_every_row_in_private_database(self):
        with self.auth():
            r=self.upload()
            self.assertEqual(r.status_code,201,r.get_data(as_text=True))
            self.assertEqual(r.json["payment_rows_recorded"],5)
            self.assertEqual(r.json["pending_reconciliation"],2)
            self.assertEqual(r.json["master_mapping_review"],3)
            self.assertFalse(r.json["reconciliation_executed"])
            with closing(sqlite3.connect(Path(self.tmp.name)/"receipts.sqlite3")) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM payment_received_evidence_v1").fetchone()[0],5)

    def test_02_autofill_approved_branch_preserves_leading_zeros(self):
        with self.auth():
            r=self.upload().json
            p=r["payment_preview"][0]
            self.assertEqual(p["sol_id"],"001505")
            self.assertEqual(p["branch_name"],"SOUTHERN AVENUE")
            self.assertEqual(p["ledger_status"],ledger.STATUS_PENDING)
            self.assertEqual(p["credit_amount"],"113.84")

    def test_03_sol_collision_is_not_auto_resolved(self):
        with self.auth():
            r=self.upload().json
            p=r["payment_preview"][1]
            self.assertEqual(p["branch_name"],"PENDING_SOL_MASTER")
            self.assertIn("SOL_MASTER_MAPPING_PENDING_OR_AMBIGUOUS",
                          p["review_flags"])
            self.assertEqual(p["ledger_status"],ledger.STATUS_MASTER)

    def test_04_unapproved_master_branch_not_auto_resolved(self):
        with self.auth():
            p=self.upload().json["payment_preview"][2]
            self.assertEqual(p["ledger_status"],ledger.STATUS_MASTER)

    def test_05_unknown_sol_stored_for_review(self):
        with self.auth():
            p=self.upload().json["payment_preview"][3]
            self.assertEqual(p["sol_id"],"00999999")
            self.assertEqual(p["ledger_status"],ledger.STATUS_MASTER)

    def test_06_report_sol_counts_and_totals_no_fake_reconciliation(self):
        with self.auth():
            self.upload()
            report=self.groups()
            self.assertEqual(report["totals"],
                             {"payment_rows":5,"matched":0,
                              "not_calculated":5,"excluded":0})
            self.assertFalse(report["reconciliation_executed"])
            self.assertFalse(report["master_v251_matrix_v239_connected"])
            sol={x["sol_id"]:x for x in report["sol_groups"]}
            self.assertEqual(sol["1505"]["payment_rows"],2)
            self.assertEqual(sol["1505"]["credit_total"],"129.04")
            self.assertEqual(sol["1505"]["matched"],0)
            self.assertEqual(sol["1505"]["not_calculated"],2)
            self.assertEqual(sol["6884"]["held_for_review"],1)

    def test_07_details_and_summary_csv_are_authenticated(self):
        with self.auth():
            self.upload()
            summary=self.client.get("/api/payment-received/sol-report.csv")
            detail=self.client.get("/api/payment-received/payment-details.csv")
            self.assertEqual(summary.status_code,200)
            self.assertEqual(detail.status_code,200)
            self.assertIn("SOUTHERN AVENUE",detail.get_data(as_text=True))
            self.assertIn("Matched,Not Calculated,Excluded",summary.get_data(as_text=True))
            self.assertEqual(summary.headers["X-Reconciliation-Engine"],"NOT_CONNECTED")

    def test_08_previous_receipt_reloads_persisted_branch(self):
        with self.auth():
            data=self.upload().json
            rid=data["receipt_id"]
            q=self.client.get("/api/payment-evidence/uploads/"+rid).json
            self.assertEqual(q["payment_rows_recorded"],5)
            self.assertEqual(q["payment_preview"][0]["branch_name"],"SOUTHERN AVENUE")

    def test_09_future_engine_input_returns_only_eligible_rows(self):
        with self.auth():
            self.upload()
            with closing(sqlite3.connect(Path(self.tmp.name)/"receipts.sqlite3")) as conn:
                conn.row_factory=sqlite3.Row
                eligible=ledger.source_payment_rows(conn,USER,eligible_only=True)
            self.assertEqual(len(eligible),2)
            self.assertTrue(all(x["official_branch_name"]=="SOUTHERN AVENUE"
                                for x in eligible))

    def test_10_second_receipt_duplicate_candidate_not_double_matched(self):
        with self.auth():
            self.upload()
            second=self.upload(rows=[
                ("BANK POSTAGE FOR AUG-26","001505",113.84),
                ("NEW SEPARATE PAYMENT","001505",8.75),
            ])
            self.assertEqual(second.status_code,201,second.get_data(as_text=True))
            data=second.json
            self.assertEqual(data["duplicate_candidate_review"],1)
            self.assertEqual(data["pending_reconciliation"],1)
            self.assertEqual(data["payment_preview"][0]["ledger_status"],ledger.STATUS_DUPLICATE)
            self.assertEqual(self.groups()["totals"]["matched"],0)

    def test_11_bad_credit_eliminated_only_and_other_rows_continue(self):
        with self.auth():
            result=self.upload(rows=[
                ("INVALID","001505","not money"),
                ("GOOD","001505",99.55),
            ])
            self.assertEqual(result.status_code,201,result.get_data(as_text=True))
            self.assertEqual(result.json["excluded_invalid_source"],1)
            self.assertEqual(result.json["pending_reconciliation"],1)
            groups=self.groups()
            self.assertEqual(groups["totals"]["excluded"],1)
            self.assertEqual(groups["totals"]["not_calculated"],1)

    def test_12_nonnumeric_sol_excluded_locally_without_sum_parity_error(self):
        with self.auth():
            r=self.upload(rows=[
                ("UNKNOWN ALPHA SOL","ABC",8.50),
                ("GOOD","001505",10.00),
            ])
            self.assertEqual(r.status_code,201,r.get_data(as_text=True))
            self.assertEqual(r.json["valid_credit_total"],"18.50")
            self.assertEqual(r.json["excluded_invalid_source"],1)
            self.assertEqual(r.json["pending_reconciliation"],1)

    def test_13_numeric_sol_cell_gets_review_not_eligible(self):
        with self.auth():
            r=self.upload(rows=[
                ("NUMERIC SOL",1505,8.50),
                ("TEXT SOL","1505",20.00),
            ])
            self.assertEqual(r.status_code,201)
            self.assertEqual(r.json["excluded_invalid_source"],1)
            self.assertEqual(r.json["pending_reconciliation"],1)

    def test_14_missing_master_still_stores_evidence_on_hold(self):
        with self.auth(master=False):
            r=self.upload(rows=[("GOOD SOURCE","1505",17.25)])
            self.assertEqual(r.status_code,201)
            self.assertEqual(r.json["master_mapping_review"],1)
            self.assertEqual(r.json["pending_reconciliation"],0)
            self.assertEqual(r.json["payment_rows_recorded"],1)

    def test_15_wrong_master_sha_rolls_back_whole_receipt_and_payment_rows(self):
        with self.auth():
            with patch.dict(os.environ,{"SBI_PAYMENT_SOL_MASTER_SHA256":"0"*64}):
                r=self.upload()
            self.assertEqual(r.status_code,503)
            self.assertFalse(list(Path(self.tmp.name).glob("*.xlsx")))
            with closing(sqlite3.connect(Path(self.tmp.name)/"receipts.sqlite3")) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],0)

    def test_16_owner_scoping_prevents_other_user_rows(self):
        with self.auth():
            self.upload()
        with self.auth(user="another-user"):
            report=self.groups()
            self.assertEqual(report["totals"]["payment_rows"],0)

    def test_17_duplicate_entire_file_is_idempotent(self):
        with self.auth():
            self.assertEqual(self.upload().status_code,201)
            self.assertEqual(self.upload().status_code,409)
            self.assertEqual(self.groups()["totals"]["payment_rows"],5)

    def test_18_no_finance_or_db_update_api_exposed(self):
        with self.auth():
            self.upload()
            self.assertEqual(self.client.post(
                "/api/payment-reconciliation/run",headers={"Origin":app_module.SITE_ORIGIN}
            ).status_code,403)
            self.assertEqual(self.client.post(
                "/api/payment-received/sol-report",headers={"Origin":app_module.SITE_ORIGIN}
            ).status_code,403)
            self.assertFalse(self.groups()["financial_writes"])

    def test_19_unauthed_report_denied(self):
        client=app_module.app.test_client()
        self.assertEqual(client.get("/api/payment-received/sol-report").status_code,401)

    def test_20_ui_shows_mapped_branch_and_matched_uncalculated_excluded(self):
        html=(ROOT/"dashboard_source/index.html").read_text()
        for phrase in ("Payment Received — SOL-wise Reconciliation Tally",
                        "Official Branch Name","Not Calculated",
                        "/api/payment-received/sol-report",
                        "/api/payment-received/payment-details.csv",
                        "payment_preview","payment_rows_recorded"):
            self.assertIn(phrase,html)

    def test_21_csv_formula_injection_escaped_but_original_preserved(self):
        with self.auth():
            self.upload(rows=[
                ("@HYPERLINK(\"https://bad.invalid\")","1505",12.00),
                ("SAFE","1505",6.00),
            ])
            csvr=self.client.get("/api/payment-received/payment-details.csv")
            self.assertIn("'@HYPERLINK",csvr.get_data(as_text=True))
            with closing(sqlite3.connect(Path(self.tmp.name)/"receipts.sqlite3")) as conn:
                raw=conn.execute("SELECT description FROM payment_received_evidence_v1 "
                                 "WHERE excel_row=2").fetchone()[0]
            self.assertTrue(raw.startswith("@HYPERLINK"))

    def test_22_synthetic_master_tamper_detected(self):
        with self.auth():
            self.master_path.write_text('{"schema":"tampered"}')
            self.assertEqual(self.upload().status_code,503)

    def test_23_sol_canonical_identity_keeps_source_text(self):
        self.assertEqual(ledger.canonical_sol("0001505"),"1505")
        self.assertEqual(ledger.canonical_sol("000000"),None)
        self.assertIsNone(ledger.canonical_sol("1505.0"))
        self.assertIsNone(ledger.canonical_sol("15A5"))

    def test_24_no_private_source_reuse_assumed_to_be_verified_bank(self):
        with self.auth():
            self.upload()
            r=self.groups()
            self.assertTrue(r["matched_requires_independent_engine_evidence"])
            self.assertTrue(r["new_invoice_upload_can_reuse_saved_payment_inputs"])
            self.assertFalse(r["automatic_invoice_matching_enabled"])


if __name__=="__main__":
    unittest.main()
