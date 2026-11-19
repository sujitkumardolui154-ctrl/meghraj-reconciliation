#!/usr/bin/env python3
"""Verify AWS private header workbook against the Git-pinned 34/35/53 contracts.

Python stdlib only. Reads header row of a local XLSX without printing
customer values or editing any file. Does not certify financial records.
Usage:
  git show "$SHA:tools/sbi_aws_header_contract_check.py" |
    python3 - "$SHA" "/home/ubuntu/sbi-private-evidence/heder sbi.xlsx"
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = "{" + SHEET_NS + "}"
MAIN_CONTRACT = "backend_source/invoice_import_contract.json"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical_digest(headers):
    return sha(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def excel_column(ref):
    prefix = re.match(r"^([A-Z]{1,3})[1-9][0-9]*$", ref)
    if not prefix:
        raise ValueError("INVALID_EXCEL_CELL_REFERENCE")
    number = 0
    for char in prefix.group(1):
        number = number * 26 + ord(char) - 64
    return number - 1


def text_from_si(node):
    pieces = []
    for child in node:
        if child.tag == NS + "t":
            pieces.append(child.text or "")
        elif child.tag == NS + "r":
            pieces.extend(t.text or "" for t in child.findall(NS + "t"))
    return "".join(pieces)


def cell_text(cell, shared):
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        inline = cell.find(NS + "is")
        return text_from_si(inline) if inline is not None else ""
    value = cell.find(NS + "v")
    if value is None:
        return ""
    if kind == "s":
        index = int(value.text or "-1")
        if index < 0 or index >= len(shared):
            raise ValueError("SHARED_STRING_INDEX_INVALID")
        return shared[index]
    return value.text or ""


def extract_headers(source):
    with ZipFile(source) as book:
        # The historical workbook has one stored sheet1 XML and two XML rows.
        # Verify the workbook's first sheet rather than making assumptions
        # from a raw count of <c> tags.
        names = book.namelist()
        if "xl/workbook.xml" not in names:
            raise ValueError("WORKBOOK_XML_MISSING")
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        sheet_names = [
            el.attrib.get("name", "")
            for el in workbook.findall(".//" + NS + "sheets/" + NS + "sheet")
        ]
        if len(sheet_names) != 1:
            raise ValueError("HEADER_WORKBOOK_MUST_HAVE_ONE_SHEET")
        if "xl/worksheets/sheet1.xml" not in names:
            raise ValueError("FIRST_SHEET_XML_MISSING")
        shared = []
        if "xl/sharedStrings.xml" in names:
            strings = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = [text_from_si(si) for si in strings.findall(NS + "si")]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        sheet_data = sheet.find(NS + "sheetData")
        if sheet_data is None:
            raise ValueError("SHEETDATA_MISSING")
        row1 = next((r for r in sheet_data.findall(NS + "row") if r.attrib.get("r") == "1"), None)
        if row1 is None:
            raise ValueError("HEADER_ROW_MISSING")
        cells = row1.findall(NS + "c")
        headers = {}
        for cell in cells:
            idx = excel_column(cell.attrib.get("r", ""))
            if idx in headers:
                raise ValueError("DUPLICATE_CELL_REFERENCE")
            headers[idx] = cell_text(cell, shared)
        if not headers or max(headers) >= 100:
            raise ValueError("INVALID_HEADER_ROW_WIDTH")
        return sheet_names[0], [headers.get(i, "") for i in range(max(headers) + 1)], len(cells)


def load_contract(repo, sha_ref):
    if not re.fullmatch(r"[0-9a-f]{40}", sha_ref):
        raise ValueError("INVALID_PINNED_COMMIT")
    result = subprocess.run(
        ["git", "-C", str(repo), "show", sha_ref + ":" + MAIN_CONTRACT],
        text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError("PINNED_IMPORT_CONTRACT_UNAVAILABLE")
    data = json.loads(result.stdout)
    headers53 = data["headers"]
    if len(headers53) != 53:
        raise ValueError("PINNED_53_CONTRACT_INVALID")
    headers34 = headers53[:8] + headers53[11:37]
    headers35 = headers34[:8] + ["Branch Code"] + headers34[8:]
    if len(headers34) != 34 or len(headers35) != 35:
        raise ValueError("PINNED_SOURCE_CONTRACT_INVALID")
    return {34: headers34, 35: headers35, 53: headers53}


def main():
    if len(sys.argv) != 3:
        raise ValueError("NEED_PINNED_SOURCE_SHA_AND_WORKBOOK_PATH")
    source_sha, path_name = sys.argv[1:]
    local = Path(path_name)
    if not local.is_file() or local.is_symlink():
        raise ValueError("HEADER_WORKBOOK_MISSING_OR_LINKED")
    print("=== AWS SBI EXACT HEADER CONTRACT COMPARISON ===")
    contracts = load_contract(Path("/home/ubuntu/sbi-aws-app"), source_sha)
    name, actual, stored_cells = extract_headers(local)
    print("PINNED_CONTRACT_SOURCE_SHA=" + source_sha)
    print("HEADER_WORKBOOK_SHA256=" + sha(local.read_bytes()))
    print("FIRST_SHEET_NAME=" + name)
    print("FIRST_ROW_STORED_CELLS=" + str(stored_cells))
    print("FIRST_ROW_WIDTH=" + str(len(actual)))
    print("FIRST_ROW_HEADER_SEQUENCE_SHA256=" + canonical_digest(actual))
    matched = [n for n, headers in contracts.items() if actual == headers]
    for count in (34, 35, 53):
        print("EXACT_APPROVED_{}_HEADERS={}".format(
            count, "MATCH" if count in matched else "NO_MATCH"
        ))
    if not matched:
        print("HEADER_CONTRACT=REVIEW_REQUIRED_NO_EXACT_MATCH")
        if len(actual) in contracts:
            different = [str(i + 1) for i, (left, right) in enumerate(zip(actual, contracts[len(actual)])) if left != right]
            print("MISMATCH_COLUMN_POSITIONS=" + ",".join(different))
    else:
        print("HEADER_CONTRACT=EXACT_MATCH_{}_SOURCE_LAYOUT".format(matched[0]))
        print("APPROVED_SOURCE_HEADER_SHA256=" + canonical_digest(contracts[matched[0]]))
        if matched[0] in (34, 35):
            print("INVOICE_IMPORT_SHEET_NAME=" +
                  ("MATCH" if name == "Invoice Details." else "NOT_MATCHED"))
    print("HEADER_WORKBOOK_FINANCIAL_ROWS=NOT_CERTIFIED")
    print("INDEPENDENT_VALUE_PARITY=NOT_VERIFIED")
    print("FINANCIAL_WRITES=NOT_PERFORMED")
    print("PRODUCTION_CUTOVER=BLOCKED")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, BadZipFile, ET.ParseError) as error:
        print("EXACT_HEADER_CONTRACT_QA=REVIEW_REQUIRED_" + str(error))
        print("FINANCIAL_WRITES=NOT_PERFORMED")
        print("PRODUCTION_CUTOVER=BLOCKED")
        sys.exit(2)
