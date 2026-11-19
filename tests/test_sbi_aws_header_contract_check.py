"""Synthetic Python-stdlib XLSX extraction against the real 34/35/53 contract."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/sbi_aws_header_contract_check.py"
spec = importlib.util.spec_from_file_location("header_compare", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONTRACT = json.loads((ROOT / "backend_source/invoice_import_contract.json").read_text())
HEADERS53 = CONTRACT["headers"]
HEADERS34 = HEADERS53[:8] + HEADERS53[11:37]
HEADERS35 = HEADERS34[:8] + ["Branch Code"] + HEADERS34[8:]
XML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def letter(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def make_xlsx(path, headers, *, inline=False, sheet_name="Invoice Details."):
    root = ET.Element("{" + XML_NS + "}worksheet")
    data = ET.SubElement(root, "{" + XML_NS + "}sheetData")
    row = ET.SubElement(data, "{" + XML_NS + "}row", r="1")
    for idx, text in enumerate(headers, 1):
        cell = ET.SubElement(
            row, "{" + XML_NS + "}c", r=letter(idx) + "1",
            t="inlineStr" if inline else "s"
        )
        if inline:
            ins = ET.SubElement(cell, "{" + XML_NS + "}is")
            ET.SubElement(ins, "{" + XML_NS + "}t").text = text
        else:
            ET.SubElement(cell, "{" + XML_NS + "}v").text = str(idx - 1)
    workbook = ET.Element("{" + XML_NS + "}workbook")
    sheets = ET.SubElement(workbook, "{" + XML_NS + "}sheets")
    ET.SubElement(sheets, "{" + XML_NS + "}sheet", name=sheet_name, sheetId="1")
    strings = ET.Element("{" + XML_NS + "}sst")
    for header in headers:
        si = ET.SubElement(strings, "{" + XML_NS + "}si")
        ET.SubElement(si, "{" + XML_NS + "}t").text = header
    with ZipFile(path, "w") as output:
        output.writestr("xl/workbook.xml", ET.tostring(workbook))
        output.writestr("xl/worksheets/sheet1.xml", ET.tostring(root))
        output.writestr("xl/sharedStrings.xml", ET.tostring(strings))


class HeaderContractCheckTests(unittest.TestCase):
    def test_real_approved_53_contract_has_duplicates(self):
        self.assertEqual(len(HEADERS53), 53)
        self.assertLess(len(set(HEADERS53)), 53)
        self.assertEqual(len(HEADERS35), 35)
        self.assertEqual(len(HEADERS34), 34)

    def test_import_contract_matches_main_schema(self):
        sha = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, check=True, text=True
        ).stdout.strip()
        contracts = module.load_contract(ROOT, sha)
        self.assertEqual(contracts[53], HEADERS53)
        self.assertEqual(contracts[35], HEADERS35)

    def test_shared_strings_xlsx_35_headers_match_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "contract.xlsx"
            make_xlsx(file, HEADERS35)
            name, actual, stored = module.extract_headers(file)
            self.assertEqual(name, "Invoice Details.")
            self.assertEqual(stored, 35)
            self.assertEqual(actual, HEADERS35)

    def test_inline_strings_xlsx_53_headers_match_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "contract.xlsx"
            make_xlsx(file, HEADERS53, inline=True)
            name, actual, stored = module.extract_headers(file)
            self.assertEqual(stored, 53)
            self.assertEqual(actual, HEADERS53)

    def test_wrong_header_name_not_falsely_approved(self):
        changed = HEADERS35[:]
        changed[12] = changed[12] + " INVALID"
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "contract.xlsx"
            make_xlsx(file, changed)
            name, actual, stored = module.extract_headers(file)
            self.assertNotEqual(actual, HEADERS35)
            self.assertEqual(len(actual), 35)

    def test_header_sequence_digest_is_order_sensitive(self):
        normal = module.canonical_digest(HEADERS35)
        reversed_digest = module.canonical_digest(list(reversed(HEADERS35)))
        self.assertNotEqual(normal, reversed_digest)

    def test_invalid_excel_column_reference_blocked(self):
        with self.assertRaisesRegex(ValueError, "INVALID_EXCEL_CELL_REFERENCE"):
            module.excel_column("A-1")


if __name__ == "__main__":
    unittest.main()
