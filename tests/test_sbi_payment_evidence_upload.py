"""Fixed-format Excel payment evidence: CSRF, receipt, review and finance-deny QA."""
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

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "dashboard_source", ROOT / "staging/aws_login_v150",
          ROOT / "staging/railway_public"):
    sys.path.insert(0, str(p))
spec = importlib.util.spec_from_file_location(
    "sbi_payment_evidence_qa", ROOT / "staging/aws_login_v150/app.py"
)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def workbook(headers=("Description","SOL ID","Credit Amount"), rows=None):
    wb = Workbook()
    sh = wb.active
    sh.title = "PAYMENT EVIDENCE"
    sh.append(headers)
    for row in rows or [("POSTAGE CHARGE AUG-2026","001505", 113.84)]:
        sh.append(row)
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


class PaymentEvidenceUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sbi-evidence-")
        self.addCleanup(self.tmp.cleanup)
        server.app.testing = True
        self.client = server.app.test_client()
        self.csrf = "a" * 64
        self.client.set_cookie("__Host-dil_session", "synthetic", secure=True)
        self.client.set_cookie("__Host-dil_csrf", self.csrf, secure=True)

    def auth(self, uid="qa-user"):
        stack = ExitStack()
        user = SimpleNamespace(
            uid=uid, email="test@example.invalid", disabled=False,
            display_name="QA", custom_claims={"dil_dashboard":True}
        )
        stack.enter_context(patch.dict(
            os.environ, {"SBI_PAYMENT_EVIDENCE_DIR":self.tmp.name}
        ))
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch(
            "dashboard_sessions.auth.verify_session_cookie",
            return_value={"uid":uid},
        ))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=user))
        return stack

    def headers(self):
        return {"Origin":server.SITE_ORIGIN,"X-DIL-CSRF":self.csrf}

    def send(self, payload, filename="payment.xlsx", headers=None):
        return self.client.post(
            "/api/payment-evidence/upload",
            data={"file":(io.BytesIO(payload),filename)},
            headers=headers if headers is not None else self.headers(),
            content_type="multipart/form-data"
        )

    def test_fixed_template_is_downloadable_with_text_sol_id(self):
        unauthorized = server.app.test_client().get("/api/payment-evidence/template")
        self.assertEqual(unauthorized.status_code,401)
        with self.auth():
            template=self.client.get("/api/payment-evidence/template")
            self.assertEqual(template.status_code,200)
            self.assertIn("attachment",template.headers["Content-Disposition"])
            wb=load_workbook(io.BytesIO(template.data),read_only=False)
            sheet=wb.active
            self.assertEqual(sheet.title,"PAYMENT EVIDENCE")
            self.assertEqual([sheet.cell(1,col).value for col in (1,2,3)],
                ["Description","SOL ID","Credit Amount"])
            self.assertEqual(sheet["B2"].number_format,"@")
            wb.close()

    def test_stage_preview_persist_receipt_owner_isolation_and_duplicate(self):
        source=workbook(rows=[
            ("BULK POSTING FOR AUG-26","001505",113.84),
            ("BULK POSTING FOR SEP-26","1",55.25),
        ])
        with self.auth():
            resp=self.send(source)
            self.assertEqual(resp.status_code,201,resp.get_data(as_text=True))
            result=resp.json
            self.assertEqual(result["header"],["Description","SOL ID","Credit Amount"])
            self.assertEqual(result["source_rows"],2)
            self.assertEqual(result["valid_rows"],2)
            self.assertEqual(result["review_rows"],0)
            self.assertEqual(result["valid_credit_total"],"169.09")
            self.assertEqual(result["preview"][0]["sol_id"],"001505")
            self.assertFalse(result["financial_writes"])
            self.assertFalse(result["reconciliation_executed"])
            receipt=result["receipt_id"]
            self.assertEqual(len(receipt),32)
            self.assertEqual(self.client.get("/api/payment-evidence/uploads").status_code,200)
            again=self.client.get("/api/payment-evidence/uploads/"+receipt)
            self.assertEqual(again.status_code,200)
            self.assertEqual(again.json["preview"][0]["credit_amount"],"113.84")
            self.assertEqual(self.send(source).status_code,409)
            stored=Path(self.tmp.name)/(receipt+".xlsx")
            self.assertTrue(stored.is_file())
            self.assertEqual(stored.stat().st_mode & 0o777,0o600)
            self.assertEqual(self.client.get("/api/reports").status_code,403)
            self.assertEqual(self.client.post(
                "/api/payment-reconciliation/run",
                headers={"Origin":server.SITE_ORIGIN}
            ).status_code,403)
        with self.auth("other-user"):
            self.assertEqual(self.client.get("/api/payment-evidence/uploads").json["evidence"],[])
            self.assertEqual(self.client.get("/api/payment-evidence/uploads/"+receipt).status_code,404)

    def test_malformed_headers_formula_duplicate_and_numeric_sol_review(self):
        with self.auth():
            invalid=self.send(workbook(headers=("Description","SOL Code","Credit Amount")))
            self.assertEqual(invalid.status_code,422)
            self.assertIn("Incorrect headers",invalid.json["error"])
            self.assertEqual(list(Path(self.tmp.name).glob("*.xlsx")),[])
            wrongformat=self.send(b"abc",filename="old.xls")
            self.assertEqual(wrongformat.status_code,422)
            formula_and_flags=workbook(rows=[
                ("NARRATION", 1505, 100),
                ("NARRATION", 1505, 100),
                ("OTHER","1","=1+2"),
                ("INVALID","2","not numeric"),
                ("REVERSAL","3",-25),
            ])
            response=self.send(formula_and_flags)
            self.assertEqual(response.status_code,201,response.get_data(as_text=True))
            result=response.json
            self.assertEqual(result["source_rows"],5)
            self.assertEqual(result["valid_rows"],0)
            self.assertEqual(result["review_rows"],5)
            flags=result["review_flag_counts"]
            self.assertEqual(flags["SOL_ID_MUST_BE_TEXT_REVIEW_LEADING_ZEROS"],2)
            self.assertEqual(flags["REPEATED_SOURCE_ROW_REVIEW"],1)
            self.assertEqual(flags["FORMULA_NOT_ALLOWED"],1)
            self.assertEqual(flags["CREDIT_AMOUNT_INVALID"],1)
            self.assertEqual(flags["NON_POSITIVE_CREDIT_REVIEW"],1)
            self.assertEqual(result["staging_status"],"REVIEW_REQUIRED")
            self.assertEqual(result["valid_credit_total"],"0.00")

    def test_secure_origin_rejects_untrusted_upload_and_unavailable_storage(self):
        payload=workbook()
        with self.auth():
            self.assertEqual(self.send(payload,headers={
                "Origin":"https://evil.invalid","X-DIL-CSRF":self.csrf
            }).status_code,403)
            self.assertEqual(self.send(payload,headers={
                "Origin":server.SITE_ORIGIN
            }).status_code,403)
            self.assertEqual(self.send(payload,filename="x.csv").status_code,422)
            self.assertEqual(self.send(b"not-a-zip",filename="x.xlsx").status_code,422)
            self.assertEqual(self.send(payload).status_code,201)
            self.assertEqual(self.send(payload).status_code,409)
            with patch.dict(os.environ,{"SBI_PAYMENT_EVIDENCE_DIR":""}):
                self.assertEqual(
                    self.client.get("/api/payment-evidence/uploads").status_code,503
                )

    def test_ui_has_enabled_fixed_header_upload_and_blocked_reconciliation(self):
        html=(ROOT/"dashboard_source/index.html").read_text()
        css=(ROOT/"dashboard_source/dashboard_theme.css").read_text()
        self.assertIn('id="dil-payment-upload-form"',html)
        self.assertIn('id="dil-payment-evidence-file" name="file"',html)
        self.assertIn('id="dil-payment-preview">Upload &amp; Preview',html)
        self.assertIn('href="/api/payment-evidence/template"',html)
        self.assertIn('id="dil-payment-reconcile" disabled',html)
        self.assertIn('Description | SOL ID | Credit Amount',html)
        self.assertIn('X-DIL-CSRF',html)
        self.assertIn('/api/payment-evidence/upload',html)
        self.assertIn('/api/payment-evidence/uploads',html)
        self.assertIn('financial database',html)
        self.assertIn('.dil-payment-fixed-columns',css)
        self.assertIn("openpyxl", (ROOT/"staging/aws_login_v150/requirements.txt").read_text())


if __name__ == "__main__":
    unittest.main()
