"""Create ONE combined XLSX from the integrity-checked Bulk Report ZIP.

Convert only recognized monetary fields to Excel numeric cells. Invoice numbers,
SOL IDs, dates, remarks and review flags remain literal text. All changes are
export-time presentation only; no financial data or classifications are written.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from invoice_source_schema import HEADERS_53

MAX_COMBINED_XLSX_BYTES = 64 * 1024 * 1024


# Zero-based positions in the approved fixed 53-column export. These are
# amounts only: not invoice numbers, branch/SOL IDs, dates, percentages or model
# source-row references. Do not infer numeric fields from cell text.
AMOUNT_COLUMN_INDEXES = frozenset((
    13,  # Taxable Amount
    14,  # CGST
    15,  # SGST
    16,  # Total Bill Amount
    17,  # Less TDS
    18,  # Actual Receivable (including GST, less TDS)
    19,  # Taxable Amount Less TDS (without GST)
    20,  # Payment Received
    22,  # GST Payment Balance
    24,  # Total Payment Received (Base Amount + GST)
    25,  # Credit Note Amount
    26,  # Total Payment less Credit Note & TDS
    27,  # Outstanding / Negative Balance
    39,  # Model Matched Bank Credit
    41,  # Model Expected Bank Credit
    42,  # Model Signed Difference
))
AMOUNT_NUMBER_FORMAT = '#,##0.00;[Red](#,##0.00);0.00'
DECIMAL_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
GROUPED_NUMBER = re.compile(r'[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?\Z')
CENT = Decimal('0.01')
FLOAT_NOISE_TOLERANCE = Decimal('0.00000001')


def _excel_money(value: str):
    """Return Excel numeric value for safe monetary text, else None.

    Tolerate binary-float representation artifacts within 1e-8 of whole cents
    (e.g., 2.4299999999999997 -> 2.43). Genuine sub-cent values are retained
    numerically, never rounded in the stored Excel value. Non-numeric labels
    such as CANCLED/CREDIT NOTE remain untouched.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 64:
        return None
    if not (DECIMAL_NUMBER.fullmatch(text) or GROUPED_NUMBER.fullmatch(text)):
        return None
    try:
        number = Decimal(text.replace(',', ''))
        if not number.is_finite() or number.copy_abs() >= Decimal('1e13'):
            # Excel floating point cannot safely represent cents at this size.
            return None
        cents = number.quantize(CENT, rounding=ROUND_HALF_UP)
        if abs(number - cents) <= FLOAT_NOISE_TOLERANCE:
            number = cents
        result = float(number)
        if result == float('inf') or result == float('-inf'):
            return None
        return result
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _report_value(value: str, *, column: int, header: bool, money_sheet: bool):
    if not header and money_sheet and column in AMOUNT_COLUMN_INDEXES:
        number = _excel_money(value)
        if number is not None:
            return number, AMOUNT_NUMBER_FORMAT
    # All other content remains literal text, including neutralized formulas.
    return value, "@"


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
    """Return one XLSX with 6 or 7 sheets; amounts are numeric, IDs stay text."""
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
        if selected_source:
            wb.properties.subject = "Verified saved invoices selected by uploaded invoice numbers"
            wb.properties.description = (
                "VERIFIED READ-ONLY SAVED INVOICE SOURCE — NOT RECONCILED. "
                "Uploaded workbook supplies only invoice numbers. "
                "No financial records updated; OK does not mean fully paid."
            )
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
                money_sheet = filename not in ("validation-review.csv", "lookup-review.csv")
                for column, value in enumerate(row):
                    # Financial amounts are native Excel numbers. SOL/invoice
                    # identifiers and non-money text remain untouched.
                    converted, fmt = _report_value(
                        value, column=column, header=(n == 0),
                        money_sheet=money_sheet,
                    )
                    cell = WriteOnlyCell(sheet, value=converted)
                    cell.number_format = fmt
                    if fmt == "@":
                        cell.data_type = "s"
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
