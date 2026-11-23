"""Stage 31.4 isolated Flask test-client integration: synthetic auth, no DB."""
import io
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from openpyxl import Workbook

from invoice_source_schema import HEADERS_34,HEADERS_35,HEADERS_53
from stage31_2_schema_design import SOURCE_COLUMNS
from stage31_4_private_preview import create_private_preview_blueprint

HEADER_BY_WIDTH={34:HEADERS_34,35:HEADERS_35,53:HEADERS_53}

def invoice_xlsx(width=34,repeat=1,invoice_no="STAGE31-PRIVATE-TEST-001",headers=None):
    wb=Workbook()
    ws=wb.active
    ws.title="Invoice Details." if width!=53 else "Approved 53 source"
    ws.append(list(headers if headers is not None else HEADER_BY_WIDTH[width]))
    idx=SOURCE_COLUMNS[width]
    for x in range(repeat):
        r=[""]*width
        r[0]=r[7]="TEST VERIFIED BRANCH"
        r[idx["invoice_no"]]=invoice_no
        r[idx["invoice_branch"]]="TEST INVOICE LOCATION"
        r[idx["month"]]="October 2026"
        r[idx["invoice_date"]]="2026-11-12"
        r[idx["branch_code_primary"]]="001505"
        if "branch_code_secondary" in idx:
            r[idx["branch_code_secondary"]]="001505"
        r[idx["taxable_amount"]]="100.00"
        r[idx["cgst"]]="9.00"
        r[idx["sgst"]]="9.00"
        r[idx["total_bill_amount"]]="118.00"
        ws.append(r)
    out=io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()

def payment_xlsx(rows=None,headers=None):
    wb=Workbook()
    ws=wb.active
    ws.title="Payment Evidence"
    ws.append(list(headers or ("Description","SOL ID","Credit Amount")))
    for row in (rows if rows is not None else [("AUG-26 POSTAGE","001505","113.84")]):
        ws.append(list(row))
    out=io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()

class PrivateFlaskIntegration(unittest.TestCase):
    def setUp(self):
        self.flags={"auth":True,"csrf":True}
        self.app=Flask(__name__)
        self.app.config.update(TESTING=True,SBI_STAGE31_4_PRIVATE_ENABLED=True)
        self.app.register_blueprint(create_private_preview_blueprint(
           auth_guard=lambda:self.flags["auth"],
           csrf_guard=lambda:self.flags["csrf"]))
        self.client=self.app.test_client()

    def send(self,kind="invoice",payload=None,filename=None):
        if payload is None:
            payload=invoice_xlsx() if kind=="invoice" else payment_xlsx()
        return self.client.post("/__stage31_4/"+kind+"/preview",
            data={"file":(io.BytesIO(payload),filename or ("invoice.xlsx" if kind=="invoice" else "payment.xlsx"))},
            content_type="multipart/form-data")

    def test_private_feature_off_returns_404_even_when_registered(self):
        self.app.config["SBI_STAGE31_4_PRIVATE_ENABLED"]=False
        self.assertEqual(self.send().status_code,404)
    def test_missing_real_auth_callbacks_fails_closed(self):
        app=Flask(__name__+"_no_callbacks")
        app.config.update(TESTING=True,SBI_STAGE31_4_PRIVATE_ENABLED=True)
        app.register_blueprint(create_private_preview_blueprint())
        self.assertEqual(app.test_client().post("/__stage31_4/invoice/apply").status_code,503)
    def test_anonymous_invoice_preview_denied(self):
        self.flags["auth"]=False
        result=self.send()
        self.assertEqual(result.status_code,401)
        self.assertEqual(result.json["error"],"Login required")
    def test_anonymous_payment_preview_denied(self):
        self.flags["auth"]=False
        self.assertEqual(self.send("payment").status_code,401)
    def test_anonymous_apply_denied(self):
        self.flags["auth"]=False
        self.assertEqual(self.client.post("/__stage31_4/invoice/apply").status_code,401)
    def test_csrf_denied_for_authenticated_user(self):
        self.flags["csrf"]=False
        self.assertEqual(self.send().status_code,403)
    def test_csrf_denied_for_apply_as_well(self):
        self.flags["csrf"]=False
        self.assertEqual(self.client.post("/__stage31_4/payment/apply").status_code,403)
    def test_invoice_34_35_53_source_layouts_preview(self):
        for width in (34,35,53):
            with self.subTest(width=width):
                result=self.send(payload=invoice_xlsx(width))
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json["source_column_count"],width)
                self.assertEqual(result.json["source_contract_ready_count"],1)
                self.assertFalse(result.json["database_changed"])
                self.assertFalse(result.json["production_uniqueness_checked"])
                self.assertEqual(result.json["status"],"REVIEW_REQUIRED_NO_DATABASE_WRITE")
                self.assertNotIn("candidate_fields",result.json)
    def test_invoice_duplicate_never_ready(self):
        result=self.send(payload=invoice_xlsx(repeat=2))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_contract_ready_count"],0)
        self.assertEqual(result.json["source_rejected_count"],2)
    def test_exact_invoice_header_order_required(self):
        headers=list(HEADERS_34)
        headers[0],headers[1]=headers[1],headers[0]
        result=self.send(payload=invoice_xlsx(headers=headers))
        self.assertEqual(result.status_code,400)
    def test_fake_xlsx_rejected(self):
        result=self.send(payload=b"not-xlsx",filename="invoice.xlsx")
        self.assertEqual(result.status_code,400)
    def test_wrong_extension_rejected(self):
        result=self.send(payload=invoice_xlsx(),filename="invoice.txt")
        self.assertEqual(result.status_code,400)
    def test_payment_3_column_evidence_preview(self):
        result=self.send("payment")
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_contract_ready_count"],1)
        self.assertEqual(result.json["bank_transaction_identity_verified"],False)
        self.assertEqual(result.json["original_payment_A_to_L_mapped"],False)
        self.assertFalse(result.json["database_changed"])
    def test_payment_duplicate_requires_review(self):
        r=[("AUG-26 POSTAGE","1505","113.84")]*2
        result=self.send("payment",payment_xlsx(rows=r))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_contract_ready_count"],0)
        self.assertEqual(result.json["source_rejected_count"],2)
    def test_payment_numeric_sol_rejected_do_not_drop_leading_zero(self):
        result=self.send("payment",payment_xlsx(rows=[("AUG-26 POSTAGE",1505,"113.84")]))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_rejected_count"],1)
    def test_payment_header_reordering_rejected(self):
        result=self.send("payment",payment_xlsx(headers=("SOL ID","Description","Credit Amount")))
        self.assertEqual(result.status_code,400)
    def test_payment_credit_numeric_cell_rejected(self):
        result=self.send("payment",payment_xlsx(rows=[("AUG-26 POSTAGE","1505",113.84)]))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_rejected_count"],1)
    def test_apply_invoice_is_locked_even_authorized(self):
        result=self.client.post("/__stage31_4/invoice/apply")
        self.assertEqual(result.status_code,423)
        self.assertFalse(result.json["database_changed"])
    def test_apply_payment_is_locked_even_authorized(self):
        result=self.client.post("/__stage31_4/payment/apply")
        self.assertEqual(result.status_code,423)
    def test_only_allowed_intake_types(self):
        self.assertEqual(self.send("credit-note").status_code,404)
    def test_source_hash_in_response_but_no_invoice_details(self):
        result=self.send()
        self.assertRegex(result.json["source_sha256"],r"^[a-f0-9]{64}$")
        self.assertNotIn("original_values",result.json)
        self.assertNotIn("STAGE31-PRIVATE-TEST-001",str(result.json))
    def test_xlsx_preview_works_when_optional_xlrd_unavailable(self):
        # The private image deliberately has no xlrd. XLSX parsing must not
        # depend on the old XLS-only optional package at import time.
        with patch.dict(sys.modules, {"xlrd": None}):
            result=self.send(payload=invoice_xlsx())
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["source_contract_ready_count"],1)

    def test_xls_missing_optional_reader_fails_closed(self):
        # Valid OLE header, but NOT a valid XLS: absence of xlrd must result
        # in explicit refusal, not import-time failure of all preview routes.
        ole=bytes.fromhex("d0cf11e0a1b11ae1")+bytes(80)
        with patch.dict(sys.modules, {"xlrd": None}):
            result=self.send(payload=ole,filename="invoice.xls")
        self.assertEqual(result.status_code,400)
        self.assertEqual(result.json["error"],"XLS_READER_UNAVAILABLE_IN_PRIVATE_IMAGE")

    def test_no_cache_on_all_private_responses(self):
        for response in (self.send(),self.client.post("/__stage31_4/invoice/apply")):
            self.assertEqual(response.headers["Cache-Control"],"no-store")

if __name__=="__main__":
    unittest.main(verbosity=2)
