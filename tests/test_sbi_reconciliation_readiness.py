"""SBI payment evidence -> financial engine readiness bridge (no finance execution)."""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
for folder in (ROOT/"dashboard_source",ROOT/"staging/aws_login_v150",
               ROOT/"staging/railway_public"):
    sys.path.insert(0,str(folder))
spec=importlib.util.spec_from_file_location("sbi_finance_preflight_qa",
                                             ROOT/"staging/aws_login_v150/app.py")
appmod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def evidence(rows=None):
    wb=Workbook()
    sh=wb.active
    sh.title="PAYMENT EVIDENCE"
    sh.append(["Description","SOL ID","Credit Amount"])
    for row in rows or [("SYNTHETIC ONLY AUG-26","001505",100)]:
        sh.append(row)
    output=io.BytesIO()
    wb.save(output)
    return output.getvalue()


class PaymentReconciliationReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="reconcile-gate-synthetic-")
        self.addCleanup(self.temp.cleanup)
        appmod.app.testing=True
        self.client=appmod.app.test_client()
        self.client.set_cookie("__Host-dil_session","synthetic",secure=True)
        self.client.set_cookie("__Host-dil_csrf","a"*64,secure=True)
    def auth(self,uid="qa-user"):
        stack=ExitStack()
        user=SimpleNamespace(uid=uid,email="test@example.invalid",
                             disabled=False,display_name="QA",
                             custom_claims={"dil_dashboard":True})
        stack.enter_context(patch.dict(os.environ,
            {"SBI_PAYMENT_EVIDENCE_DIR":self.temp.name,
             "SBI_PRIVATE_WORKSPACE_DB":""}))
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",
                                  return_value={"uid":uid}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=user))
        return stack
    def headers(self):
        return {"Origin":appmod.SITE_ORIGIN,"X-DIL-CSRF":"a"*64}
    def upload(self,rows=None):
        return self.client.post("/api/payment-evidence/upload",
            data={"file":(io.BytesIO(evidence(rows)),"synthetic.xlsx")},
            headers=self.headers(),content_type="multipart/form-data")
    def preflight(self,rid,headers=None):
        return self.client.post("/api/payment-reconciliation/preflight",
            json={"receipt_id":rid},headers=self.headers() if headers is None else headers)

    def test_unauthenticated_status_and_preflight_are_denied(self):
        anon=appmod.app.test_client()
        self.assertEqual(anon.get("/api/payment-reconciliation/status").status_code,401)
        self.assertEqual(anon.post("/api/payment-reconciliation/preflight").status_code,403)

    def test_status_is_explicitly_blocked_with_source_requirements(self):
        with self.auth():
            response=self.client.get("/api/payment-reconciliation/status")
            self.assertEqual(response.status_code,200)
            data=response.json
            self.assertEqual(data["engine"],"NOT_CONNECTED")
            self.assertEqual(data["state"],"BLOCKED_PRODUCTION_DEPENDENCIES")
            self.assertFalse(data["financial_writes"])
            self.assertFalse(data["reconciliation_executed"])
            self.assertFalse(data["payment_matching_executed"])
            self.assertEqual(data["required_source_sheets"],
                            ["PAYMNENT","Invoice Details."])
            self.assertEqual(data["required_bank_credit_column"],"PAYMNENT!I")
            self.assertIn("APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED",
                          data["blockers"])

    def test_valid_staged_receipt_fails_closed_without_engine(self):
        with self.auth():
            uploaded=self.upload()
            self.assertEqual(uploaded.status_code,201,uploaded.get_data(as_text=True))
            receipt=uploaded.json["receipt_id"]
            pre=self.preflight(receipt)
            self.assertEqual(pre.status_code,503,pre.get_data(as_text=True))
            self.assertEqual(pre.json["code"],"APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED")
            self.assertEqual(pre.json["receipt_id"],receipt)
            self.assertTrue(pre.json["evidence_verified"])
            self.assertEqual(pre.json["source_rows"],1)
            self.assertEqual(pre.json["valid_rows"],1)
            self.assertFalse(pre.json["financial_writes"])
            self.assertFalse(pre.json["reconciliation_executed"])
            self.assertFalse(pre.json["allocation_approved"])
            self.assertEqual(self.client.get("/api/payment-evidence/uploads").json["evidence"][0]["status"],
                             "STAGED_FOR_REVIEW")
            self.assertEqual(self.client.post("/api/payment-reconciliation/run",
                               json={"receipt_id":receipt},
                               headers=self.headers()).status_code,403)
            self.assertEqual(self.client.post("/api/imports/apply",
                               json={},headers=self.headers()).status_code,403)

    def test_flagged_receipt_cannot_enter_matching(self):
        with self.auth():
            result=self.upload([
                ("NEGATIVE SBISA","1",-20),
                ("SOL IS NUMERIC",1505,100),
            ])
            self.assertEqual(result.status_code,201)
            pre=self.preflight(result.json["receipt_id"])
            self.assertEqual(pre.status_code,409)
            self.assertEqual(pre.json["code"],"PAYMENT_EVIDENCE_REVIEW_REQUIRED")
            self.assertEqual(pre.json["review_rows"],2)
            self.assertFalse(pre.json["financial_writes"])

    def test_csrf_validation_and_account_isolation(self):
        with self.auth("alpha"):
            rid=self.upload().json["receipt_id"]
            self.assertEqual(self.preflight(rid,{"Origin":appmod.SITE_ORIGIN}).status_code,403)
            self.assertEqual(self.preflight(rid,{"Origin":"https://evil.invalid",
                        "X-DIL-CSRF":"a"*64}).status_code,403)
            self.assertEqual(self.preflight("not-a-receipt").status_code,422)
        with self.auth("beta"):
            self.assertEqual(self.preflight(rid).status_code,404)

    def test_hash_tamper_is_detected_and_no_update(self):
        with self.auth():
            receipt=self.upload().json["receipt_id"]
            (Path(self.temp.name)/(receipt+".xlsx")).write_bytes(b"modified")
            pre=self.preflight(receipt)
            self.assertEqual(pre.status_code,503)
            self.assertIn("integrity",pre.json["error"].lower())
            self.assertFalse(pre.json["financial_writes"])

    def test_ui_preflight_enabled_only_for_selected_receipt(self):
        html=(ROOT/"dashboard_source/index.html").read_text(encoding="utf-8")
        self.assertIn('id="dil-payment-readiness" disabled',html)
        self.assertIn('id="dil-payment-reconcile" disabled',html)
        self.assertIn("/api/payment-reconciliation/preflight",html)
        self.assertIn("readiness.disabled = !/^[a-f0-9]{32}$/.test(currentReceipt)",html)
        self.assertIn("No invoice or payment database updates occurred",html)
        self.assertIn("Apply Reconciliation to Financial Database — Locked",html)


if __name__=="__main__":
    unittest.main()
