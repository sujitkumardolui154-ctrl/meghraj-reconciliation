"""Read-only user-selected invoice number list for future database Bulk Report.

This is a selection parser, NOT a financial database, reconciliation engine or
report source. It deliberately does not invent invoice data for missing IDs.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_UPLOAD = 8 * 1024 * 1024
MAX_UNCOMPRESSED = 96 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1500
MAX_REQUESTED_INVOICES = 2000
MAX_SHEET_ROWS = 5001
ALLOWED_TYPES = frozenset(("s", "str", "inlineStr"))
HEADER_ALIASES = frozenset(("invoice no", "invoice no.", "invoice number", "invoice number."))


@dataclass(frozen=True)
class Selection:
    invoice_numbers: tuple[str, ...]
    review: tuple[tuple[int, str, str], ...]


def _safe_archive(payload: bytes) -> None:
    if not 0 < len(payload) <= MAX_UPLOAD:
        raise ValueError("Invoice number workbook must be nonempty and at most 8 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Unsupported workbook archive")
            if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                raise ValueError("Workbook exceeds the uncompressed safety limit")
            if any(i.flag_bits & 1 or i.file_size > MAX_UNCOMPRESSED for i in infos):
                raise ValueError("Encrypted or excessive workbook content")
            if archive.testzip() is not None:
                raise ValueError("Corrupted XLSX archive")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid XLSX archive") from exc


def parse_selection(payload: bytes) -> Selection:
    """Accept arbitrary-order text invoice numbers from a one-column XLSX.

    Supports an optional Invoice No header. Duplicate and invalid invoice
    numbers enter review instead of causing duplicate report rows.
    """
    _safe_archive(payload)
    book = None
    try:
        book = load_workbook(io.BytesIO(payload), read_only=True,
                             data_only=False, keep_links=False)
        visible = [sheet for sheet in book.worksheets if sheet.sheet_state == "visible"]
        if len(visible) != 1:
            raise ValueError("Provide one visible sheet of invoice numbers")
        sheet = visible[0]
        if isinstance(sheet.max_row, int) and sheet.max_row > MAX_SHEET_ROWS:
            raise ValueError("Invoice number list has too many rows")
        if isinstance(sheet.max_column, int) and sheet.max_column > 1:
            raise ValueError("Invoice number list must have exactly one column")

        selected = []
        seen = set()
        review = []
        header_checked = False
        for row_number, cells in enumerate(sheet.iter_rows(), start=1):
            if row_number > MAX_SHEET_ROWS or len(cells) > 1:
                raise ValueError("Invoice number list exceeds row/column limits")
            cell = cells[0] if cells else None
            raw = "" if cell is None or cell.value is None else str(cell.value)
            value = raw.strip()
            if not header_checked:
                header_checked = True
                if value.casefold() in HEADER_ALIASES:
                    continue
            if not value:
                continue
            if (
                cell is None or cell.data_type not in ALLOWED_TYPES
                or len(value) > 128
                or any(ord(c) < 32 or ord(c) == 127 for c in value)
                or value.startswith(("=", "+", "-", "@"))
            ):
                review.append((row_number, value[:128], "INVALID_INVOICE_NUMBER"))
                continue
            if value in seen:
                review.append((row_number, value, "DUPLICATE_REQUESTED_INVOICE"))
                continue
            if len(selected) >= MAX_REQUESTED_INVOICES:
                raise ValueError("At most 2,000 unique invoices per request")
            seen.add(value)
            selected.append(value)
        if not selected:
            raise ValueError("No valid invoice numbers found")
        return Selection(tuple(selected), tuple(review))
    except InvalidFileException as exc:
        raise ValueError("Invalid XLSX workbook") from exc
    finally:
        if book is not None:
            book.close()
