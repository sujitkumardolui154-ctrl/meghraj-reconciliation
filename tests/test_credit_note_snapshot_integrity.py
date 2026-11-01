"""Synthetic integrity QA for CREDIT NOTE report counts (no cloud/API access)."""
import csv
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard_source"))
from sbi_credit_report_auth import _validate_snapshot_counts, _verify_conflicts_digest
import hashlib

HEADERS = ["Source Field " + str(i) for i in range(18)]
HEADERS[8] = "Invoice No"
HEADERS[16] = "Payment Received ( If With GST or Excluding GST)"
HEADERS[17] = "Credi note"

ROWS = [
    ("INV-A", "CREDIT NOTE"),
    ("INV-A", ""),
    ("INV-B", "CREDIT NOTE"),
    ("INV-C", ""),
]
MANIFEST = {
    "all_invoice_rows": 4,
    "credit_note_unique_invoices": 2,
    "credit_note_confirmed_unique_invoices": 1,
    "conflicting_duplicate_invoice_numbers": 1,
    "release_status": "REVIEW_REQUIRED",
}


def csv_bytes(rows=ROWS, headers=HEADERS):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    for invoice, marker in rows:
        fields = [""] * 18
        fields[8], fields[17] = invoice, marker
        writer.writerow(fields)
    return output.getvalue().encode("utf-8")


class CreditNoteSnapshotIntegrityTests(unittest.TestCase):
    def test_verified_counts_pass(self):
        self.assertEqual(
            _validate_snapshot_counts(csv_bytes(), MANIFEST),
            {
                "all_invoice_rows": 4,
                "credit_note_unique_invoices": 2,
                "credit_note_confirmed_unique_invoices": 1,
                "conflicting_duplicate_invoice_numbers": 1,
            },
        )

    def test_all_mismatched_counts_fail_closed(self):
        for key in (
            "all_invoice_rows", "credit_note_unique_invoices",
            "credit_note_confirmed_unique_invoices",
            "conflicting_duplicate_invoice_numbers"
        ):
            with self.subTest(key=key):
                forged = {**MANIFEST, key: MANIFEST[key] + 1}
                with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                    _validate_snapshot_counts(csv_bytes(), forged)

    def test_missing_and_boolean_counts_are_rejected(self):
        for field in (
            "all_invoice_rows", "credit_note_unique_invoices",
            "credit_note_confirmed_unique_invoices",
            "conflicting_duplicate_invoice_numbers",
        ):
            with self.subTest(field=field):
                forged = MANIFEST.copy()
                forged[field] = True
                with self.assertRaises(ValueError):
                    _validate_snapshot_counts(csv_bytes(), forged)
                forged.pop(field)
                with self.assertRaises(ValueError):
                    _validate_snapshot_counts(csv_bytes(), forged)

    def test_modified_derived_credit_marker_detected(self):
        tampered = list(ROWS)
        tampered[1] = ("INV-A", "CREDIT NOTE")
        with self.assertRaisesRegex(ValueError, "manifest mismatch"):
            _validate_snapshot_counts(csv_bytes(rows=tampered), MANIFEST)

    def test_unknown_status_marker_rejected(self):
        tampered = list(ROWS)
        tampered[0] = ("INV-A", "CREDIT NORTE")
        with self.assertRaisesRegex(ValueError, "Unknown CREDIT NOTE marker"):
            _validate_snapshot_counts(csv_bytes(rows=tampered), MANIFEST)

    def test_bad_column_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid report header"):
            _validate_snapshot_counts(csv_bytes(headers=HEADERS[:-1]), MANIFEST)

    def test_missing_invoice_header_rejected(self):
        bad_headers = list(HEADERS)
        bad_headers[8] = "Unknown invoice identifier"
        with self.assertRaisesRegex(ValueError, "Invalid report header"):
            _validate_snapshot_counts(csv_bytes(headers=bad_headers), MANIFEST)

    def test_blank_invoice_does_not_invent_identity(self):
        rows = list(ROWS) + [("", "")]
        valid = {**MANIFEST, "all_invoice_rows": 5}
        result = _validate_snapshot_counts(csv_bytes(rows=rows), valid)
        self.assertEqual(result["credit_note_unique_invoices"], 2)

    def test_csv_with_bom_is_readable(self):
        data = b"\xef\xbb\xbf" + csv_bytes()
        self.assertEqual(_validate_snapshot_counts(data, MANIFEST)[
            "conflicting_duplicate_invoice_numbers"], 1)

    def test_conflict_report_digest_required(self):
        raw = b"synthetic,conflict\\r\\n"
        digest = hashlib.sha256(raw).hexdigest()
        _verify_conflicts_digest(raw, {"conflicts_sha256": digest})
        for invalid in (None, "", True, "not-a-sha256", digest.upper(), digest[:-1]):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "missing or invalid"):
                    _verify_conflicts_digest(raw, {"conflicts_sha256": invalid})
        with self.assertRaisesRegex(ValueError, "missing or invalid"):
            _verify_conflicts_digest(raw, {})
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _verify_conflicts_digest(raw + b"tampered", {"conflicts_sha256": digest})

    def test_approval_claim_rejected_for_review_snapshot(self):
        with self.assertRaisesRegex(ValueError, "release classification"):
            _validate_snapshot_counts(
                csv_bytes(), {**MANIFEST, "release_status": "PASSED"}
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
