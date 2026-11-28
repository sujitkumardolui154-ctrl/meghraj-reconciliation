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
            cancellations_sql = (
                ROOT / "staging/invoice-gst/004_invoice_cancellation_ledger.sql"
            ).read_text()
            conn.execute(cancellations_sql)
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
        from invoice_gst_cancellation import create_invoice_cancellation_blueprint
        cls.app.register_blueprint(create_invoice_cancellation_blueprint(
            can_read=lambda: True,
            can_cancel=lambda: True,
            csrf_valid=lambda: True,
            connection_factory=connect
        ))
        cls.client = cls.app.test_client()
        cls.original_env = {
            key: os.environ.get(key) for key in (
                "SBI_INVOICE_GST_ENABLED", "SBI_INVOICE_GST_FINALIZE_ENABLED",
                "SBI_INVOICE_GST_DEPLOYMENT_MODE",
                "SBI_INVOICE_GST_CANCELLATION_ENABLED"
            )
        }
        os.environ.update({
            "SBI_INVOICE_GST_ENABLED": "1",
            "SBI_INVOICE_GST_FINALIZE_ENABLED": "1",
            "SBI_INVOICE_GST_DEPLOYMENT_MODE": "ISOLATED_QA",
            "SBI_INVOICE_GST_CANCELLATION_ENABLED": "1",
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
        """Only in dedicated invoice_qa: new import + idempotent repeat, no override."""
        from importlib.util import module_from_spec, spec_from_file_location
        from tempfile import TemporaryDirectory
        from test_invoice_gst_private_vendor import synthetic_zip
        from psycopg import sql

        importer_path = ROOT / "staging/invoice-gst/private_vendor_loader.py"
        spec = spec_from_file_location("qa_vendor_importer", importer_path)
        importer = module_from_spec(spec)
        spec.loader.exec_module(importer)

        # Keep existing synthetic invoice PDF fixture intact after testing a
        # first-time importer. No customer, payment or settlement rows touched.
        with self.connect() as conn:
            saved = conn.execute(
                """SELECT * FROM sbi_invoice_gst.vendor_profiles
                   WHERE vendor_key='MEGHRAJ_EXPRESS'"""
            ).fetchone()
            self.assertIsNotNone(saved)
            conn.execute(
                """DELETE FROM sbi_invoice_gst.vendor_profiles
                   WHERE vendor_key='MEGHRAJ_EXPRESS'"""
            )

        try:
            with TemporaryDirectory() as directory:
                bundle = synthetic_zip(Path(directory))
                outcome = importer.apply_only_isolated_qa(
                    self.dsn, bundle, "qa-verified-reviewer"
                )
                self.assertEqual(outcome["status"], "PRIVATE_VENDOR_QA_PROFILE_LOADED")
                self.assertFalse(outcome["production_write"])
                repeat = importer.apply_only_isolated_qa(
                    self.dsn, bundle, "qa-verified-reviewer"
                )
                self.assertEqual(
                    repeat["status"], "PRIVATE_VENDOR_QA_PROFILE_ALREADY_VERIFIED_UNCHANGED"
                )
            with self.connect() as conn:
                imported = conn.execute(
                    """SELECT legal_name, exact_logo_verified, registered_office,
                              head_office, website, length(logo_image) AS logo_bytes
                       FROM sbi_invoice_gst.vendor_profiles
                       WHERE vendor_key='MEGHRAJ_EXPRESS'"""
                ).fetchone()
            self.assertEqual(imported["legal_name"], "MEGHRAJ EXPRESS")
            self.assertTrue(imported["exact_logo_verified"])
            self.assertEqual(imported["registered_office"], "QA PLACEHOLDER")
            self.assertEqual(imported["head_office"], "QA PLACEHOLDER")
            self.assertGreater(imported["logo_bytes"], 50)
        finally:
            # Restore all original columns, not only the logo: other tests
            # verify the original invoice render from the same synthetic vendor.
            with self.connect() as conn:
                conn.execute(
                    """DELETE FROM sbi_invoice_gst.vendor_profiles
                       WHERE vendor_key='MEGHRAJ_EXPRESS'"""
                )
                columns = list(saved.keys())
                stmt = sql.SQL(
                    "INSERT INTO sbi_invoice_gst.vendor_profiles ({}) VALUES ({})"
                ).format(
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.SQL(",").join(sql.Placeholder() for _ in columns),
                )
                conn.execute(stmt, [saved[key] for key in columns])

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

    def test_10_owner_approved_vendor_profile_is_not_silently_overwritten(self):
        import tempfile
        from test_invoice_gst_private_vendor import synthetic_zip
        from private_vendor_loader import apply_only_isolated_qa
        with tempfile.TemporaryDirectory() as folder:
            bundle = synthetic_zip(Path(folder))
            with self.assertRaisesRegex(
                ValueError, "VENDOR_PROFILE_CONFLICT_NEW_OWNER_APPROVAL_REQUIRED"
            ):
                apply_only_isolated_qa(self.dsn, bundle, "qa-reviewer")
        with self.connect() as conn:
            row = conn.execute(
                """SELECT bank_instructions, legal_name
                   FROM sbi_invoice_gst.vendor_profiles
                   WHERE vendor_key='MEGHRAJ_EXPRESS'"""
            ).fetchone()
        self.assertEqual(row["bank_instructions"], "QA BANK")
        self.assertEqual(row["legal_name"], "MEGHRAJ EXPRESS")

    def test_12_isolated_aws_preflight_requires_unique_verified_sol(self):
        from importlib.util import module_from_spec, spec_from_file_location
        source = ROOT / "scripts/sbi_invoice_gst_aws_staging_readiness.py"
        spec = spec_from_file_location("qa_staging_preflight", source)
        preflight = module_from_spec(spec)
        spec.loader.exec_module(preflight)
        previous = os.environ.get("SBI_INVOICE_GST_TEST_DSN")
        os.environ["SBI_INVOICE_GST_TEST_DSN"] = self.dsn
        try:
            snapshot = preflight.database_review()
            self.assertEqual(snapshot["status"], "STAGING_SCHEMA_PRESENT")
            self.assertTrue(snapshot["private_vendor_profile_present"])
            self.assertEqual(snapshot["verified_branch_records"], 1)
            self.assertFalse(snapshot["production_write"])
        finally:
            if previous is None:
                os.environ.pop("SBI_INVOICE_GST_TEST_DSN", None)
            else:
                os.environ["SBI_INVOICE_GST_TEST_DSN"] = previous

    def test_13_void_unused_invoice_number_and_block_reuse(self):
        payload = {
            "invoice_no": "MXP90002", "reason_code": "NUMBER_UNUSED",
            "reason": "Number skipped before invoice issue in QA",
        }
        result = self.client.post("/api/invoice-gst/cancellations", json=payload)
        self.assertEqual(result.status_code, 201, result.get_json())
        self.assertEqual(result.get_json()["cancellation_kind"], "VOID_UNUSED")
        self.assertFalse(result.get_json()["accounting_reversal_performed"])
        duplicate = self.client.post("/api/invoice-gst/cancellations", json=payload)
        self.assertEqual(duplicate.status_code, 409, duplicate.get_json())
        attempted = deepcopy(SOURCE)
        attempted["invoice_no"] = "MXP90002"
        preview = self.client.post("/api/invoice-gst/preview", json=attempted)
        self.assertEqual(preview.status_code, 409, preview.get_json())
        self.assertEqual(preview.get_json()["error"], "CANCELLED_INVOICE_NUMBER_CANNOT_BE_REUSED")
        response = self.client.post("/api/invoice-gst/finalize", json=attempted)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(response.get_json()["error"], "CANCELLED_INVOICE_NUMBER_CANNOT_BE_REUSED")
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoices WHERE invoice_no='MXP90002'"
            ).fetchone()["n"], 0)
            with self.assertRaises(self.psycopg.errors.RaiseException):
                with conn.transaction():
                    conn.execute(
                        "DELETE FROM sbi_invoice_gst.invoice_number_cancellations "
                        "WHERE invoice_no='MXP90002'"
                    )

    def test_14_cancel_finalized_invoice_with_review_and_gst_exclusion(self):
        incomplete = {
            "invoice_no": "MXP90001", "reason_code": "ENTRY_ERROR",
            "reason": "Incorrect original invoice entry needs cancellation",
        }
        denied = self.client.post("/api/invoice-gst/cancellations", json=incomplete)
        self.assertEqual(denied.status_code, 422, denied.get_json())
        self.assertEqual(denied.get_json()["error"], "FINALIZED_INVOICE_REVIEW_REFERENCE_REQUIRED")
        incomplete["review_reference"] = "QA-APPROVAL-001"
        denied = self.client.post("/api/invoice-gst/cancellations", json=incomplete)
        self.assertEqual(denied.status_code, 422, denied.get_json())
        incomplete["accounting_review_confirmed"] = True
        approved = self.client.post("/api/invoice-gst/cancellations", json=incomplete)
        self.assertEqual(approved.status_code, 201, approved.get_json())
        self.assertEqual(approved.get_json()["cancellation_kind"], "CANCEL_FINALIZED")
        self.assertTrue(approved.get_json()["audit_logged"])
        self.assertFalse(approved.get_json()["reconciliation_applied"])
        lookup = self.client.get("/api/invoice-gst/invoices/MXP90001")
        self.assertEqual(lookup.get_json()["invoice"]["status"], "CANCELLED")
        pdf = self.client.get("/api/invoice-gst/invoices/MXP90001.pdf")
        self.assertEqual(pdf.status_code, 409, pdf.get_json())
        self.assertEqual(pdf.get_json()["error"], "CANCELLED_INVOICE_PDF_NOT_ACTIVE")
        report = self.client.get("/api/invoice-gst/gst.xlsx?month=2026-02")
        self.assertEqual(report.status_code, 200)
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(report.data), data_only=True)
        self.assertEqual(wb.active.max_row, 1)
        self.assertEqual(tuple(c.value for c in wb.active[1]), HEADERS)
        register = self.client.get("/api/invoice-gst/cancellations?invoice_no=MXP90001")
        self.assertEqual(register.status_code, 200)
        self.assertEqual(register.get_json()["count"], 1)
        self.assertEqual(register.get_json()["records"][0]["review_reference"], "QA-APPROVAL-001")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoice_lines "
                "WHERE invoice_no='MXP90001'"
            ).fetchone()["n"]
            self.assertEqual(rows, 2)
            with self.assertRaises(self.psycopg.errors.RaiseException):
                with conn.transaction():
                    conn.execute(
                        "UPDATE sbi_invoice_gst.invoice_number_cancellations "
                        "SET reason_text='Changed without audit' WHERE invoice_no='MXP90001'"
                    )

    def test_15_cancellation_flag_and_live_mode_are_locked(self):
        initial = {
            "invoice_no": "MXP90003", "reason_code": "NUMBER_UNUSED",
            "reason": "Skipped invoice sequence number for QA",
        }
        os.environ["SBI_INVOICE_GST_CANCELLATION_ENABLED"] = "0"
        try:
            denied = self.client.post("/api/invoice-gst/cancellations", json=initial)
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.get_json()["error"], "INVOICE_CANCELLATION_LOCKED")
        finally:
            os.environ["SBI_INVOICE_GST_CANCELLATION_ENABLED"] = "1"
        os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"] = "APPROVED_LIVE"
        try:
            denied = self.client.post("/api/invoice-gst/cancellations", json=initial)
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(
                denied.get_json()["error"],
                "LIVE_CANCELLATION_REQUIRES_EXTERNAL_LEDGER_INTEGRATION",
            )
        finally:
            os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"] = "ISOLATED_QA"
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoice_number_cancellations "
                "WHERE invoice_no='MXP90003'"
            ).fetchone()["n"], 0)

    def test_16_cancellation_needs_separate_permission_and_csrf(self):
        from flask import Flask, g
        from invoice_gst_cancellation import create_invoice_cancellation_blueprint
        request_payload = {
            "invoice_no": "MXP90004", "reason_code": "NUMBER_UNUSED",
            "reason": "Cancelled unused invoice number in QA",
        }
        def app_with_access(can_cancel, csrf_valid):
            app = Flask(__name__)
            @app.before_request
            def set_identity():
                g.dil_user = SimpleNamespace(uid="synthetic-qa-uid")
            app.register_blueprint(create_invoice_cancellation_blueprint(
                can_read=lambda: True, can_cancel=can_cancel,
                csrf_valid=csrf_valid, connection_factory=self.connect,
            ))
            return app.test_client()
        client = app_with_access(lambda: False, lambda: True)
        result = client.post("/api/invoice-gst/cancellations", json=request_payload)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.get_json()["error"], "INVOICE_CANCELLER_PERMISSION_REQUIRED")
        client = app_with_access(lambda: True, lambda: False)
        result = client.post("/api/invoice-gst/cancellations", json=request_payload)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.get_json()["error"], "CSRF_VERIFICATION_FAILED")
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoice_number_cancellations "
                "WHERE invoice_no='MXP90004'"
            ).fetchone()["n"], 0)

    def test_05_fy_conflict_and_review(self):
        response = self.client.get("/api/invoice-gst/gst.xlsx?month=2026-02&fy=2026-2027")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["error"], "FY_SERVICE_MONTH_CONFLICT")


    def test_17_verified_branch_lookup_by_sol_and_name(self):
        for query in ("03970", "SAMPLE VERIFIED"):
            response=self.client.get("/api/invoice-gst/branches?search="+
                                     query.replace(" ","%20"))
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertTrue(any(row["branch_key"]==BRANCH["branch_key"]
                                for row in response.get_json()["branches"]))
        absent=self.client.get("/api/invoice-gst/branches?search=999999")
        self.assertEqual(absent.status_code,200)
        self.assertEqual(absent.get_json()["count"],0)

    def test_18_xlsx_awb_upload_is_readonly_and_formulas_denied(self):
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active
        ws.append(["Dispatch Date","AWB No","Packet Ref No",
                   "Consignee","Weight (kg)","Amount ₹"])
        ws.append(["01/09/2026","QA-AWB5","","QA CONSIGNEE",0.250,150])
        raw=BytesIO();wb.save(raw);wb.close()
        response=self.client.post("/api/invoice-gst/annexure/parse",
            data={"file":(BytesIO(raw.getvalue()),"qa_annexure.xlsx")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()["shipments"][0]["lr_no"],"QA-AWB5")
        self.assertFalse(response.get_json()["persisted"])
        self.assertFalse(response.get_json()["financial_writes"])
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM sbi_invoice_gst.invoice_lines "
                "WHERE lr_no='QA-AWB5'"
            ).fetchone()["n"],0)
        wb=Workbook();ws=wb.active
        ws.append(["Dispatch Date","AWB No","Packet Ref No",
                   "Consignee","Weight (kg)","Amount ₹"])
        ws.append(["01/09/2026","QA-AWB6","","QA CONSIGNEE",0.250,"=1+2"])
        raw=BytesIO();wb.save(raw);wb.close()
        denied=self.client.post("/api/invoice-gst/annexure/parse",
            data={"file":(BytesIO(raw.getvalue()),"qa_formula.xlsx")},
            content_type="multipart/form-data")
        self.assertEqual(denied.status_code,422,denied.get_json())
        self.assertEqual(denied.get_json()["error"],"EXCEL_FORMULA_OR_ERROR_NOT_ALLOWED")

    def test_19_multimonth_preview_finalize_isolated_only(self):
        data=deepcopy(SOURCE)
        data["invoice_no"]="MXP90070"
        data["service_from"]="2026-09-01"
        data["service_to"]="2026-10-31"
        data["invoice_date"]="2026-11-05"
        data["shipments"][0]["dispatch_date"]="2026-09-01"
        data["shipments"][1]["dispatch_date"]="2026-10-31"
        data["shipments"][0]["packet_ref_no"]="UI-V2-EDIT"
        data["shipments"][1]["consignee"]="QA EDITED USER CONSIGNEE"
        data["shipments"][1]["amount"]="75.00"
        self.__class__.multimonth_source=data
        preview=self.client.post("/api/invoice-gst/preview",json=data)
        self.assertEqual(preview.status_code,200,preview.get_json())
        self.assertEqual(preview.get_json()["invoice"]["service_month"],
                         "Sept To Oct 2026")
        self.assertEqual(preview.get_json()["invoice"]["taxable"],"1075.00")
        issued=self.client.post("/api/invoice-gst/finalize",json=data)
        self.assertEqual(issued.status_code,201,issued.get_json())
        self.assertEqual(issued.get_json()["shipment_count"],2)
        for month in ("2026-09","2026-10"):
            # Until accountants approve period allocation, neither month can
            # silently omit or double-count this multi-month invoice.
            gst=self.client.get("/api/invoice-gst/gst.xlsx?month="+month)
            self.assertEqual(gst.status_code,409,gst.get_json())
            self.assertEqual(gst.get_json()["error"],
                "MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING")

    def test_20_full_invoice_reload_is_immutable(self):
        r=self.client.get(
            "/api/invoice-gst/invoices/MXP90070?include_lines=1"
        )
        self.assertEqual(r.status_code,200,r.get_json())
        self.assertTrue(r.get_json()["original_immutable"])
        self.assertTrue(r.get_json()["correction_requires_separate_approval"])
        invoice=r.get_json()["invoice"];rows=r.get_json()["shipments"]
        self.assertEqual(invoice["service_month"],"Sept To Oct 2026")
        self.assertEqual(invoice["service_from"],"2026-09-01")
        self.assertEqual(invoice["service_to"],"2026-10-31")
        self.assertEqual(invoice["branch_key"],BRANCH["branch_key"])
        self.assertEqual(len(rows),invoice["shipment_count"])
        self.assertEqual(rows[0]["packet_ref_no"],"UI-V2-EDIT")
        self.assertEqual(rows[1]["consignee"],"QA EDITED USER CONSIGNEE")
        self.assertEqual(rows[1]["amount"],"75.00")
        with self.connect() as conn:
            with self.assertRaises(self.psycopg.errors.RaiseException):
                conn.execute("UPDATE sbi_invoice_gst.invoice_lines "
                             "SET amount=1 WHERE invoice_no='MXP90070'")

    def test_21_correction_draft_can_preview_never_finalize(self):
        copy=deepcopy(self.multimonth_source)
        copy["invoice_no"]="MXP90071"
        copy["replaces_invoice_no"]="MXP90070"
        response=self.client.post("/api/invoice-gst/preview",json=copy)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertTrue(response.get_json()["invoice"]["correction_review_only"])
        self.assertEqual(response.get_json()["invoice"]["correction_source_invoice_no"],
                         "MXP90070")
        denied=self.client.post("/api/invoice-gst/finalize",json=copy)
        self.assertEqual(denied.status_code,403,denied.get_json())
        self.assertEqual(denied.get_json()["error"],
                         "CORRECTION_REQUIRES_APPROVED_REVISION_WORKFLOW")
        missing=deepcopy(copy);missing["replaces_invoice_no"]="MXP999999"
        failed=self.client.post("/api/invoice-gst/preview",json=missing)
        self.assertEqual(failed.status_code,409,failed.get_json())
        with self.connect() as conn:
            n=conn.execute("SELECT count(*) AS n FROM sbi_invoice_gst.invoices "
                           "WHERE invoice_no='MXP90071'").fetchone()["n"]
        self.assertEqual(n,0)

    def test_22_live_multimonth_finalization_remains_blocked(self):
        data=deepcopy(self.multimonth_source)
        data["invoice_no"]="MXP90072"
        original=os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"]
        try:
            os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"]="APPROVED_LIVE"
            denied=self.client.post("/api/invoice-gst/finalize",json=data)
            self.assertEqual(denied.status_code,403,denied.get_json())
            self.assertEqual(denied.get_json()["error"],
                             "INVOICE_UI_V2_PRODUCTION_FINALIZATION_LOCKED")
            one_month=deepcopy(SOURCE)
            one_month["invoice_no"]="MXP90073"
            denied_single=self.client.post("/api/invoice-gst/finalize",json=one_month)
            self.assertEqual(denied_single.status_code,403,denied_single.get_json())
            self.assertEqual(denied_single.get_json()["error"],
                             "INVOICE_UI_V2_PRODUCTION_FINALIZATION_LOCKED")
        finally:
            os.environ["SBI_INVOICE_GST_DEPLOYMENT_MODE"]=original

    def test_23_annexure_upload_requires_creator_and_csrf(self):
        from flask import Flask, g
        from invoice_gst_feature import create_invoice_gst_blueprint
        def check_client(can_create,csrf):
            app=Flask(__name__)
            @app.before_request
            def identity():
                g.dil_user=SimpleNamespace(uid="synthetic-qa-uid")
            app.register_blueprint(create_invoice_gst_blueprint(
                can_read=lambda:True,can_create=can_create,
                csrf_valid=csrf,connection_factory=self.connect
            ))
            return app.test_client()
        unauth=check_client(lambda:False,lambda:True).post(
            "/api/invoice-gst/annexure/parse",data={})
        self.assertEqual(unauth.status_code,403)
        self.assertEqual(unauth.get_json()["error"],"INVOICE_CREATOR_PERMISSION_REQUIRED")
        no_csrf=check_client(lambda:True,lambda:False).post(
            "/api/invoice-gst/annexure/parse",data={})
        self.assertEqual(no_csrf.status_code,403)
        self.assertEqual(no_csrf.get_json()["error"],"CSRF_VERIFICATION_FAILED")


if __name__ == "__main__":
    unittest.main()
