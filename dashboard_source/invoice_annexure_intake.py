"""In-memory .xlsx annexure intake for the approved Invoice UI Version 2.

No disk writes, no permanent import, no database changes. Uploaded AWBs are
reviewed/selected/edited in the browser and ALWAYS revalidated server-side
at invoice preview/finalization.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile, ZipFile
import re

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_SHIPMENTS = 5000
MAX_ARCHIVE_ITEMS = 1500
CENT = Decimal("0.01")
THOUSANDTH = Decimal("0.001")


class AnnexureImportError(ValueError):
    pass


def _header(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))


EXPECTED = (
    {"dispatch date", "dispatch date (dd/mm/yyyy)"},
    {"lr no", "lr no.", "lr number", "awb no", "awb no.", "awb number", "awb no."},
    {"packet ref no", "packet ref no.", "packet ref", "packet reference"},
    {"consignee", "consignee name"},
    {"weight", "weight (kg)", "weight kg"},
    {"amount", "amount ₹", "amount rs", "amount (rs)"},
)


def _check_zip(raw):
    try:
        with ZipFile(BytesIO(raw)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_ITEMS:
                raise AnnexureImportError("UNSAFE_EXCEL_ARCHIVE")
            total = 0
            for member in members:
                total += member.file_size
                if member.flag_bits & 1 or member.file_size > MAX_UNCOMPRESSED:
                    raise AnnexureImportError("UNSAFE_EXCEL_ARCHIVE")
                if total > MAX_UNCOMPRESSED:
                    raise AnnexureImportError("EXCEL_UNCOMPRESSED_SIZE_LIMIT")
            if archive.testzip() is not None:
                raise AnnexureImportError("CORRUPT_EXCEL_ARCHIVE")
    except BadZipFile:
        raise AnnexureImportError("INVALID_XLSX_ARCHIVE") from None


def _safe_text(value, name, limit, *, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise AnnexureImportError("INVALID_" + name)
    result = str(value).strip()
    if (not result and not optional) or len(result) > limit:
        raise AnnexureImportError("INVALID_" + name)
    if any(ord(c) < 32 for c in result):
        raise AnnexureImportError("INVALID_" + name)
    return result


def _dispatch_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise AnnexureImportError("INVALID_DISPATCH_DATE")
    raw = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    raise AnnexureImportError("INVALID_DISPATCH_DATE")


def _number(value, name, resolution):
    if value is None or isinstance(value, (bool, datetime, date)):
        raise AnnexureImportError("INVALID_" + name)
    try:
        number = Decimal(str(value).strip())
    except (ValueError, InvalidOperation):
        raise AnnexureImportError("INVALID_" + name) from None
    if not number.is_finite() or number <= 0:
        raise AnnexureImportError("INVALID_" + name)
    rounded = number.quantize(resolution)
    # Safe only for binary-to-decimal Excel float representation noise;
    # a real extra half-cent or 4th weight decimal place is rejected.
    if abs(number - rounded) > Decimal("0.00000001"):
        raise AnnexureImportError("INVALID_" + name + "_PRECISION")
    if rounded > Decimal("9999999999.99"):
        raise AnnexureImportError("INVALID_" + name)
    return str(rounded)


def parse_xlsx_annexure(raw):
    """Return exactly one verified six-column annexure, no side effects."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_FILE_BYTES:
        raise AnnexureImportError("EXCEL_FILE_SIZE_LIMIT")
    _check_zip(raw)
    from openpyxl import load_workbook
    try:
        book = load_workbook(
            BytesIO(raw), read_only=True, data_only=False,
            keep_links=False,
        )
    except Exception:
        raise AnnexureImportError("INVALID_XLSX_WORKBOOK") from None
    try:
        sheets = []
        for sheet in book.worksheets:
            head = next(sheet.iter_rows(min_row=1, max_row=1), ())
            if len(head) != 6:
                continue
            if all(_header(head[i].value) in EXPECTED[i] for i in range(6)):
                sheets.append(sheet)
        if len(sheets) != 1:
            raise AnnexureImportError("EXACTLY_ONE_APPROVED_SIX_COLUMN_SHEET_REQUIRED")
        sheet = sheets[0]
        if sheet.max_row is not None and sheet.max_row > MAX_SHIPMENTS + 1:
            raise AnnexureImportError("ANNEXURE_ROW_LIMIT_EXCEEDED")
        if sheet.max_column is not None and sheet.max_column != 6:
            raise AnnexureImportError("EXACTLY_SIX_ANNEXURE_COLUMNS_REQUIRED")
        items = []
        seen = set()
        duplicate_count = 0
        for source_row, cells in enumerate(
            sheet.iter_rows(min_row=2, max_col=6), start=2
        ):
            if all(c.value is None or c.value == "" for c in cells):
                continue
            if any(c.data_type in ("f", "e") for c in cells):
                raise AnnexureImportError("EXCEL_FORMULA_OR_ERROR_NOT_ALLOWED")
            if len(items) + duplicate_count >= MAX_SHIPMENTS:
                raise AnnexureImportError("ANNEXURE_ROW_LIMIT_EXCEEDED")
            vals = [c.value for c in cells]
            row = {
                "dispatch_date": _dispatch_date(vals[0]),
                "lr_no": _safe_text(vals[1], "AWB_NUMBER", 40),
                "packet_ref_no": _safe_text(vals[2], "PACKET_REF", 80, optional=True),
                "consignee": _safe_text(vals[3], "CONSIGNEE", 200),
                "weight_kg": _number(vals[4], "WEIGHT", THOUSANDTH),
                "amount": _number(vals[5], "AMOUNT", CENT),
                "source_row": source_row,
            }
            if not re.fullmatch(r"[A-Za-z0-9/-]{1,40}", row["lr_no"]):
                raise AnnexureImportError("INVALID_AWB_NUMBER")
            key = (row["dispatch_date"], row["lr_no"])
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            items.append(row)
        if not items:
            raise AnnexureImportError("ANNEXURE_EMPTY")
        return {
            "shipments": items,
            "imported_count": len(items),
            "duplicate_rows_skipped": duplicate_count,
            "source_sheet": sheet.title,
            "persisted": False,
            "financial_writes": False,
        }
    finally:
        book.close()
