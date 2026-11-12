"""Bounded Excel/CSV Credit Note import parsing and read-only Error export.

Separate from the 34/35/53 invoice workbook parser. No Cloud or DB access.
Only a dedicated Credit Note No field can be used for CN uniqueness.
"""
import csv
import io
from pathlib import PurePath

from credit_note_validation import (
    INVOICE_ALIASES, CREDIT_NOTE_ALIASES, NARRATION_ALIASES,
    REPLACEMENT_ALIASES,
)
from credit_note_registry_readonly import MAX_PREVIEW_ROWS

MAX_FILE_BYTES = 8 * 1024 * 1024
ALLOWED = set(INVOICE_ALIASES + CREDIT_NOTE_ALIASES +
              NARRATION_ALIASES + REPLACEMENT_ALIASES)
CSV_HEADERS = ("Source Row", "Invoice No", "Credit Note No",
               "New Invoice Against Credit Note", "Status", "Error Reasons")


def _headings(headers):
    headers = [str(h).strip() if h is not None else "" for h in headers]
    nonempty = [h for h in headers if h]
    if len(nonempty) != len(set(nonempty)):
        raise ValueError("DUPLICATED_CREDIT_NOTE_HEADERS")
    for group, label in (
        (INVOICE_ALIASES, "INVOICE_NUMBER"),
        (CREDIT_NOTE_ALIASES, "CREDIT_NOTE_NUMBER"),
        (NARRATION_ALIASES, "CREDIT_NOTE_DESCRIPTION"),
    ):
        if sum(h in group for h in headers) != 1:
            raise ValueError("MISSING_OR_AMBIGUOUS_" + label)
    if sum(h in REPLACEMENT_ALIASES for h in headers) > 1:
        raise ValueError("AMBIGUOUS_REPLACEMENT_INVOICE")
    return headers


def _rows_to_maps(headers, rows):
    result = []
    for excel_row, values in enumerate(rows, start=2):
        values = list(values)
        if not any(str(v if v is not None else "").strip() for v in values):
            continue
        if len(values) != len(headers):
            raise ValueError("SOURCE_ROW_WIDTH_MISMATCH")
        if len(result) >= MAX_PREVIEW_ROWS:
            raise ValueError("MAX_20000_ROWS_PER_PREVIEW")
        record = {
            h: "" if v is None else str(v)
            for h, v in zip(headers, values) if h in ALLOWED
        }
        record["_source_row"] = excel_row
        result.append(record)
    if not result:
        raise ValueError("EMPTY_CREDIT_NOTE_UPLOAD")
    return result


def parse_credit_note_upload(filename, data):
    if not isinstance(filename, str) or not isinstance(data, bytes):
        raise ValueError("INVALID_CREDIT_NOTE_UPLOAD")
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("CREDIT_NOTE_UPLOAD_EMPTY_OR_OVER_8MIB")
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CREDIT_NOTE_CSV_MUST_BE_UTF8") from exc
        stream = io.StringIO(text, newline="")
        reader = csv.reader(stream, strict=True)
        try:
            header = _headings(next(reader))
        except StopIteration as exc:
            raise ValueError("EMPTY_CREDIT_NOTE_UPLOAD") from exc
        return _rows_to_maps(header, reader)
    if suffix == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise ValueError("XLSX_PARSER_DEPENDENCY_MISSING") from exc
        book = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=False,
            keep_links=False
        )
        try:
            matches = []
            for sheet in book.worksheets:
                if sheet.max_row < 2:
                    continue
                headers = list(next(
                    sheet.iter_rows(min_row=1, max_row=1, values_only=True)
                ))
                try:
                    names = _headings(headers)
                except ValueError:
                    continue
                matches.append((sheet, names))
            if len(matches) != 1:
                raise ValueError("REQUIRE_ONE_VALID_CREDIT_NOTE_SHEET")
            sheet, headers = matches[0]
            if sheet.max_row > MAX_PREVIEW_ROWS + 1:
                raise ValueError("MAX_20000_ROWS_PER_PREVIEW")
            rows = []
            for cells in sheet.iter_rows(min_row=2, max_col=len(headers)):
                if any(cell.data_type in ("f", "e") for cell in cells):
                    raise ValueError("FORMULA_OR_CELL_ERROR_IN_CN_UPLOAD")
                rows.append([cell.value for cell in cells])
            return _rows_to_maps(headers, rows)
        finally:
            book.close()
    raise ValueError("CREDIT_NOTE_UPLOAD_MUST_BE_CSV_OR_XLSX")


def _safe_csv(value):
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "@", "-", "\t", "\r", "\n")):
        return "'" + text
    return text


def error_report_csv(preview):
    """Only Error/Review rows; no attempt to publish validated records."""
    if not isinstance(preview, dict) or "rows" not in preview:
        raise ValueError("INVALID_PREVIEW")
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for row in preview["rows"]:
        if row.get("status") not in ("ERROR", "REVIEW_PENDING_REGISTRY"):
            continue
        writer.writerow([
            _safe_csv(row.get("source_row")),
            _safe_csv(row.get("invoice_no")),
            _safe_csv(row.get("credit_note_no")),
            _safe_csv(row.get("replacement_invoice_no")),
            _safe_csv(row.get("status")),
            _safe_csv(";".join(row.get("reasons", []))),
        ])
    return out.getvalue().encode("utf-8-sig")
