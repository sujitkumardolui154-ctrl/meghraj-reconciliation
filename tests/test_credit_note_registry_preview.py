"""Offline tests for fail-closed certified-registry preview and Error CSV.

No network, no Firebase, no credentials, no financial writes.
"""
import csv
import hashlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))

from credit_note_import_preview import preview_uploaded_credit_notes
from credit_note_import_file import parse_credit_note_upload, error_report_csv
from credit_note_registry_readonly import preview_against_certified_registry


def id_for(s):
    return hashlib.sha256(s.upper().encode("utf-8")).hexdigest()


def record(invoice="MXP1001", cn="MXPCN01", marker="CREDIT NOTE",
           replacement=None):
    r = {"Invoice No": invoice, "Credit Note No": cn,
         "Credit Note Description": marker}
    if replacement is not None:
        r["New Invoice Against Credit Note"] = replacement
    return r


def csv_data(records=None):
    if records is None:
        records = [record()]
    headers = ["Invoice No", "Credit Note No", "Credit Note Description"]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in records:
        writer.writerow([r.get(h, "") for h in headers])
    return output.getvalue().encode("utf-8-sig")


class Snapshot:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class DocRef:
    def __init__(self, db, collection, doc_id):
        self.db = db
        self.collection = collection
        self.id = doc_id

    def get(self, timeout=None):
        self.db.reads += 1
        return Snapshot(self.id, self.db.docs.get((self.collection, self.id)))

    def create(self, *_a, **_kw):
        raise AssertionError("Write attempted")

    def set(self, *_a, **_kw):
        raise AssertionError("Write attempted")

    def update(self, *_a, **_kw):
        raise AssertionError("Write attempted")


class Collection:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def document(self, doc_id):
        return DocRef(self.db, self.name, doc_id)


class FakeDB:
    def __init__(self, certified=False):
        self.docs = {}
        self.reads = 0
        self.writes = 0
        self.partial_reads = False
        if certified:
            self.docs[("dashboard_cn_registry_control_v1", "read_only")] = {
                "state": "CERTIFIED_READ_ONLY",
                "source_verified": True, "backfill_complete": True,
                "invoice_registry_certified": True,
                "credit_note_registry_certified": True,
                "replacement_registry_certified": True,
                "invoice_key_encoding": "SHA256_UPPERCASE",
                "credit_note_key_encoding": "SHA256_UPPERCASE",
                "replacement_key_encoding": "SHA256_UPPERCASE",
                "snapshot_sha256": "a" * 64,
            }

    def collection(self, name):
        return Collection(self, name)

    def get_all(self, refs, timeout=None):
        self.reads += len(refs)
        source = refs[:-1] if self.partial_reads else refs
        return [
            Snapshot(ref.id, self.docs.get((ref.collection, ref.id)))
            for ref in source
        ]

    def add_existing(self, kind, key, field):
        self.docs[(kind, id_for(key))] = {field: key}

    def batch(self):
        raise AssertionError("Write attempted")

    def transaction(self):
        raise AssertionError("Write attempted")


class CertifiedIndexPreviewTests(unittest.TestCase):
    def test_unconfigured_registry_blocks_without_looking_up_empty_index(self):
        db = FakeDB()
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["registry_status"], "BLOCKED")
        self.assertEqual(result["reason"], "REGISTRY_CONTROL_NOT_FOUND")
        self.assertEqual(db.reads, 1)
        self.assertFalse(result["import_ready"])

    def test_uncertified_registry_blocks(self):
        db = FakeDB(certified=True)
        db.docs[("dashboard_cn_registry_control_v1", "read_only")]["backfill_complete"] = False
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["reason"], "REGISTRY_NOT_CERTIFIED")

    def test_certified_match_never_enables_apply(self):
        db = FakeDB(certified=True)
        db.add_existing("dashboard_invoice_keys_v140", "MXP1001", "invoice_no")
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["registry_status"], "CERTIFIED_READ_ONLY")
        self.assertEqual(result["summary"]["error_rows"], 0)
        self.assertFalse(result["import_ready"])
        self.assertFalse(result["database_changed"])

    def test_existing_credit_note_is_error(self):
        db = FakeDB(certified=True)
        db.add_existing("dashboard_invoice_keys_v140", "MXP1001", "invoice_no")
        db.add_existing("dashboard_cn_keys_v1", "MXPCN01", "credit_note_no")
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["summary"]["error_flags"]["CREDIT_NOTE_NUMBER_ALREADY_EXISTS"], 1)

    def test_missing_original_invoice_is_error(self):
        result = preview_against_certified_registry(FakeDB(certified=True), [record()])
        self.assertEqual(result["summary"]["error_flags"]["INVOICE_REFERENCE_NOT_IN_APPROVED_REGISTER"], 1)

    def test_existing_replacement_invoice_is_error(self):
        db = FakeDB(certified=True)
        db.add_existing("dashboard_invoice_keys_v140", "MXP1001", "invoice_no")
        db.add_existing("dashboard_cn_replacement_keys_v1", "MXPNEW01", "replacement_invoice_no")
        result = preview_against_certified_registry(db, [record(replacement="MXPNEW01")])
        self.assertEqual(result["summary"]["error_flags"]["REPLACEMENT_INVOICE_ALREADY_EXISTS"], 1)

    def test_corrupt_index_value_fails_closed(self):
        db = FakeDB(certified=True)
        db.docs[("dashboard_invoice_keys_v140", id_for("MXP1001"))] = {"invoice_no": "MXPDIFFERENT"}
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["reason"], "REGISTRY_VALUE_CONFLICT")
        self.assertEqual(result["registry_status"], "BLOCKED")

    def test_partial_database_response_fails_closed(self):
        db = FakeDB(certified=True)
        db.partial_reads = True
        result = preview_against_certified_registry(db, [record()])
        self.assertEqual(result["reason"], "INCOMPLETE_REGISTRY_READ")
        self.assertFalse(result["import_ready"])

    def test_error_flags_still_available_when_registry_blocked(self):
        db = FakeDB()
        result = preview_against_certified_registry(db, [record(cn="CN-NOT-MXP")])
        self.assertEqual(result["summary"]["error_flags"]["INVALID_CREDIT_NOTE_NO_NON_MXP"], 1)
        self.assertEqual(result["rows"][0]["status"], "ERROR")

    def test_nonerror_rows_marked_review_when_registry_missing(self):
        result = preview_against_certified_registry(FakeDB(), [record()])
        self.assertEqual(result["rows"][0]["status"], "REVIEW_PENDING_REGISTRY")

    def test_existing_invoice_is_reference_not_invoice_import_duplicate(self):
        db = FakeDB(certified=True)
        db.add_existing("dashboard_invoice_keys_v140", "MXP1001", "invoice_no")
        result = preview_against_certified_registry(db, [record()])
        self.assertNotIn("INVOICE_ALREADY_EXISTS", result["summary"]["error_flags"])


class FilePreviewTests(unittest.TestCase):
    def test_utf8_csv_parsed(self):
        parsed = parse_credit_note_upload("credit.csv", csv_data())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["_source_row"], 2)

    def test_blank_rows_preserve_source_row(self):
        raw = csv_data() + b"\r\nMXP1002,MXPCN02,CREDIT NOTE\r\n"
        parsed = parse_credit_note_upload("credit.csv", raw)
        self.assertEqual(parsed[-1]["_source_row"], 4)

    def test_csv_duplicate_identity_header_rejected(self):
        raw = b"Invoice No,Invoice No,Credit Note No,Credit Note Description\r\nMXP1,MXP2,MXPCN1,CREDIT NOTE\r\n"
        with self.assertRaisesRegex(ValueError, "DUPLICATED"):
            parse_credit_note_upload("credit.csv", raw)

    def test_missing_cn_number_header_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISSING_OR_AMBIGUOUS_CREDIT_NOTE_NUMBER"):
            parse_credit_note_upload("credit.csv", b"Invoice No,Credit Note Description\r\nMXP1,CREDIT NOTE\r\n")

    def test_unknown_suffix_rejected(self):
        with self.assertRaisesRegex(ValueError, "MUST_BE_CSV_OR_XLSX"):
            parse_credit_note_upload("credit.zip", b"abc")

    def test_upload_size_bounded(self):
        with self.assertRaisesRegex(ValueError, "OVER_8MIB"):
            parse_credit_note_upload("credit.csv", b"x" * (8 * 1024 * 1024 + 1))

    def test_authorization_before_parsing_or_db_read(self):
        db = FakeDB(certified=True)
        with self.assertRaises(PermissionError):
            preview_uploaded_credit_notes(db, "credit.csv", csv_data(), authenticated=False)
        self.assertEqual(db.reads, 0)

    def test_authorization_must_be_true_boolean(self):
        with self.assertRaises(PermissionError):
            preview_uploaded_credit_notes(FakeDB(), "credit.csv", csv_data(), authenticated="true")

    def test_future_preview_returns_error_csv_without_writes(self):
        db = FakeDB()
        preview, error = preview_uploaded_credit_notes(db, "credit.csv", csv_data(), authenticated=True)
        self.assertEqual(preview["registry_status"], "BLOCKED")
        self.assertEqual(preview["source_rows"], 1)
        self.assertFalse(preview["database_changed"])
        self.assertFalse(preview["import_ready"])
        self.assertIn("REVIEW_PENDING_REGISTRY", error.decode("utf-8-sig"))
        self.assertEqual(db.writes, 0)

    def test_formula_injection_in_error_csv_escaped(self):
        preview = {"rows": [{
            "source_row": 2, "invoice_no": "=HYPERLINK(1,2)",
            "credit_note_no": "MXPCN1", "replacement_invoice_no": "",
            "status": "ERROR", "reasons": ["INVALID_INVOICE_NO_NON_MXP"],
        }]}
        output = error_report_csv(preview).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(output)))
        self.assertTrue(rows[1][1].startswith("'="))

    def test_future_xlsx_parser(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Invoice No", "Credit Note No", "Credit Note Description", ""])
        ws.append(["MXP1001", "MXPCN001", "CREDIT NOTE @ 30/11/2024", None])
        buf = io.BytesIO()
        wb.save(buf)
        parsed = parse_credit_note_upload("future.xlsx", buf.getvalue())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["Credit Note No"], "MXPCN001")
        wb.close()

    def test_excel_formula_rejected(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Invoice No", "Credit Note No", "Credit Note Description"])
        ws.append(["MXP1001", "=SUM(1,2)", "CREDIT NOTE"])
        buf = io.BytesIO()
        wb.save(buf)
        with self.assertRaisesRegex(ValueError, "FORMULA_OR_CELL_ERROR"):
            parse_credit_note_upload("future.xlsx", buf.getvalue())
        wb.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
