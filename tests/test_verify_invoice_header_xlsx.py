"""Synthetic XLSX fixtures: verify header fingerprint and worksheet without financial rows."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "invoice_header_verifier", ROOT / "tools" / "verify_invoice_header_xlsx.py"
)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

CONTRACT = json.loads(
    (ROOT / "backend_source" / "invoice_import_contract.json").read_text()
)


def column_label(index):
    output = ""
    while index:
        index, rem = divmod(index - 1, 26)
        output = chr(65 + rem) + output
    return output


def make_synthetic_xlsx(path, headers, sheet="Invoice Details.", shuffle=False,
                        duplicate_address=False):
    cells = [
        '<c r="%s1" t="inlineStr"><is><t>%s</t></is></c>' %
        (column_label(i), escape(value))
        for i, value in enumerate(headers, start=1)
    ]
    if shuffle:
        cells[0], cells[1] = cells[1], cells[0]
    if duplicate_address:
        cells.append(cells[0])
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
    ) % escape(sheet)
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    worksheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1">%s</row></sheetData></worksheet>'
    ) % "".join(cells)
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OfflineHeaderVerifierTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.path = Path(self.work.name) / "synthetic.xlsx"
        self.h34 = CONTRACT["original_source_headers_34"]
        self.h35 = self.h34[:8] + ["Branch Code"] + self.h34[8:]
        self.h53 = CONTRACT["headers"]

    def test_all_approved_widths(self):
        for headers in (self.h34, self.h35, self.h53):
            with self.subTest(width=len(headers)):
                digest = make_synthetic_xlsx(self.path, headers)
                result = VERIFIER.verify(self.path, digest)
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["columns"], len(headers))
                self.assertFalse(result["financial_values_compared"])
                self.assertFalse(result["database_access"])

    def test_modified_header_rejected(self):
        headers = self.h35.copy()
        headers[8] = "Branch Code Modified"
        digest = make_synthetic_xlsx(self.path, headers)
        with self.assertRaisesRegex(ValueError, "differs"):
            VERIFIER.verify(self.path, digest)

    def test_unapproved_worksheet_rejected(self):
        digest = make_synthetic_xlsx(self.path, self.h34, sheet="Sheet1")
        with self.assertRaisesRegex(ValueError, "worksheet"):
            VERIFIER.verify(self.path, digest)

    def test_digest_mismatch_rejected_before_workbook_parse(self):
        make_synthetic_xlsx(self.path, self.h34)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            VERIFIER.verify(self.path, "0" * 64)

    def test_duplicate_header_cell_reference_rejected(self):
        digest = make_synthetic_xlsx(self.path, self.h34, duplicate_address=True)
        with self.assertRaisesRegex(ValueError, "Duplicate header cell"):
            VERIFIER.verify(self.path, digest)

    def test_xml_cell_order_does_not_change_column_positions(self):
        digest = make_synthetic_xlsx(self.path, self.h34, shuffle=True)
        self.assertEqual(VERIFIER.verify(self.path, digest)["status"], "PASS")

    def test_missing_real_worksheet_never_approved(self):
        digest = make_synthetic_xlsx(self.path, self.h34, sheet="Invoice Details")
        with self.assertRaises(ValueError):
            VERIFIER.verify(self.path, digest)


if __name__ == "__main__":
    unittest.main()
