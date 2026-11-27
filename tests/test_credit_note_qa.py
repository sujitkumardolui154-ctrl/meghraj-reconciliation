"""Credit-note generation regression, synthetic isolated invoice_qa ONLY.

No production DB, real customer invoice, bank evidence or GST filing changes.
"""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"dashboard_source"))
from credit_note_core import CreditNoteError, credit_note_request, build_credit_note

GSTIN="19AAACS8577K3ZK"
BASE={
    "credit_note_no":"MXP/2026-2027/01",
    "credit_note_date":"2026-05-31",
    "reason":"Courier charges deducted by the customer",
    "entries":[{"invoice_no":"MXP98001","credited_taxable":"250.00"},
               {"invoice_no":"MXP98002","credited_taxable":"500.00"}],
}
def fake_invoice(number,amt,cl="SBI_BANK",gstin=GSTIN):
    return {
        "invoice_no":number,"branch_key":"QA-BRANCH","invoice_date":"2026-03-28",
        "service_month":"February 2026","sol_id":"05011",
        "client_name":"QA SMECCC KOLKATA","gstin":gstin,
        "master_snapshot":{"client_class":cl,"recipient_title":"QA MANAGER",
                           "customer_address":"QA FICTIONAL ADDRESS"},
        "taxable":amt,"status":"FINALIZED","verification_flags":"",
        "cancelled":False,
    }


class PureCreditNoteContract(unittest.TestCase):
    def test_manual_note_number_date_and_multi_invoice_calc(self):
        invoices={"MXP98001":fake_invoice("MXP98001","1000.00"),
                  "MXP98002":fake_invoice("MXP98002","2000.00")}
        r=build_credit_note(BASE,invoices,{})
        self.assertEqual((r["taxable"],r["cgst"],r["sgst"],r["total"]),
                         ("750.00","67.50","67.50","885.00"))
        self.assertEqual(r["line_count"],2)
        self.assertEqual(r["lines"][0]["service_month"],"February 2026")
        self.assertEqual(r["lines"][0]["invoice_date"],"2026-03-28")
        self.assertFalse(r["gst_filing_updated"])
    def test_financial_year_must_match_manual_date(self):
        p=deepcopy(BASE);p["credit_note_no"]="MXP/2025-2026/01"
        with self.assertRaisesRegex(CreditNoteError,"FINANCIAL_YEAR_MISMATCH"):
            credit_note_request(p)
    def test_manual_credit_note_number_must_not_exceed_16_chars(self):
        p=deepcopy(BASE)
        p["credit_note_no"]="MXP/2026-2027/100"
        with self.assertRaisesRegex(CreditNoteError,"INVALID_CREDIT_NOTE_NUMBER"):
            credit_note_request(p)

    def test_no_unverified_or_missing_historical_records(self):
        with self.assertRaisesRegex(CreditNoteError,"NOT_FOUND_OR_NOT_IMPORTED"):
            build_credit_note(BASE,{}, {})
    def test_reject_duplicate_invoice_and_overcredit(self):
        p=deepcopy(BASE);p["entries"][1]["invoice_no"]="MXP98001"
        with self.assertRaisesRegex(CreditNoteError,"DUPLICATE_INVOICE_IN_CREDIT_NOTE"):
            credit_note_request(p)
        p=deepcopy(BASE);p["entries"][0]["credited_taxable"]="950.00"
        rows={"MXP98001":fake_invoice("MXP98001","1000.00"),
              "MXP98002":fake_invoice("MXP98002","2000.00")}
        with self.assertRaisesRegex(CreditNoteError,"EXCEEDS_REMAINING"):
            build_credit_note(p,rows,{"MXP98001":"100.00"})
    def test_reject_mixed_bank_and_fund_gstin(self):
        rows={"MXP98001":fake_invoice("MXP98001","1000.00"),
              "MXP98002":fake_invoice("MXP98002","2000.00",
                                      "SBI_FUND","19AAACS7339D1ZB")}
        with self.assertRaisesRegex(CreditNoteError,"MIXED_CUSTOMER_GSTIN"):
            build_credit_note(BASE,rows,{})
    def test_reject_source_cancelled(self):
        rows={"MXP98001":fake_invoice("MXP98001","1000.00"),
              "MXP98002":fake_invoice("MXP98002","2000.00")}
        rows["MXP98001"]["cancelled"]=True
        with self.assertRaisesRegex(CreditNoteError,"SOURCE_INVOICE_CANCELLED"):
            build_credit_note(BASE,rows,{})
    def test_reject_untrusted_credit_value(self):
        p=deepcopy(BASE);p["entries"][0]["credited_taxable"]=10.0
        with self.assertRaisesRegex(CreditNoteError,"INVALID_CREDIT_AMOUNT"):
            credit_note_request(p)
        p=deepcopy(BASE);p["entries"][0]["credited_taxable"]="10.555"
        with self.assertRaisesRegex(CreditNoteError,"INVALID_CREDIT_AMOUNT"):
            credit_note_request(p)


@unittest.skipUnless(os.environ.get("SBI_INVOICE_GST_TEST_DSN"),
                     "Dedicated invoice_qa PostgreSQL not configured")
class IsolatedCreditNotePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from PIL import Image
        from flask import Flask,g
        from credit_note_feature import create_credit_note_blueprint
        cls.psycopg=psycopg
        dsn=os.environ["SBI_INVOICE_GST_TEST_DSN"]
        cls.connect=staticmethod(lambda:psycopg.connect(dsn,row_factory=dict_row))
        cls.original={k:os.environ.get(k) for k in
                      ("SBI_CREDIT_NOTE_ENABLED","SBI_CREDIT_NOTE_FINALIZE_ENABLED",
                       "SBI_INVOICE_GST_DEPLOYMENT_MODE")}
        os.environ.update({
            "SBI_CREDIT_NOTE_ENABLED":"1",
            "SBI_CREDIT_NOTE_FINALIZE_ENABLED":"1",
            "SBI_INVOICE_GST_DEPLOYMENT_MODE":"ISOLATED_QA",
        })
        image=BytesIO()
        Image.new("RGB",(306,105),(235,245,250)).save(image,format="PNG")
        with cls.connect() as conn:
            if conn.execute("SELECT current_database() AS db").fetchone()["db"]!="invoice_qa":
                raise AssertionError("REFUSE_NON_ISOLATED_QA_DATABASE")
            conn.execute("DROP SCHEMA IF EXISTS sbi_invoice_gst CASCADE")
            for filename in (
                "001_isolated_invoice_schema.sql","002_vendor_header_fields.sql",
                "003_verified_sol_uniqueness.sql","004_invoice_cancellation_ledger.sql",
                "005_credit_note_registry.sql",
            ):
                conn.execute((ROOT/"staging/invoice-gst"/filename).read_text())
            conn.execute(
                """INSERT INTO sbi_invoice_gst.verified_branches (
                      branch_key,client_name,invoice_branch,invoice_generate_location,
                      original_branch_name,sol_id,client_class,gstin,recipient_title,
                      customer_address,state_code,verified,verified_by,verified_at)
                   VALUES ('QA-BRANCH','QA SMECCC KOLKATA','QA KOLKATA','QA KOLKATA',
                           'QA SMECCC','05011','SBI_BANK',%s,'QA MANAGER',
                           'QA FICTIONAL ADDRESS','19',TRUE,'QA REVIEWER',now())""",
                (GSTIN,),
            )
            conn.execute(
                """INSERT INTO sbi_invoice_gst.vendor_profiles
                   (vendor_key,legal_name,logo_image,logo_mime,exact_logo_verified,
                    declaration_text,bank_instructions,pan,gstin,vendor_id,
                    service_type,sac_code,footer_text,authorized_signature_label,
                    registered_office,registered_phone,registered_email,
                    head_office,head_phone,website,verified_by,verified_at)
                   VALUES ('MEGHRAJ_EXPRESS','MEGHRAJ EXPRESS',%s,'image/png',TRUE,
                           'QA DECLARATION','QA BANK','QA PAN','QA GSTIN',
                           'QA VENDOR','COURIER','996812','QA FOOTER','QA SIGNATURE',
                           'QA REGISTERED OFFICE','033 QA PHONE','qa@example.invalid',
                           'QA HEAD OFFICE','033 QA PHONE 2','qa.example.invalid',
                           'QA REVIEWER',now())""",
                (image.getvalue(),),
            )
            for number,amount in (("MXP98001","1000.00"),("MXP98002","2000.00")):
                row=fake_invoice(number,amount)
                tax=Decimal(amount)
                conn.execute(
                    """INSERT INTO sbi_invoice_gst.invoices
                      (invoice_no,branch_key,service_from,service_to,invoice_date,
                       service_month,service_month_key,fy,invoice_branch,
                       invoice_generate_location,original_branch_name,sol_id,
                       client_name,gstin,master_snapshot,taxable,cgst,sgst,total,
                       shipment_count,created_by_uid)
                      VALUES (%s,'QA-BRANCH','2026-02-01','2026-02-28','2026-03-28',
                              'February 2026','2026-02','2025-2026','QA KOLKATA',
                              'QA KOLKATA','QA SMECCC','05011','QA SMECCC KOLKATA',
                              %s,%s,%s,%s,%s,%s,1,'synthetic-qa-uid')""",
                    (number,GSTIN,Jsonb(row["master_snapshot"]),tax,
                     (tax*Decimal(".09")),(tax*Decimal(".09")),(tax*Decimal("1.18"))),
                )
                conn.execute(
                    """INSERT INTO sbi_invoice_gst.invoice_lines
                      (invoice_no,line_no,dispatch_date,lr_no,packet_ref_no,
                       consignee,weight_kg,amount)
                      VALUES (%s,1,'2026-02-04',%s,'','QA CONSIGNEE',0.100,%s)""",
                    (number,"QA-"+number,amount),
                )
        cls.app=Flask(__name__)
        @cls.app.before_request
        def set_user():
            g.dil_user=SimpleNamespace(uid="synthetic-credit-operator")
        cls.app.register_blueprint(create_credit_note_blueprint(
            can_read=lambda:True,can_create=lambda:True,
            csrf_valid=lambda:True,connection_factory=cls.connect,
        ))
        cls.client=cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        for k,v in cls.original.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

    def test_01_fetch_invoice_from_database(self):
        r=self.client.post("/api/credit-notes/lookup",json={
            "invoice_numbers":["MXP98001","MXP98002","MXP99999"]
        })
        self.assertEqual(r.status_code,200,r.get_json())
        values=r.get_json()["invoices"]
        self.assertEqual(values[0]["invoice_date"],"2026-03-28")
        self.assertEqual(values[0]["service_month"],"February 2026")
        self.assertEqual(values[0]["remaining_taxable"],"1000.00")
        self.assertEqual(values[2]["status"],"SOURCE_INVOICE_NOT_FOUND_OR_NOT_IMPORTED")

    def test_02_preview_is_readonly(self):
        r=self.client.post("/api/credit-notes/preview",json=BASE)
        self.assertEqual(r.status_code,200,r.get_json())
        self.assertEqual(r.get_json()["credit_note"]["total"],"885.00")
        with self.connect() as conn:
            count=conn.execute("SELECT count(*) AS n FROM sbi_invoice_gst.credit_notes").fetchone()["n"]
        self.assertEqual(count,0)

    def test_03_finalize_once_and_generate_credit_note_pdf(self):
        r=self.client.post("/api/credit-notes/finalize",json=BASE)
        self.assertEqual(r.status_code,201,r.get_json())
        self.assertTrue(r.get_json()["database_recorded"])
        self.assertFalse(r.get_json()["ledger_posted"])
        dup=self.client.post("/api/credit-notes/finalize",json=BASE)
        self.assertEqual(dup.status_code,409,dup.get_json())
        from pypdf import PdfReader
        pdf=self.client.get("/api/credit-notes/pdf?no=MXP%2F2026-2027%2F01")
        self.assertEqual(pdf.status_code,200,pdf.get_json() if pdf.is_json else "")
        self.assertTrue(pdf.data.startswith(b"%PDF-"))
        text="\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages)
        for label in ("CREDIT NOTE","MXP/2026-2027/01","MXP98001",
                      "MXP98002","Service Entry Modification Details","885.00"):
            self.assertIn(label,text)
        with self.connect() as conn:
            result=conn.execute(
                """SELECT count(*) AS n FROM sbi_invoice_gst.credit_note_lines
                   WHERE credit_note_no='MXP/2026-2027/01'""").fetchone()["n"]
            self.assertEqual(result,2)
            original=conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoices"
            ).fetchone()["n"]
            self.assertEqual(original,2)

    def test_04_prevent_overcredit_and_protect_immutable_records(self):
        proposed=deepcopy(BASE)
        proposed["credit_note_no"]="MXP/2026-2027/02"
        proposed["entries"][0]["credited_taxable"]="800.00"
        denied=self.client.post("/api/credit-notes/preview",json=proposed)
        self.assertEqual(denied.status_code,422,denied.get_json())
        self.assertIn("CREDIT_AMOUNT_EXCEEDS_REMAINING",denied.get_json()["error"])
        with self.connect() as conn:
            with self.assertRaises(self.psycopg.errors.RaiseException):
                with conn.transaction():
                    conn.execute(
                        """UPDATE sbi_invoice_gst.credit_notes SET taxable=1
                           WHERE credit_note_no='MXP/2026-2027/01'"""
                    )
            with self.assertRaises(self.psycopg.errors.RaiseException):
                with conn.transaction():
                    conn.execute(
                        """DELETE FROM sbi_invoice_gst.credit_note_lines
                           WHERE credit_note_no='MXP/2026-2027/01'"""
                    )

    def test_05_live_and_flag_off_never_finalize(self):
        p=deepcopy(BASE);p["credit_note_no"]="MXP/2026-2027/03"
        os.environ["SBI_CREDIT_NOTE_FINALIZE_ENABLED"]="0"
        try:
            r=self.client.post("/api/credit-notes/finalize",json=p)
            self.assertEqual(r.status_code,403,r.get_json())
        finally:
            os.environ["SBI_CREDIT_NOTE_FINALIZE_ENABLED"]="1"
        os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"]="APPROVED_LIVE"
        try:
            r=self.client.post("/api/credit-notes/finalize",json=p)
            self.assertEqual(r.status_code,403,r.get_json())
            self.assertEqual(r.get_json()["error"],
                             "LIVE_CREDIT_NOTE_REQUIRES_LEDGER_AND_GST_APPROVAL")
        finally:
            os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"]="ISOLATED_QA"

    def test_07_historical_report_lookup_never_authorizes_issue(self):
        from flask import Flask, g
        from credit_note_feature import create_credit_note_blueprint
        from invoice_source_schema import HEADERS_53
        number = "MXP99999"
        cells = [""] * 53
        cells[4], cells[5] = "March 2024", "2024-04-10"
        cells[6], cells[8] = "03970", "03970"
        cells[7], cells[9] = "QA SMECCC KOLKATA", "QA SMECCC KOLKATA"
        cells[11], cells[12] = GSTIN, number
        cells[13:17] = ["100.00", "9.00", "9.00", "118.00"]
        cells[25] = "0"
        def verified_source(requested):
            self.assertEqual(requested, [number])
            return {
                "version": "invoice-selection-v1",
                "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
                "dataset": "qa-pinned-source",
                "financial_writes": False,
                "reconciliation_executed": False,
                "database_updated": False,
                "requested_count": 1, "matched_count": 1, "review_count": 0,
                "matches": [{
                    "invoice_no": number, "values": cells,
                    "payment_kind": "unpaid", "balance_review": False,
                }],
                "review": [],
            }
        app = Flask(__name__)
        @app.before_request
        def identity():
            g.dil_user = SimpleNamespace(uid="qa-credit-user")
        app.register_blueprint(create_credit_note_blueprint(
            can_read=lambda: True, can_create=lambda: True,
            csrf_valid=lambda: True, connection_factory=self.connect,
            historical_lookup=verified_source,
        ))
        client = app.test_client()
        old = os.environ.get("SBI_CREDIT_NOTE_HISTORICAL_REPORT_REVIEW")
        os.environ["SBI_CREDIT_NOTE_HISTORICAL_REPORT_REVIEW"] = "1"
        try:
            lookup = client.post("/api/credit-notes/lookup", json={
                "invoice_numbers": ["MXP98001", number],
            })
            self.assertEqual(lookup.status_code, 200, lookup.get_json())
            a, b = lookup.get_json()["invoices"]
            self.assertTrue(a["credit_note_eligible"])
            self.assertEqual(b["source_kind"], "VERIFIED_READ_ONLY_REPORT_SOURCE")
            self.assertFalse(b["credit_note_eligible"])
            self.assertEqual(b["original_taxable"], "100.00")
            self.assertIsNone(b["remaining_taxable"])
            self.assertTrue(lookup.get_json()["historical_report_review"])
            self.assertFalse(lookup.get_json()["historical_issuance_authorized"])
            attempt = deepcopy(BASE)
            attempt["credit_note_no"] = "MXP/2026-2027/20"
            attempt["entries"] = [{
                "invoice_no": number, "credited_taxable": "20.00",
            }]
            # Even an accurate report row never enables preview or finalization.
            preview = client.post("/api/credit-notes/preview", json=attempt)
            self.assertEqual(preview.status_code, 422)
            self.assertIn("NOT_FOUND_OR_NOT_IMPORTED", preview.get_json()["error"])
            issued = client.post("/api/credit-notes/finalize", json=attempt)
            self.assertEqual(issued.status_code, 422)
            with self.connect() as conn:
                n = conn.execute(
                    "SELECT count(*) AS n FROM sbi_invoice_gst.credit_notes "
                    "WHERE credit_note_no='MXP/2026-2027/20'"
                ).fetchone()["n"]
            self.assertEqual(n, 0)
        finally:
            if old is None:
                os.environ.pop("SBI_CREDIT_NOTE_HISTORICAL_REPORT_REVIEW", None)
            else:
                os.environ["SBI_CREDIT_NOTE_HISTORICAL_REPORT_REVIEW"] = old

    def test_06_separate_creator_claim_and_csrf(self):
        from flask import Flask,g
        from credit_note_feature import create_credit_note_blueprint
        payload=deepcopy(BASE);payload["credit_note_no"]="MXP/2026-2027/04"
        def make(can_create,csrf):
            app=Flask(__name__)
            @app.before_request
            def identity():
                g.dil_user=SimpleNamespace(uid="qa-actor")
            app.register_blueprint(create_credit_note_blueprint(
                can_read=lambda:True,can_create=can_create,
                csrf_valid=csrf,connection_factory=self.connect,
            ))
            return app.test_client()
        r=make(lambda:False,lambda:True).post("/api/credit-notes/finalize",json=payload)
        self.assertEqual(r.status_code,403)
        self.assertEqual(r.get_json()["error"],"CREDIT_NOTE_CREATOR_PERMISSION_REQUIRED")
        r=make(lambda:True,lambda:False).post("/api/credit-notes/finalize",json=payload)
        self.assertEqual(r.status_code,403)
        self.assertEqual(r.get_json()["error"],"CSRF_VERIFICATION_FAILED")
