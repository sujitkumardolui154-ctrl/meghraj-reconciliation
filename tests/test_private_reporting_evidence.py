"""Synthetic checks for private-report preflight; never upload actual invoice rows."""
import csv
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from collect_private_reporting_evidence import verify

class EvidenceTests(unittest.TestCase):
    def test_missing_sources_are_never_release_approval(self):
        result = verify()
        self.assertEqual(result["result"], "REVIEW_REQUIRED")
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["deployment_authorized"])
        self.assertEqual(len(result["blockers"]), 5)

    def test_forged_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            header=[""]*18
            header[8]="Invoice No"
            header[16]="Payment Received (If With GST or Excluding GST)"
            header[17]="Credi note"
            out=io.StringIO(newline="")
            writer=csv.writer(out)
            writer.writerow(header)
            writer.writerow([""]*8+["TEST-ID"]+[""]*8+["CREDIT NOTE"])
            report=root/"report.csv"
            report.write_bytes(out.getvalue().encode("utf-8"))
            manifest=root/"manifest.json"
            good={"report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                  "release_status":"REVIEW_REQUIRED", "all_invoice_rows":1,
                  "credit_note_unique_invoices":1,
                  "credit_note_confirmed_unique_invoices":1,
                  "conflicting_duplicate_invoice_numbers":0}
            manifest.write_text(json.dumps(good))
            valid=verify(report=str(report),manifest=str(manifest))
            self.assertEqual(valid["checks"]["PRIVATE_REPORT_HASH_STRUCTURE_COUNTS"],"PASS")
            self.assertFalse(valid["release_approved"])
            good["all_invoice_rows"]=2
            manifest.write_text(json.dumps(good))
            invalid=verify(report=str(report),manifest=str(manifest))
            self.assertEqual(invalid["checks"]["PRIVATE_REPORT_HASH_STRUCTURE_COUNTS"],"PENDING")
            self.assertFalse(invalid["deployment_authorized"])

    def test_unrelated_header_cannot_self_certify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            headers=["h"+str(i) for i in range(53)]
            (root/"contract.json").write_text(json.dumps({"headers":headers}))
            (root/"approved.json").write_text(json.dumps(headers[:-1]+["altered"]))
            result=verify(headers=str(root/"approved.json"),contract=str(root/"contract.json"))
            self.assertEqual(result["checks"]["INDEPENDENT_53_HEADERS"],"PENDING")

if __name__ == "__main__":
    unittest.main()
