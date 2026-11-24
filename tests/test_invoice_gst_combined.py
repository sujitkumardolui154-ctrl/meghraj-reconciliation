"""Combined invoice/GST contract + synthetic PostgreSQL API verification.

Never connects to a production DB: integration tests enforce exact
database name 'invoice_qa'. No real SBI/Meghraj source records are stored.
"""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard_source"))
from invoice_gst_core import (  # noqa: E402
    HEADERS, InvoiceError, build_invoice, gst_row,
)

BRANCH = {
    "verified": True, "branch_key": "synthetic-03970",
    "client_name": "QA SAMPLE VERIFIED BRANCH",
    "invoice_branch": "KOLKATA QA",
    "invoice_generate_location": "KOLKATA",
    "original_branch_name": "QA SAMPLE BRANCH NAME",
    "sol_id": "03970", "gstin": "19AAACS8577K3ZK",
    "client_class": "SBI_BANK", "recipient_title": "Assistant General Manager",
    "customer_address": "SYNTHETIC TEST ADDRESS, WEST BENGAL",
    "state_code": "19",
}
SOURCE = {
    "branch_key": BRANCH["branch_key"],
    "invoice_no": "MXP90001",
    "service_from": "2026-02-01", "service_to": "2026-02-28",
    "invoice_date": "2026-03-28",
    "shipments": [
        {"dispatch_date": "2026-02-02", "lr_no": "QA-LR1",
         "packet_ref_no": "", "consignee": "TEST CONSIGNEE 1",
         "weight_kg": "0.100", "amount": "1000.00"},
        {"dispatch_date": "2026-02-03", "lr_no": "QA-LR2",
         "packet_ref_no": "8", "consignee": "TEST CONSIGNEE 2",
         "weight_kg": "0.250", "amount": "2841.00"},
    ],
}


class PdfContractTests(unittest.TestCase):
    def test_rupees_words_match_the_source_invoice(self):
        from invoice_gst_pdf import money_in_words
        self.assertEqual(
            money_in_words("4532.38"),
            "Rupees Four Thousand Five Hundred Thirty Two and Thirty Eight Paisas Only",
        )

class ContractTests(unittest.TestCase):
    def test_original_sample_amounts_and_month_independence(self):
        value = build_invoice(SOURCE, BRANCH)
        self.assertEqual((value["taxable"], value["cgst"], value["sgst"], value["total"]),
                         ("3841.00", "345.69", "345.69", "4532.38"))
        self.assertEqual(value["service_month"], "February 2026")
        self.assertEqual(value["fy"], "2025-2026")
        self.assertEqual(value["invoice_date"], "2026-03-28")
        self.assertFalse(value["reconciliation_applied"])

    def test_gst_exact_16_columns_and_two_text_sol_fields(self):
        record = build_invoice(SOURCE, BRANCH)
        record["status"] = "FINALIZED"
        record["verification_flags"] = ""
        row = gst_row(record)
        self.assertEqual(len(row), 16)
        self.assertEqual(row[5], row[7])
        self.assertEqual(row[5], "03970")
        self.assertEqual(row[10:14], ("3841.00", "345.69", "345.69", "4532.38"))
        self.assertEqual(HEADERS[5], HEADERS[7])
        self.assertEqual(HEADERS[9:14], (
            "Invoice No", "Taxable Amount", "CGST", "SGST", "Total Bill Amount"
        ))

    def test_invoice_requires_verified_branch_master(self):
        with self.assertRaisesRegex(InvoiceError, "BRANCH_MASTER_NOT_VERIFIED"):
            build_invoice(SOURCE, {**BRANCH, "verified": False})

    def test_never_accept_generic_sbi_client_name(self):
        with self.assertRaisesRegex(InvoiceError, "GENERIC_CLIENT_NAME_NOT_ALLOWED"):
            build_invoice(SOURCE, {**BRANCH, "client_name": "STATE BANK OF INDIA"})

    def test_gstin_class_mismatch_is_rejected(self):
        with self.assertRaisesRegex(InvoiceError, "GSTIN_CLASS_MISMATCH"):
            build_invoice(SOURCE, {**BRANCH, "client_class": "SBI_FUND"})

    def test_duplicate_lr_is_rejected(self):
        wrong = deepcopy(SOURCE)
        wrong["shipments"][1]["lr_no"] = "QA-LR1"
        wrong["shipments"][1]["dispatch_date"] = "2026-02-02"
        with self.assertRaisesRegex(InvoiceError, "DUPLICATE_LR_IN_INVOICE"):
            build_invoice(wrong, BRANCH)

    def test_no_manual_override_of_amount(self):
        wrong = deepcopy(SOURCE)
        wrong["taxable"] = "9999999.00"
        actual = build_invoice(wrong, BRANCH)
        self.assertEqual(actual["taxable"], "3841.00")

    def test_invalid_invoice_number_and_dispatch_date(self):
        wrong = deepcopy(SOURCE)
        wrong["invoice_no"] = "CREDIT_NOTE-3"
        with self.assertRaisesRegex(InvoiceError, "INVALID_INVOICE_NUMBER"):
            build_invoice(wrong, BRANCH)
        wrong = deepcopy(SOURCE)
        wrong["shipments"][0]["dispatch_date"] = "2026-03-01"
        with self.assertRaisesRegex(InvoiceError, "DISPATCH_DATE_OUTSIDE_SERVICE_PERIOD"):
            build_invoice(wrong, BRANCH)

    def test_invalid_precision_and_floats(self):
        wrong = deepcopy(SOURCE)
        wrong["shipments"][0]["amount"] = "10.005"
        with self.assertRaisesRegex(InvoiceError, "INVALID_SHIPMENT_AMOUNT"):
            build_invoice(wrong, BRANCH)
        wrong["shipments"][0]["amount"] = 10.0
        with self.assertRaisesRegex(InvoiceError, "INVALID_SHIPMENT_AMOUNT"):
            build_invoice(wrong, BRANCH)

    def test_draft_or_unverified_gst_is_blocked(self):
        row = build_invoice(SOURCE, BRANCH)
        with self.assertRaisesRegex(InvoiceError, "DRAFT_NOT_EXPORTABLE"):
            gst_row(row)
        row["status"] = "FINALIZED"
        row["verification_flags"] = "SOURCE_REVIEW_REQUIRED"
        with self.assertRaisesRegex(InvoiceError, "UNVERIFIED_INVOICE_NOT_EXPORTABLE"):
            gst_row(row)


@unittest.skipUnless(os.environ.get("SBI_INVOICE_GST_TEST_DSN"), "QA Postgres not configured")
class IsolatedPostgresCombinedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        cls.psycopg = psycopg
        cls.dsn = os.environ["SBI_INVOICE_GST_TEST_DSN"]
        def connect():
            return psycopg.connect(cls.dsn, row_factory=dict_row)
        cls.connect = staticmethod(connect)
        from PIL import Image
        logo = BytesIO()
        Image.new("RGB", (306, 105), (230, 240, 250)).save(logo, "PNG")
        cls.synthetic_logo = logo.getvalue()
        with connect() as conn:
            name = conn.execute("SELECT current_database() AS db").fetchone()["db"]
            if name != "invoice_qa":
                raise AssertionError("REFUSE_NON_ISOLATED_TEST_DATABASE")
            conn.execute("DROP SCHEMA IF EXISTS sbi_invoice_gst CASCADE")
            ddl = (ROOT / "staging/invoice-gst/001_isolated_invoice_schema.sql").read_text()
            conn.execute(ddl)
            migration = (ROOT / "staging/invoice-gst/002_vendor_header_fields.sql").read_text()
            conn.execute(migration)
            verified_sol_index = (
                ROOT / "staging/invoice-gst/003_verified_sol_uniqueness.sql"
            ).read_text()
            conn.execute(verified_sol_index)
            conn.execute(
                """INSERT INTO sbi_invoice_gst.verified_branches
                   (branch_key,client_name,invoice_branch,invoice_generate_location,
                    original_branch_name,sol_id,client_class,gstin,recipient_title,
                    customer_address,state_code,verified,verified_by,verified_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,'qa-reviewer',now())""",
                (BRANCH["branch_key"], BRANCH["client_name"], BRANCH["invoice_branch"],
                 BRANCH["invoice_generate_location"], BRANCH["original_branch_name"],
                 BRANCH["sol_id"], BRANCH["client_class"], BRANCH["gstin"],
                 BRANCH["recipient_title"], BRANCH["customer_address"], BRANCH["state_code"])
            )
            conn.execute(
                """INSERT INTO sbi_invoice_gst.vendor_profiles
                   (vendor_key,legal_name,logo_image,logo_mime,exact_logo_verified,
                    declaration_text,bank_instructions,pan,gstin,vendor_id,
                    service_type,sac_code,footer_text,authorized_signature_label,
                    registered_office,registered_phone,registered_email,
                    head_office,head_phone,website,verified_by,verified_at)
                   VALUES ('MEGHRAJ_EXPRESS','MEGHRAJ EXPRESS',
                           %s,'image/png',TRUE,'QA DECLARATION','QA BANK','QA PAN',
                           'QA GSTIN','QA VENDOR ID','COURIER','QA SAC',
                           'QA FOOTER','QA SIGNATURE',
                           'QA REGISTERED OFFICE, KOLKATA','033 00000000','qa@example.invalid',
                           'QA HEAD OFFICE, KOLKATA','033 00000001','example.invalid',
                           'qa-reviewer',now())""",
                (cls.synthetic_logo,)
            )
        from flask import Flask, g
        from invoice_gst_feature import create_invoice_gst_blueprint
        cls.app = Flask(__name__)
        @cls.app.before_request
        def dummy_identity():
            g.dil_user = SimpleNamespace(uid="synthetic-qa-uid")
        cls.app.register_blueprint(create_invoice_gst_blueprint(
            can_read=lambda: True,
            can_create=lambda: True,
            csrf_valid=lambda: True,
            connection_factory=connect
        ))
        cls.client = cls.app.test_client()
        cls.original_env = {
            key: os.environ.get(key) for key in (
                "SBI_INVOICE_GST_ENABLED", "SBI_INVOICE_GST_FINALIZE_ENABLED",
                "SBI_INVOICE_GST_DEPLOYMENT_MODE"
            )
        }
        os.environ.update({
            "SBI_INVOICE_GST_ENABLED": "1",
            "SBI_INVOICE_GST_FINALIZE_ENABLED": "1",
            "SBI_INVOICE_GST_DEPLOYMENT_MODE": "ISOLATED_QA",
        })

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_01_preview_does_not_write(self):
        response = self.client.post("/api/invoice-gst/preview", json=SOURCE)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["invoice"]["total"], "4532.38")
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoices"
            ).fetchone()["n"], 0)

    def test_02_finalize_atomic_and_duplicate_conflict(self):
        response = self.client.post("/api/invoice-gst/finalize", json=SOURCE)
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertTrue(response.get_json()["database_recorded"])
        duplicate = self.client.post("/api/invoice-gst/finalize", json=SOURCE)
        self.assertEqual(duplicate.status_code, 409, duplicate.get_json())
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoices"
            ).fetchone()["n"], 1)
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoice_lines"
            ).fetchone()["n"], 2)

    def test_03_gst_download_and_immutable_record(self):
        from openpyxl import load_workbook
        result = self.client.get("/api/invoice-gst/gst.xlsx?month=2026-02")
        self.assertEqual(result.status_code, 200, result.get_json() if result.is_json else "")
        wb = load_workbook(BytesIO(result.data), data_only=True)
        sheet = wb.active
        self.assertEqual(tuple(c.value for c in sheet[1]), HEADERS)
        self.assertEqual(sheet["F2"].value, "03970")
        self.assertEqual(sheet["H2"].value, "03970")
        self.assertEqual(sheet["J2"].value, "MXP90001")
        self.assertEqual(sheet["K2"].value, 3841)
        self.assertEqual(sheet["N2"].value, 4532.38)
        with self.connect() as conn:
            with self.assertRaises(self.psycopg.errors.RaiseException):
                conn.execute(
                    "UPDATE sbi_invoice_gst.invoices SET taxable=1 WHERE invoice_no='MXP90001'"
                )

    def test_04_preview_is_readonly_and_auth_enabled_flag_fail_closed(self):
        os.environ["SBI_INVOICE_GST_ENABLED"] = "0"
        try:
            response = self.client.get("/api/invoice-gst/branches")
            self.assertEqual(response.status_code, 503)
        finally:
            os.environ["SBI_INVOICE_GST_ENABLED"] = "1"

    def test_06_native_pdf_uses_logo_vendor_and_annexure(self):
        from pypdf import PdfReader
        result = self.client.get("/api/invoice-gst/invoices/MXP90001.pdf")
        self.assertEqual(result.status_code, 200,
                         result.get_json() if result.is_json else "")
        self.assertEqual(result.mimetype, "application/pdf")
        self.assertTrue(result.data.startswith(b"%PDF-"))
        doc = PdfReader(BytesIO(result.data))
        self.assertGreaterEqual(len(doc.pages), 2)
        invoice_text = doc.pages[0].extract_text()
        self.assertIn("TAX INVOICE", invoice_text)
        self.assertIn("MXP90001", invoice_text)
        self.assertIn("MEGHRAJ EXPRESS", invoice_text)
        self.assertIn("Regd. Off.", invoice_text)
        self.assertIn("QA REGISTERED OFFICE, KOLKATA", invoice_text)
        self.assertIn("Head Off.", invoice_text)
        self.assertIn("QA HEAD OFFICE, KOLKATA", invoice_text)
        self.assertIn("qa@example.invalid", invoice_text)

        annexure_text = "\\n".join(p.extract_text() for p in doc.pages[1:])
        self.assertIn("QA-LR1", annexure_text)
        self.assertIn("QA-LR2", annexure_text)

    def test_08_private_vendor_bundle_qa_database_import(self):
        """Real PostgreSQL QA: checked archive import updates only vendor profile."""
        from importlib.util import module_from_spec, spec_from_file_location
        from tempfile import TemporaryDirectory
        from test_invoice_gst_private_vendor import synthetic_zip
        importer_path = ROOT / "staging/invoice-gst/private_vendor_loader.py"
        spec = spec_from_file_location("qa_vendor_importer", importer_path)
        importer = module_from_spec(spec)
        spec.loader.exec_module(importer)
        with TemporaryDirectory() as directory:
            bundle = synthetic_zip(Path(directory))
            outcome = importer.apply_only_isolated_qa(
                self.dsn, bundle, "qa-verified-reviewer"
            )
            self.assertEqual(outcome["status"], "PRIVATE_VENDOR_QA_PROFILE_LOADED")
            self.assertFalse(outcome["production_write"])
        with self.connect() as conn:
            saved = conn.execute(
                """SELECT legal_name, exact_logo_verified, registered_office,
                          head_office, website, length(logo_image) AS logo_bytes
                   FROM sbi_invoice_gst.vendor_profiles
                   WHERE vendor_key='MEGHRAJ_EXPRESS'"""
            ).fetchone()
        self.assertEqual(saved["legal_name"], "MEGHRAJ EXPRESS")
        self.assertTrue(saved["exact_logo_verified"])
        self.assertEqual(saved["registered_office"], "QA PLACEHOLDER")
        self.assertEqual(saved["head_office"], "QA PLACEHOLDER")
        self.assertGreater(saved["logo_bytes"], 50)

    def test_07_unapproved_logo_denied(self):
        with self.connect() as conn:
            conn.execute(
                """UPDATE sbi_invoice_gst.vendor_profiles
                   SET exact_logo_verified=FALSE
                   WHERE vendor_key='MEGHRAJ_EXPRESS'"""
            )
        try:
            response = self.client.get("/api/invoice-gst/invoices/MXP90001.pdf")
            self.assertEqual(response.status_code, 409)
        finally:
            with self.connect() as conn:
                conn.execute(
                    """UPDATE sbi_invoice_gst.vendor_profiles
                       SET exact_logo_verified=TRUE
                       WHERE vendor_key='MEGHRAJ_EXPRESS'"""
                )

    def test_08_master_import_never_silently_overrides_identity_or_address(self):
        # This test runs against the dedicated isolated invoice_qa database.
        sys.path.insert(0, str(ROOT / "staging/invoice-gst"))
        from load_private_branch_master import stage_approved_master_qa
        valid = {**BRANCH, "verified_by": "qa-reviewer"}
        altered_address = {**valid, "customer_address": "CONFLICTING QA ADDRESS"}
        payload = {"status": "READY_FOR_PRIVATE_QA_IMPORT", "rows": [altered_address]}
        with self.assertRaisesRegex(ValueError, "PREEXISTING_BRANCH_MASTER_CONFLICT"):
            stage_approved_master_qa(self.dsn, payload)
        same_sol_other_key = {**valid, "branch_key": "different-qa-branch"}
        payload["rows"] = [same_sol_other_key]
        with self.assertRaisesRegex(ValueError, "PREEXISTING_SOL_OWNERSHIP_CONFLICT"):
            stage_approved_master_qa(self.dsn, payload)
        with self.connect() as conn:
            count = conn.execute(
                """SELECT count(*) AS n FROM sbi_invoice_gst.verified_branches
                   WHERE sol_id='03970'"""
            ).fetchone()["n"]
            self.assertEqual(count, 1)

    def test_09_database_rejects_duplicate_verified_sol_even_direct_sql(self):
        with self.connect() as conn:
            with self.assertRaises(self.psycopg.errors.UniqueViolation):
                with conn.transaction():
                    conn.execute(
                        """INSERT INTO sbi_invoice_gst.verified_branches
                          (branch_key, client_name, invoice_branch,
                           invoice_generate_location, original_branch_name,
                           sol_id, client_class, gstin, recipient_title,
                           customer_address, state_code, verified,
                           verified_by, verified_at)
                           SELECT 'qa-second-key', client_name || ' OTHER',
                           invoice_branch, invoice_generate_location,
                           original_branch_name, sol_id, client_class,
                           gstin, recipient_title, customer_address,
                           state_code, TRUE, 'qa-reviewer', now()
                           FROM sbi_invoice_gst.verified_branches
                           WHERE branch_key=%s""",
                        (BRANCH["branch_key"],),
                    )
            count = conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.verified_branches "
                "WHERE sol_id='03970'"
            ).fetchone()["n"]
            self.assertEqual(count, 1)

    def test_05_fy_conflict_and_review(self):
        response = self.client.get("/api/invoice-gst/gst.xlsx?month=2026-02&fy=2026-2027")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["error"], "FY_SERVICE_MONTH_CONFLICT")


if __name__ == "__main__":
    unittest.main()
