"""Offline CSV bundle tests; only synthetic source rows are used."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_approved_report_bundle", ROOT / "tools" / "sbi_approved_report_bundle.py"
)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class ApprovedReportBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "private"
        self.source.mkdir()
        rows = [["Invoice No", "Paid", "Branch Code"],
                ["TEST-001", "100", "00123"], ["TEST-002", "0", "00234"]]
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerows(rows)
        self.data = output.getvalue().encode("utf-8-sig")
        (self.source / "unpaid.csv").write_bytes(self.data)
        self.item = {
            "report_id": "unpaid", "source_path": "unpaid.csv",
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "headers": rows[0], "expected_rows": 2,
            "approval_state": "APPROVED", "approval_reference": "SYNTHETIC_TEST_SIGNOFF",
        }
        self.manifest = {
            "manifest_version": 1, "source_dataset_sha256": "a" * 64,
            "reports": [self.item],
        }

    def output(self, name="test_bundle.zip"):
        return self.root / name

    def assert_blocked(self, expected):
        with self.assertRaises(bundle.ReportBundleBlocked) as ctx:
            bundle.make_bundle(self.manifest, self.source, self.output())
        self.assertEqual(str(ctx.exception), expected)
        self.assertFalse(self.output().exists())

    def test_synthetic_bundle_is_byte_exact_and_deterministic(self):
        first = bundle.make_bundle(self.manifest, self.source, self.output())
        second = bundle.make_bundle(self.manifest, self.source, self.output("second.zip"))
        self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])
        self.assertEqual(first["status"], "OFFLINE_BUNDLE_PREPARED_REVIEW_REQUIRED")
        self.assertEqual(first["financial_writes"], 0)
        self.assertEqual(first["financial_release"], "RESTRICTED")
        with ZipFile(self.output()) as archive:
            self.assertEqual(archive.namelist(), ["unpaid.csv", "manifest.json"])
            self.assertEqual(archive.read("unpaid.csv"), self.data)
            meta = json.loads(archive.read("manifest.json"))
            self.assertFalse(meta["reports"][0]["approval_independently_verified"])
            self.assertFalse(meta["financial_production_release"])
            self.assertEqual(meta["reports"][0]["approved_header_order"], self.item["headers"])

    def test_source_sha_tamper_rejected(self):
        self.item["sha256"] = "b" * 64
        self.assert_blocked("SOURCE_REPORT_SHA256_MISMATCH")

    def test_approval_missing_rejected(self):
        self.item["approval_state"] = "PENDING"
        self.assert_blocked("APPROVAL_EVIDENCE_MISSING")

    def test_header_mismatch_rejected(self):
        self.item["headers"][0] = "Wrong"
        self.assert_blocked("APPROVED_HEADER_MISMATCH")

    def test_row_count_mismatch_rejected(self):
        self.item["expected_rows"] = 50
        self.assert_blocked("REPORT_ROW_COUNT_MISMATCH")

    def test_parent_traversal_rejected(self):
        self.item["source_path"] = "../outside.csv"
        self.assert_blocked("UNSAFE_REPORT_PATH")

    def test_unknown_report_id_rejected(self):
        self.item["report_id"] = "fake_paid"
        self.assert_blocked("UNAPPROVED_REPORT_TYPE")

    def test_duplicate_category_rejected(self):
        self.manifest["reports"].append(dict(self.item))
        self.assert_blocked("DUPLICATE_REPORT_TYPE")

    def test_existing_output_not_overwritten(self):
        dest = self.output()
        dest.write_text("preserve me", encoding="utf-8")
        with self.assertRaises(bundle.ReportBundleBlocked):
            bundle.make_bundle(self.manifest, self.source, dest)
        self.assertEqual(dest.read_text(encoding="utf-8"), "preserve me")

    def test_broken_csv_width_rejected(self):
        rows = "a,b\none,two,three\n".encode()
        self.source.joinpath("unpaid.csv").write_bytes(rows)
        self.item["sha256"] = hashlib.sha256(rows).hexdigest()
        self.item["headers"] = ["a", "b"]
        self.item["expected_rows"] = 1
        self.assert_blocked("ROW_WIDTH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
