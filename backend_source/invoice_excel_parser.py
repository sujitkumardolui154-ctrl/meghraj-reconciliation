
"""Dashboard v1.4.0 Excel import parser; no database writes."""
import io
import json
from pathlib import Path
from datetime import date, datetime
import openpyxl
import xlrd
from upload_api import validate_excel
from invoice_source_schema import sheet_layout

MAX_ROWS = 20000
HEADERS = json.loads(
    Path(__file__).with_name("invoice_import_contract.json").read_text()
)["headers"]

def as_text(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)

def parse_excel(filename, data):
    ext = validate_excel(filename, data)
    rows, rejected = [], []

    def collect(number, values, types, invoice_is_text, missing_cache=False):
        if all(value is None or value == "" for value in values):
            if not missing_cache:
                return
        reasons = []
        if not invoice_is_text:
            reasons.append("INVOICE_NUMBER_MUST_BE_TEXT")
        if missing_cache:
            reasons.append("FORMULA_SAVED_VALUE_MISSING")
        record = {
            "source_row": number,
            "original_values": [as_text(value) for value in values],
            "original_cell_types": types,
            "original_headers": list(source_headers),
        }
        if reasons:
            rejected.append({
                "source_row": number,
                "invoice_no": as_text(values[invoice_index]),
                "reasons": reasons,
            })
        else:
            rows.append(record)

    if ext == ".xlsx":
        raw = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=False
        )
        saved = None
        try:
            matches = []
            for sheet in raw.worksheets:
                header = list(next(sheet.iter_rows(
                    min_row=1, max_row=1, values_only=True
                ), ()))
                layout = sheet_layout(sheet.title, header)
                if layout:
                    matches.append((sheet.title, header, layout))
            if len(matches) != 1:
                raise ValueError("Use Invoice Details. with the original 34 headers, or one sheet with the approved 53 headers.")
            name, source_headers, layout = matches[0]
            width, invoice_index = layout
            sheet = raw[name]
            if sheet.max_row > MAX_ROWS + 1:
                raise ValueError("maximum_20000_rows_per_import")
            if sheet.max_column != width:
                raise ValueError("Source column count does not match its headers.")
            saved = openpyxl.load_workbook(
                io.BytesIO(data), read_only=True, data_only=True
            )
            originals = sheet.iter_rows(min_row=2, max_col=width)
            cached = saved[name].iter_rows(min_row=2, max_col=width)
            for number, (original, values) in enumerate(
                zip(originals, cached), start=2
            ):
                invoice = original[invoice_index]
                collect(
                    number,
                    [cell.value for cell in values],
                    [cell.data_type for cell in values],
                    isinstance(invoice.value, str)
                    and invoice.data_type not in ("e", "f"),
                    any(
                        a.data_type == "f" and b.value is None
                        for a, b in zip(original, values)
                    ),
                )
        finally:
            raw.close()
            if saved is not None:
                saved.close()
    else:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        try:
            matches = [
                sheet for sheet in book.sheets()
                if sheet.nrows and sheet_layout(sheet.name, sheet.row_values(0))
            ]
            if len(matches) != 1:
                raise ValueError("Use Invoice Details. with the original 34 headers, or one sheet with the approved 53 headers.")
            sheet = matches[0]
            name = sheet.name
            source_headers = sheet.row_values(0)
            width, invoice_index = sheet_layout(name, source_headers)
            if sheet.nrows > MAX_ROWS + 1:
                raise ValueError("maximum_20000_rows_per_import")
            if sheet.ncols != width:
                raise ValueError("Source column count does not match its headers.")
            for index in range(1, sheet.nrows):
                values, types = [], []
                for cell in sheet.row(index):
                    value = cell.value
                    kind = "s"
                    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        value, kind = None, "n"
                    elif cell.ctype == xlrd.XL_CELL_DATE:
                        value = xlrd.xldate_as_datetime(value, book.datemode)
                        kind = "d"
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value, kind = bool(value), "b"
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        value = xlrd.error_text_from_code.get(value, "#ERROR!")
                        kind = "e"
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        value = int(value) if value.is_integer() else value
                        kind = "n"
                    values.append(value)
                    types.append(kind)
                collect(
                    index + 1, values, types,
                    sheet.cell_type(index, invoice_index) == xlrd.XL_CELL_TEXT,
                )
        finally:
            book.release_resources()

    return {
        "sheet": name,
        "headers": list(source_headers),
        "rows": rows,
        "rejected": rejected,
    }
