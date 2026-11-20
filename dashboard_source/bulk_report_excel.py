"""Create ONE combined XLSX from the existing validated source-only Bulk Report ZIP.

Do not alter invoice classifications, write financial data, or run reconciliation.
The CSVs come from bulk_reports._build; they are verified against the manifest
before being projected into six separate Excel worksheets.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from invoice_source_schema import HEADERS_53

MAX_COMBINED_XLSX_BYTES = 64 * 1024 * 1024

REPORT_SHEETS = (
    ("all-invoices.csv", "All Invoices"),
    ("unpaid.csv", "Unpaid"),
    ("ok.csv", "OK Payment Value"),
    ("error-value.csv", "Error Value"),
    ("balance-review.csv", "Balance Review"),
    ("validation-review.csv", "Validation Review"),
)
REVIEW_HEADERS = ["Source Row", "Invoice No", "Review Flag"]
LOOKUP_REVIEW = ("lookup-review.csv", "Lookup Review")
LOOKUP_HEADERS = ["Invoice No", "Reason"]


def combined_excel_from_report_zip(payload: bytes) -> bytes:
    """Return one XLSX with six named sheets; all imported values stay text."""
    wb = Workbook(write_only=True)
    wb.properties.title = "SBI Bulk Report — Combined Excel"
    wb.properties.subject = "Source-only invoice payment-value classifications"
    wb.properties.description = (
        "USER UPLOADED SOURCE ONLY — NOT RECONCILED. "
        "No financial database updated; OK does not mean fully paid."
    )

    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if (manifest.get("financial_writes") is not False or
            manifest.get("reconciliation_executed") is not False or
            manifest.get("database_updated") is not False):
            raise ValueError("Bulk Report financial safety manifest mismatch")
        entries = {item["name"]: item for item in manifest["files"]}
        selected_source = manifest.get("schema") == "sbi-database-selected-bulk-report/v1"
        if selected_source and manifest.get("source_kind") != "VERIFIED_READ_ONLY_REPORT_SOURCE":
            raise ValueError("Selected report source was not verified")
        required_sheets = REPORT_SHEETS + ((LOOKUP_REVIEW,) if selected_source else ())
        for filename, sheet_name in required_sheets:
            info = entries.get(filename)
            if info is None:
                raise ValueError("Missing source report: " + filename)
            raw = zf.read(filename)
            if hashlib.sha256(raw).hexdigest() != info["sha256"]:
                raise ValueError("Bulk Report source integrity check failed")
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
            sheet = wb.create_sheet(title=sheet_name)
            expected = (
                LOOKUP_HEADERS if filename == "lookup-review.csv"
                else REVIEW_HEADERS if filename == "validation-review.csv"
                else HEADERS_53
            )
            # Write-only XLSX sheets serialize view/column metadata before rows.
            sheet.freeze_panes = "A2"
            sheet.sheet_view.showGridLines = False
            for col in range(1, len(expected) + 1):
                width = 27 if col in (1, 3, 8, 13, 21) else 20
                sheet.column_dimensions[get_column_letter(col)].width = width
            sheet.row_dimensions[1].height = 40
            count = 0
            for n, row in enumerate(reader):
                if len(row) != len(expected):
                    raise ValueError("Bulk Report CSV width mismatch")
                if n == 0 and row != expected:
                    raise ValueError("Bulk Report CSV headers mismatch")
                cells = []
                for value in row:
                    # Prevent Excel formula injection and preserve SOL/invoice leading 0s.
                    cell = WriteOnlyCell(sheet, value=value)
                    cell.data_type = "s"
                    cell.number_format = "@"
                    if n == 0:
                        cell.font = Font(name="Aptos", bold=True, color="FFFFFF", size=11)
                        cell.fill = PatternFill("solid", fgColor="164E63")
                        cell.alignment = Alignment(vertical="center", wrap_text=True)
                    cells.append(cell)
                sheet.append(cells)
                if n:
                    count += 1
            if count != info["rows"]:
                raise ValueError("Bulk Report CSV row count mismatch")

    output = io.BytesIO()
    wb.save(output)
    result = output.getvalue()
    if len(result) > MAX_COMBINED_XLSX_BYTES:
        raise ValueError("Combined Excel exceeds the export safety limit")
    return result
