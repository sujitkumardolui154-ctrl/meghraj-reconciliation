"""Synthetic workbook tests for real four-tab SBI master source layout."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

TARGET = Path(__file__).resolve().parents[1] / "staging/invoice-gst/master_workbook_gate.py"
spec = spec_from_file_location("sbi_master_workbook_gate", TARGET)
gate = module_from_spec(spec)
spec.loader.exec_module(gate)


def make_source(path, *, official_count=2):
    book = Workbook()
    sheet = book.active
    sheet.title = "Clean Branch Master"
    sheet.append([
        "Search Aliases","Official Branch Name","Column1",
        "Matched Branch Name(s) from Arranged Data","SOL ID",
        "Billing Location (Most Frequent)","Search Aliases2",
        "Billing Location Frequency Evidence","District","State",
        "Pincode","Address","Billing Location Selection Status","Review Flag"
    ])
    sheet.append([
        "QA BRANCH A","QA VERIFIED BRANCH A",None,"QA VERIFIED BRANCH A",
        "00001","KOLKATA",None,None,"KOLKATA","WEST BENGAL",
        "700001","QA POSTAL ADDRESS","Highest frequency selected","OK"
    ])
    sheet.append([
        "QA BRANCH B","QA VERIFIED BRANCH B",None,None,
        "00002",None,None,None,"KOLKATA","WEST BENGAL",
        "700002",None,"No billing location found",
        "BILLING LOCATION NOT FOUND; NO ALTERNATE ALIAS"
    ])
    sheet.append(["SUPPLEMENT","SUPPLEMENTAL UNVERIFIED",None,None,
                  "00003",None,None,None,None,None,None,None,None,None])
    book.create_sheet("Sheet1")
    book.create_sheet("Name Match Audit")
    summary = book.create_sheet("Review Summary")
    summary.append(["SBI SOL Branch Name Matching - Working Review",None,None])
    summary.append(["Assessment Item","Result","Interpretation / Handling"])
    summary.append(["Canonical master rows",official_count,"Only canonical records"])
    summary.append(["Production status","WORKING REVIEW — NOT FINAL","Require QA"])
    book.save(path)


class PrivateMasterWorkbookGateTests(unittest.TestCase):
    def test_approved_candidate_selection_excludes_review_appendix(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "SBI_SOL_Branch_Master_FINAL.xlsx"
            make_source(source)
            result = gate.inspect_private_workbook(source)
            self.assertEqual(result["canonical_count"],2)
            self.assertEqual(result["canonical_candidates"],2)
            self.assertEqual(result["supplemental_review_rows_excluded"],1)
            self.assertFalse(result["automatic_database_write"])
            self.assertEqual(result["source_status"],
                             "WORKING_REVIEW_NOT_APPROVED_FOR_AUTOMATIC_IMPORT")
            self.assertEqual(result["issue_counts"]["CANONICAL_ADDRESS_MISSING"],1)
            self.assertEqual(result["issue_counts"]["INVOICE_GENERATION_LOCATION_NOT_PROVEN"],1)
            public = gate.safe_audit_summary(result)
            self.assertNotIn("candidates", public)
            self.assertNotIn("issues", public)

    def test_verified_source_digest_private_canonical_export_only(self):
        import csv
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "SBI_SOL_Branch_Master_FINAL.xlsx"
            make_source(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            export = Path(directory) / "private_canonical.csv"
            result = gate.export_private_canonical_csv(
                source, export, expected_source_sha=digest
            )
            self.assertEqual(result["canonical_candidate_rows_exported"],2)
            self.assertEqual(result["supplemental_review_rows_excluded"],1)
            with export.open(encoding="utf-8",newline="") as stream:
                records=list(csv.DictReader(stream))
            self.assertEqual(len(records),2)
            self.assertEqual(records[0]["SOL ID"],"00001")
            self.assertNotIn("SUPPLEMENTAL UNVERIFIED",
                             str(records))
            with self.assertRaisesRegex(gate.MasterReviewError,
                                         "SOURCE_WORKBOOK_DIGEST_MISMATCH"):
                gate.export_private_canonical_csv(
                    source, Path(directory)/"wrong.csv",
                    expected_source_sha="0"*64
                )

    def test_canonical_count_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "SBI_SOL_Branch_Master_FINAL.xlsx"
            make_source(source,official_count=5)
            with self.assertRaisesRegex(gate.MasterReviewError,
                                       "CANONICAL_ROW_COUNT_SHORT"):
                gate.inspect_private_workbook(source)

    def test_missing_review_summary_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "SBI_SOL_Branch_Master_FINAL.xlsx"
            make_source(source)
            from openpyxl import load_workbook
            b = load_workbook(source)
            del b["Review Summary"]
            b.save(source)
            with self.assertRaisesRegex(gate.MasterReviewError,
                                       "REVIEW_SUMMARY_SHEET_MISSING"):
                gate.inspect_private_workbook(source)

if __name__=="__main__":
    unittest.main()
