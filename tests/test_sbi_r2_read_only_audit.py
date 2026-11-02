"""Synthetic SBI R2 checks. No Cloud or customer records are accessed."""
import csv
import hashlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_r2_read_only_audit", ROOT / "tools" / "sbi_r2_read_only_audit.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

HEADERS = json.loads(
    (ROOT / "backend_source" / "invoice_import_contract.json").read_text(encoding="utf-8")
)["headers"]
SOURCE_SHA = "a" * 64
DATASET = SOURCE_SHA + "-report-v1"


def row(number, invoice):
    values = [""] * 53
    values[6], values[12], values[20] = "00123", invoice, ""
    return {"export_values": values, "source_row": number, "source_sha256": SOURCE_SHA}


def csv_report(rows=2):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["field" + str(i) for i in range(18)])
    for _ in range(rows):
        writer.writerow([""] * 18)
    return output.getvalue().encode("utf-8-sig")


def evidence():
    baseline = [row(2, "TEST-1"), row(3, "TEST-2")]
    metadata = {
        "rows": 2, "state": "READY", "source_sha256": SOURCE_SHA,
        "original_headers": HEADERS, "original_column_count": 53,
        "original_columns_row_count": 2,
    }
    data = csv_report()
    manifest = {
        "dataset_id": DATASET, "source_sha256": SOURCE_SHA,
        "baseline_rows": 2, "completed_import_rows": 0,
        "all_invoice_rows": 2, "full_schema_columns": 53,
        "report_columns": 18, "release_status": "READY",
        "report_sha256": hashlib.sha256(data).hexdigest(),
    }
    receipts = {
        "result": "PASS_ZERO_IMPORTS", "completed_import_row_count": 0,
        "blockers": [],
    }
    return baseline, [], metadata, HEADERS, receipts, dict(
        dataset_id=DATASET, report_manifest=manifest,
        report_bytes=data, approved_headers=HEADERS,
    )


class ReadOnlyR2Tests(unittest.TestCase):
    def assess(self, *args, **kwargs):
        return audit.evaluate(*args, **kwargs)

    def test_valid_evidence_is_not_production_approval(self):
        b, i, m, h, r, kwargs = evidence()
        output = self.assess(b, i, m, h, r, **kwargs)
        self.assertEqual(output["result"], "R2_EVIDENCE_COLLECTED_NOT_RELEASE_APPROVAL")
        self.assertFalse(output["production_release_approved"])
        self.assertFalse(output["database_writes"])
        self.assertEqual(output["snapshot_freshness"], "NOT_INDEPENDENTLY_CERTIFIED")
        self.assertEqual(output["total_invoice_rows"], 2)

    def test_missing_manifest_and_header_evidence_rejected(self):
        b, i, m, h, r, kw = evidence()
        kw["report_manifest"] = None
        kw["approved_headers"] = None
        reasons = self.assess(b, i, m, h, r, **kw)["blockers"]
        self.assertIn("PRIVATE_REPORT_MANIFEST_NOT_PROVIDED", reasons)
        self.assertIn("INDEPENDENT_APPROVED_HEADERS_NOT_PROVIDED", reasons)

    def test_duplicate_positional_header_mismatch_rejected(self):
        b, i, m, h, r, kw = evidence()
        kw["approved_headers"] = list(h)
        kw["approved_headers"][10] = "Branch Code corrected"
        self.assertIn("INDEPENDENT_APPROVED_HEADERS_MISMATCH",
                      self.assess(b, i, m, h, r, **kw)["blockers"])

    def test_manifest_count_and_csv_sha_tamper_rejected(self):
        b, i, m, h, r, kw = evidence()
        kw["report_manifest"]["baseline_rows"] = 999
        self.assertIn("PRIVATE_REPORT_MANIFEST_MISMATCH",
                      self.assess(b, i, m, h, r, **kw)["blockers"])
        b, i, m, h, r, kw = evidence()
        kw["report_bytes"] += b"altered"
        self.assertIn("PRIVATE_REPORT_CSV_SHA_MISMATCH",
                      self.assess(b, i, m, h, r, **kw)["blockers"])

    def test_snapshot_csv_row_count_mismatch_rejected(self):
        b, i, m, h, r, kw = evidence()
        kw["report_bytes"] = csv_report(3)
        kw["report_manifest"]["report_sha256"] = hashlib.sha256(kw["report_bytes"]).hexdigest()
        self.assertIn("PRIVATE_REPORT_ROW_COUNT_MISMATCH",
                      self.assess(b, i, m, h, r, **kw)["blockers"])

    def test_baseline_missing_row_rejected(self):
        b, i, m, h, r, kw = evidence()
        self.assertIn("BASELINE_ROW_COUNT_MISMATCH",
                      self.assess(b[:1], i, m, h, r, **kw)["blockers"])

    def test_incomplete_import_proof_rejected(self):
        b, i, m, h, r, kw = evidence()
        i.append({**row(5, "TEST-3"), "import_receipt": "b" * 32})
        r = {"result": "REVIEW_REQUIRED", "completed_import_row_count": 1,
             "blockers": ["NONZERO_IMPORT_ROWSET_IDENTITY_NOT_CERTIFIED"]}
        self.assertIn("IMPORT_LEDGER_NOT_INDEPENDENTLY_CERTIFIED",
                      self.assess(b, i, m, h, r, **kw)["blockers"])

    def test_dataset_changed_during_read_rejected(self):
        b, i, m, h, r, kw = evidence()
        kw["metadata_stable"] = False
        self.assertIn("DATASET_CHANGED_DURING_READ",
                      self.assess(b, i, m, h, r, **kw)["blockers"])

    def test_existing_credit_note_conflict_remains_review(self):
        b, i, m, h, r, kw = evidence()
        b[1]["export_values"][12] = "TEST-1"
        kw["report_manifest"]["release_status"] = "REVIEW_REQUIRED"
        output = self.assess(b, i, m, h, r, **kw)
        self.assertEqual(output["duplicate_invoice_numbers"], 1)
        self.assertIn("CREDIT_NOTE_REPORT_REQUIRES_REVIEW", output["blockers"])

    def test_no_live_read_flag_prevents_cloud_access(self):
        with self.assertRaises(SystemExit) as outcome:
            audit.main([])
        self.assertEqual(outcome.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
