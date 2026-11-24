"""R20 synthetic-only real XLSX serializer tests."""
import hashlib
import io
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"/"ci"))
from sbi_r19_combined_synthetic_rehearsal import build_synthetic_fixture, workbook_bytes
from sbi_r20_synthetic_review_writer import create_locked_synthetic_review_xlsx
from sbi_r18_output_parity_gate import verify_xlsx_output_structure


def generate(src=None, master=None):
    s,m=build_synthetic_fixture()
    src = src if src is not None else s
    master = master if master is not None else m
    return create_locked_synthetic_review_xlsx(
        src,master,expected_source_sha256=hashlib.sha256(src).hexdigest(),
        expected_master_sha256=hashlib.sha256(master).hexdigest(),
    )


class R20ActualSyntheticXlsxTests(unittest.TestCase):
    def test_01_writer_actually_serializes_real_xlsx_bytes(self):
        out,diag=generate()
        self.assertTrue(out.startswith(b"PK"))
        self.assertEqual(diag["stage"],"R20_SYNTHETIC_REVIEW_XLSX_SERIALIZER")

    def test_02_all_original_sheets_and_original_values_preserved(self):
        src,master=build_synthetic_fixture()
        out,diag=generate(src,master)
        p=verify_xlsx_output_structure(
            src,out,
            expected_source_sha256=hashlib.sha256(src).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(out).hexdigest())
        self.assertTrue(p["original_cells_formulas_number_formats_preserved"])
        self.assertEqual(p["payment_status_counts_structure_only"],{"SUSPENSE":4})

    def test_03_blank_K_and_protected_L_keep_identity(self):
        src,master=build_synthetic_fixture()
        out,_=generate(src,master)
        a=load_workbook(io.BytesIO(src));b=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual(a["PAYMNENT"]["K2"].value,b["PAYMNENT"]["K2"].value)
            self.assertEqual(a["PAYMNENT"]["L2"].value,b["PAYMNENT"]["L2"].value)
            self.assertEqual(a["PAYMNENT"]["J2"].value,b["PAYMNENT"]["J2"].value)
        finally:a.close();b.close()

    def test_04_numeric_S_zero_protection_preserved(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual(w["Invoice Details."]["S3"].value,0)
            self.assertEqual(w["Invoice Details."]["AM3"].value,"SYNTHETIC S NONBLANK — EXCLUDED")
            self.assertIsNone(w["Invoice Details."]["AI3"].value)
        finally:w.close()

    def test_05_typed_sol_leading_zeroes_preserved(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual(w["PAYMNENT"]["V2"].value,"0001")
            self.assertEqual(w["Invoice Details."]["AI2"].value,"0001")
            self.assertEqual(w["PAYMNENT"]["V4"].value,"1")
        finally:w.close()

    def test_06_real_model_column_M_status_only_suspense(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual([w["PAYMNENT"].cell(i,13).value for i in range(2,7)],
                             ["SUSPENSE"]*5)
        finally:w.close()

    def test_07_old_source_K_OK_never_auto_model_OK(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual(w["PAYMNENT"]["K6"].value,"OK")
            self.assertEqual(w["PAYMNENT"]["M6"].value,"SUSPENSE")
        finally:w.close()

    def test_08_writer_does_not_infer_invoice_bank_link(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            for row in (2,3):
                self.assertIsNone(w["Invoice Details."].cell(row,37).value)
                self.assertIsNone(w["Invoice Details."].cell(row,38).value)
        finally:w.close()

    def test_09_no_tds_money_written_without_certified_engine(self):
        out,_=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            for row in range(2,7):
                for col in (18,19,20):
                    self.assertIsNone(w["PAYMNENT"].cell(row,col).value)
        finally:w.close()

    def test_10_diagnostic_not_financial_certification(self):
        out,diag=generate()
        self.assertTrue(diag["financial_apply_locked"])
        self.assertFalse(diag["v251_certified"])
        self.assertFalse(diag["real_v218_writer_verified"])
        self.assertFalse(diag["financial_database_connected"])

    def test_11_original_source_and_master_hashes_unchanged(self):
        src,m=build_synthetic_fixture()
        source_sha=hashlib.sha256(src).hexdigest();master_sha=hashlib.sha256(m).hexdigest()
        generate(src,m)
        self.assertEqual(hashlib.sha256(src).hexdigest(),source_sha)
        self.assertEqual(hashlib.sha256(m).hexdigest(),master_sha)

    def test_12_non_synthetic_real_invoice_refused(self):
        src,m=build_synthetic_fixture()
        w=load_workbook(io.BytesIO(src))
        w["Invoice Details."]["M2"]="MXP19970"
        bad=workbook_bytes(w);w.close()
        with self.assertRaisesRegex(ValueError,"NON_SYNTHETIC_INVOICE_ROW_REFUSED"):
            generate(bad,m)

    def test_13_wrong_expected_master_hash_refused(self):
        src,m=build_synthetic_fixture()
        with self.assertRaisesRegex(ValueError,"MASTER_SHA256_MISMATCH"):
            create_locked_synthetic_review_xlsx(
                src,m,expected_source_sha256=hashlib.sha256(src).hexdigest(),
                expected_master_sha256="0"*64)

    def test_14_review_decisions_never_expose_bank_narrations_in_audit(self):
        _,d=generate()
        for forbidden in ("SYN-PAY-001","SYN-MXP-001","SYNTHETIC ALPHA","1160.00"):
            self.assertNotIn(forbidden,repr(d))

    def test_15_negative_bank_credit_is_not_allocated(self):
        out,d=generate()
        w=load_workbook(io.BytesIO(out))
        try:
            self.assertEqual(w["PAYMNENT"]["M3"].value,"SUSPENSE")
            self.assertEqual(w["PAYMNENT"]["U3"].value,"NONPOSITIVE_CREDIT_REVIEW")
        finally:w.close()


if __name__=="__main__":
    unittest.main()
