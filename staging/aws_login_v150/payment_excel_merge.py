"""Authenticated, in-memory Excel merge for SBI payment evidence.

This module NEVER performs financial reconciliation, allocations, database
writes, persistent uploads, or GitHub changes. Original PAYMNENT A-L values
(including Column I Credit) are preserved in an exported *review copy*.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from werkzeug.utils import secure_filename
from dashboard_sessions import csrf_valid

payment_excel = Blueprint("sbi_payment_excel", __name__)

MAX_FILES = 6
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 24 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DATA_ROWS = 40000
SOURCE_COLUMNS = 12


class EvidenceError(ValueError):
    pass


def _checked_files():
    if not csrf_valid():
        return None, (jsonify(error="Verified same-origin CSRF token required"), 403)
    if not request.content_type or not request.content_type.lower().startswith(
        "multipart/form-data"
    ):
        return None, (jsonify(error="Excel files must use multipart upload"), 415)
    if request.content_length is None or request.content_length > MAX_REQUEST_BYTES:
        return None, (jsonify(error="Excel request exceeds the 24 MiB limit"), 413)
    uploaded = request.files.getlist("files")
    if not 1 <= len(uploaded) <= MAX_FILES:
        return None, (jsonify(error="Choose 1–6 .xlsx payment workbooks"), 422)
    result = []
    total = 0
    names = set()
    for file in uploaded:
        name = secure_filename(file.filename or "")
        if not name.lower().endswith(".xlsx") or not name:
            return None, (jsonify(
                error="Only .xlsx is supported. Convert .xls to .xlsx before merging."
            ), 422)
        if name.casefold() in names:
            return None, (jsonify(error="Files must have distinct filenames"), 422)
        names.add(name.casefold())
        content = file.stream.read(MAX_FILE_BYTES + 1)
        total += len(content)
        if len(content) > MAX_FILE_BYTES or not content:
            return None, (jsonify(error="Each workbook must be 1 byte–8 MiB"), 413)
        if total > MAX_REQUEST_BYTES:
            return None, (jsonify(error="Combined workbooks exceed 24 MiB"), 413)
        if not zipfile.is_zipfile(io.BytesIO(content)):
            return None, (jsonify(error="Invalid .xlsx workbook: " + name), 422)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            expanded = sum(item.file_size for item in archive.infolist())
            if expanded > MAX_UNCOMPRESSED_BYTES:
                return None, (jsonify(error="Expanded Excel content exceeds safe limit"), 413)
        result.append((name, content))
    return result, None


def _sheet(workbook):
    found = [
        name for name in workbook.sheetnames
        if re.sub(r"[\s_.-]", "", name).upper() == "PAYMNENT"
    ]
    if len(found) != 1:
        raise EvidenceError(
            "Exactly one PAYMNENT worksheet is required in every workbook"
        )
    return workbook[found[0]]


def _heading(sheet):
    for index, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=min(sheet.max_row or 0, 12),
                        min_col=1, max_col=SOURCE_COLUMNS),
        start=1,
    ):
        credit = str(row[8].value or "").strip().casefold()
        populated = sum(bool(str(cell.value or "").strip()) for cell in row)
        if credit == "credit" and populated >= 4:
            headings = [cell.value if cell.value is not None else "" for cell in row]
            return index, headings
    raise EvidenceError(
        "PAYMNENT header not verified. Column I must have the heading 'Credit' "
        "within the first 12 rows."
    )


def _key(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().casefold().split())


def _credit(value, name, row):
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, bool):
        raise EvidenceError(f"{name}, row {row}: invalid Column I Credit")
    try:
        normalized = str(value).replace(",", "").replace("₹", "").strip()
        amount = Decimal(normalized)
        if not amount.is_finite():
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise EvidenceError(
            f"{name}, row {row}: Column I Credit has a non-numeric value"
        ) from None


def _load(files):
    expected = None
    all_rows = []
    evidence = []
    seen = set()
    duplicate_count = 0
    aggregate_credit = Decimal("0")
    for name, content in files:
        book = None
        try:
            book = load_workbook(
                filename=io.BytesIO(content),
                read_only=True,
                data_only=False,
                keep_links=False,
            )
            sheet = _sheet(book)
            header_row, headers = _heading(sheet)
            schema = tuple(_key(value) for value in headers)
            if expected is None:
                expected = schema
                original_headers = headers
            elif schema != expected:
                raise EvidenceError(
                    f"{name}: A–L headers differ from the first payment workbook; "
                    "merge stopped to avoid mixing schemas"
                )
            n_rows = 0
            credits = Decimal("0")
            for row_index, cells in enumerate(
                sheet.iter_rows(min_row=header_row + 1, min_col=1,
                                max_col=SOURCE_COLUMNS),
                start=header_row + 1,
            ):
                values = [cell.value for cell in cells]
                if not any(value is not None and value != "" for value in values):
                    continue
                if any(getattr(cell, "data_type", "") == "f" for cell in cells):
                    raise EvidenceError(
                        f"{name}, row {row_index}: formulas in source columns A–L "
                        "are not accepted for evidence merging"
                    )
                if len(all_rows) >= MAX_DATA_ROWS:
                    raise EvidenceError("More than 40,000 rows; split this batch")
                amount = _credit(values[8], name, row_index)
                credits += amount
                signature = hashlib.sha256(
                    repr([(type(v).__name__, str(v)) for v in values])
                    .encode("utf-8")
                ).digest()
                if signature in seen:
                    duplicate_count += 1
                seen.add(signature)
                formats = [getattr(c, "number_format", "General") for c in cells]
                all_rows.append((name, sheet.title, row_index, values, formats))
                n_rows += 1
            aggregate_credit += credits
            evidence.append({
                "filename": name,
                "worksheet": sheet.title,
                "header_row": header_row,
                "data_rows": n_rows,
                "credit_total": str(credits),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        except EvidenceError:
            raise
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            raise EvidenceError(f"{name}: unreadable Excel workbook") from error
        finally:
            if book is not None:
                book.close()
    return evidence, all_rows, duplicate_count, aggregate_credit, original_headers


@payment_excel.post("/payment-evidence/excel/<mode>")
def excel_evidence(mode):
    if mode not in ("preview", "merge"):
        return jsonify(error="Unknown Excel operation"), 404
    files, rejection = _checked_files()
    if rejection is not None:
        return rejection
    try:
        audit, rows, duplicates, credits, headers = _load(files)
        if mode == "preview":
            return jsonify(
                ok=True,
                operation="read_only_excel_evidence_preview",
                workbooks=len(audit),
                rows=len(rows),
                total_credit=str(credits),
                duplicate_rows=duplicates,
                sources=audit,
                note=(
                    "Only A–L source values are examined. No financial records "
                    "are written, no reconciliation is performed."
                ),
                financial_execution_enabled=False,
                stored_on_server=False,
            )
        if len(files) < 2:
            return jsonify(error="Select at least two workbooks to merge"), 422
        if duplicates:
            return jsonify(
                error=(
                    f"{duplicates} repeated payment rows detected. "
                    "Merge blocked until duplicates are resolved in source evidence."
                ),
                duplicate_rows=duplicates,
            ), 409

        book = Workbook()
        payment = book.active
        payment.title = "PAYMNENT"
        payment.append(list(headers) + ["Source File", "Source Sheet", "Source Row"])
        for name, source_sheet, source_row, values, formats in rows:
            payment.append(values + [name, source_sheet, source_row])
            for col, number_format in enumerate(formats, start=1):
                payment.cell(row=payment.max_row, column=col).number_format = number_format
                # Excel text beginning '=' must stay text, never become a formula.
                target = payment.cell(row=payment.max_row, column=col)
                if isinstance(target.value, str) and target.value.startswith("="):
                    target.data_type = "s"
        audit_sheet = book.create_sheet("Merge Audit")
        audit_sheet.append(["Source File", "Worksheet", "Header Row", "Rows",
                            "Credit Total", "SHA-256"])
        for source in audit:
            audit_sheet.append([source[k] for k in
                ("filename", "worksheet", "header_row", "data_rows",
                 "credit_total", "sha256")])
        audit_sheet.append(["TOTAL", "", "", len(rows), str(credits), ""])
        for sheet in (payment, audit_sheet):
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(color="FFFFFF", bold=True)
                cell.fill = PatternFill("solid", fgColor="16435A")
        payment.column_dimensions["A"].width = 20
        payment.column_dimensions["M"].width = 35
        payment.column_dimensions["N"].width = 20
        audit_sheet.column_dimensions["A"].width = 35
        audit_sheet.column_dimensions["F"].width = 67
        result = io.BytesIO()
        book.save(result)
        book.close()
        result.seek(0)
        if result.getbuffer().nbytes > 12 * 1024 * 1024:
            return jsonify(error="Merged workbook exceeds 12 MiB output limit"), 413
        response = send_file(
            result,
            as_attachment=True,
            download_name="SBI_Payment_Evidence_Merged_Review.xlsx",
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response.headers["X-Financial-Writes"] = "DISABLED"
        return response
    except EvidenceError as error:
        return jsonify(error=str(error)), 422
