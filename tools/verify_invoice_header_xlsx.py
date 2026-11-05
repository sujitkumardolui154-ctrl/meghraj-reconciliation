"""Offline, read-only source XLSX header verification; do not upload source files.

Usage:
  python3 tools/verify_invoice_header_xlsx.py /private/path/source.xlsx \
      --expected-sha256 <actual-known-64-hex-hash>

Prints only aggregate outcome, layout and source digest, never source row values.
No cloud, network, imports, database writes, or payment logic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
CONTRACT = Path(__file__).resolve().parents[1] / "backend_source" / "invoice_import_contract.json"
EXPECTED_SHEET = "Invoice Details."
MAX_ZIP_MEMBER = 8 * 1024 * 1024


def _xml(zf, name):
    part = zf.getinfo(name)
    if part.file_size > MAX_ZIP_MEMBER:
        raise ValueError("Workbook XML metadata exceeds safety limit")
    return ET.fromstring(zf.read(part))


def _col_index(cell_reference):
    letters = re.match(r"^[A-Z]+", cell_reference or "")
    if not letters:
        raise ValueError("Invalid source header cell coordinate")
    index = 0
    for ch in letters.group():
        index = index * 26 + ord(ch) - 64
    return index - 1


def _relationship_target(zf, relationship_id):
    rels = _xml(zf, "xl/_rels/workbook.xml.rels")
    for rel in rels.findall("p:Relationship", NS):
        if rel.get("Id") == relationship_id:
            target = rel.get("Target", "")
            if rel.get("TargetMode") == "External":
                raise ValueError("External workbook relationship forbidden")
            if target.startswith("/xl/"):
                target = target[1:]
            elif target.startswith("xl/"):
                pass
            else:
                target = "xl/" + target
            pieces = Path(target).parts
            if ".." in pieces or not target.startswith("xl/"):
                raise ValueError("Invalid worksheet relationship target")
            return target
    raise ValueError("Worksheet relationship missing")


def _shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _xml(zf, "xl/sharedStrings.xml")
    return [
        "".join(n.text or "" for n in item.iter("{%s}t" % NS["m"]))
        for item in root.findall("m:si", NS)
    ]


def source_header(zf):
    workbook = _xml(zf, "xl/workbook.xml")
    worksheets = workbook.findall("m:sheets/m:sheet", NS)
    named = [s for s in worksheets if s.get("name") == EXPECTED_SHEET]
    if len(named) != 1:
        raise ValueError("Approved Invoice Details. worksheet missing or duplicated")
    identifier = named[0].get("{%s}id" % NS["r"])
    path = _relationship_target(zf, identifier)
    root = _xml(zf, path)
    first_row = root.find("m:sheetData/m:row", NS)
    if first_row is None or first_row.get("r") != "1":
        raise ValueError("Source header row 1 is missing")
    strings = _shared_strings(zf)
    result = {}
    for cell in first_row.findall("m:c", NS):
        reference = cell.get("r", "")
        idx = _col_index(reference)
        if idx in result:
            raise ValueError("Duplicate header cell address")
        kind = cell.get("t")
        if kind == "inlineStr":
            value = "".join(x.text or "" for x in cell.iter("{%s}t" % NS["m"]))
        elif kind == "s":
            node = cell.find("m:v", NS)
            if node is None or not (node.text or "").isdigit():
                raise ValueError("Invalid shared string index")
            ix = int(node.text)
            if ix >= len(strings):
                raise ValueError("Shared string index out of range")
            value = strings[ix]
        else:
            node = cell.find("m:v", NS)
            value = node.text if node is not None and node.text is not None else ""
        result[idx] = value
    if not result:
        raise ValueError("Source header cells missing")
    width = max(result) + 1
    if width not in (34, 35, 53) or set(result) != set(range(width)):
        raise ValueError("Source header count or positions invalid")
    return [result[i] for i in range(width)]


def verify(path, expected_sha):
    expected = expected_sha.lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Expected original SHA-256 must be supplied")
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("Original workbook SHA-256 mismatch")
    with ZipFile(path) as zf:
        headers = source_header(zf)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    frozen = contract["headers"]
    original34 = contract["original_source_headers_34"]
    original35 = original34[:8] + ["Branch Code"] + original34[8:]
    choices = {34: original34, 35: original35, 53: frozen}
    if len(headers) not in choices or headers != choices[len(headers)]:
        raise ValueError("Original worksheet header differs from approved contract")
    return {"status": "PASS", "sheet": EXPECTED_SHEET, "columns": len(headers),
            "sha256": digest, "comparison": "EXACT_ORDERED_HEADER_MATCH",
            "financial_values_compared": False, "database_access": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xlsx")
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.source_xlsx, args.expected_sha256), sort_keys=True))
    except (ValueError, KeyError, OSError, ET.ParseError, BadZipFile) as exc:
        # Do not print filenames, invoice headers or raw source values.
        print(json.dumps({"status": "FAIL", "reason": type(exc).__name__,
                          "financial_values_compared": False}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
