"""SBI Bulk Report: authenticated in-memory, read-only invoice Excel to ZIP.

SOURCE_ONLY: never accesses financial database, creates receipts, allocates
payments, changes invoice fields or claims actual settlement. A bulk report
from a user-supplied workbook is NOT a certified financial database report.
Exact approved 34 / 35 / 53 original source headers are required.
"""
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, jsonify, request
from openpyxl import load_workbook
from openpyxl.cell.read_only import EmptyCell
from openpyxl.utils.exceptions import InvalidFileException

from dashboard_sessions import csrf_valid
from invoice_source_schema import HEADERS_53, sheet_layout, export_values_53
from sbi_reporting_bundle import csv_bytes

bulk_report = Blueprint("sbi_aws_bulk_report", __name__)

MAX_UPLOAD = 8 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED = 80 * 1024 * 1024
MAX_ROWS = 20_000
MAX_REPORT_ZIP = 64 * 1024 * 1024
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
SCIENTIFIC = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
REVIEW_HEADERS = ["Source Row", "Invoice No", "Review Flag"]
KINDS = ("unpaid", "ok", "error-value", "balance-review")
ALLOWED_TYPES = frozenset(("s", "str", "inlineStr", "n"))


def _as_text(cell):
    val = cell.value
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    return str(val)


def _payment_kind(cell):
    value = _as_text(cell).strip()
    if cell.data_type not in ALLOWED_TYPES:
        return "error-value"
    if not value:
        return "unpaid"
    regex = SCIENTIFIC if cell.data_type == "n" else NUMBER
    if not regex.fullmatch(value):
        return "error-value"
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return "error-value"
    if not amount.is_finite() or amount < 0:
        return "error-value"
    return "unpaid" if amount == 0 else "ok"


def _invalid_balance(cell):
    if cell.data_type not in ALLOWED_TYPES:
        return True
    text = _as_text(cell).strip()
    if not text or not (SCIENTIFIC if cell.data_type == "n" else NUMBER).fullmatch(text):
        return True
    try:
        return not Decimal(text).is_finite()
    except InvalidOperation:
        return True


def _zip_safety(data):
    """Never extract an XLSX; reject oversized, encrypted and malformed archives."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            items = archive.infolist()
            if not items or len(items) > 1500:
                raise ValueError("Workbook archive has an unsupported structure")
            total = 0
            for item in items:
                total += item.file_size
                if item.flag_bits & 1 or item.file_size > MAX_XLSX_UNCOMPRESSED:
                    raise ValueError("Workbook archive is encrypted or too large")
                if total > MAX_XLSX_UNCOMPRESSED:
                    raise ValueError("Workbook archive exceeds the safety limit")
            if archive.testzip() is not None:
                raise ValueError("Workbook archive integrity failed")
    except zipfile.BadZipFile as error:
        raise ValueError("Invalid .xlsx workbook") from error


def _build(data):
    _zip_safety(data)
    workbook = None
    try:
        workbook = load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
        matched = []
        for sheet in workbook.worksheets:
            headers = list(next(sheet.iter_rows(min_row=1,max_row=1,values_only=True),()))
            layout = sheet_layout(sheet.title,headers)
            if layout is not None:
                matched.append((sheet,headers,layout))
        if len(matched) != 1:
            raise ValueError("Provide exactly one approved Invoice Details. (34/35 columns) or 53-column source sheet")
        sheet, source_headers, layout = matched[0]
        width, invoice_col = layout
        # Read-only XLSX files may legitimately omit the optional worksheet
        # <dimension> element. In that case openpyxl reports None for the
        # worksheet bounds even when the approved headers and data are valid.
        # Enforce known dimensions, and always verify the actual streamed rows.
        if ((isinstance(sheet.max_row, int) and sheet.max_row > MAX_ROWS+1) or
            (isinstance(sheet.max_column, int) and sheet.max_column != width)):
            raise ValueError("Workbook exceeds 20,000 rows or approved source column width")

        accepted = []
        reviewed = []
        frequency = Counter()
        # Do not set max_col here: when worksheet dimensions are absent, scan
        # the actual row width instead of silently dropping unexpected columns.
        for i, cells in enumerate(sheet.iter_rows(min_row=2),start=2):
            if i > MAX_ROWS+1 or len(cells) > width:
                raise ValueError("Workbook exceeds 20,000 rows or approved source column width")
            # Streaming XML rows may omit empty trailing cells. Normalize only
            # those missing cells so approved source fields retain their indexes.
            if len(cells) < width:
                cells = tuple(cells) + tuple(EmptyCell() for _ in range(width-len(cells)))
            if all(cell.value is None or cell.value=="" for cell in cells):
                continue
            row_values = [_as_text(cell) for cell in cells]
            if any(len(v)>8192 for v in row_values):
                raise ValueError("Source cell exceeds the 8192-character safety limit")
            invoice_cell = cells[invoice_col]
            invoice_no = row_values[invoice_col].strip()
            issues = []
            if not invoice_no:
                issues.append("MISSING_INVOICE_NUMBER")
            elif invoice_cell.data_type not in ("s","str","inlineStr"):
                issues.append("INVOICE_NUMBER_MUST_BE_TEXT")
            else:
                frequency[invoice_no] += 1
            accepted.append((i,invoice_no,cells,row_values,issues))
        if not accepted:
            raise ValueError("No invoice rows found in the approved source sheet")
        groups = {name:[] for name in KINDS}
        groups["all-invoices"]=[]
        for source_row,invoice_no,cells,values,issues in accepted:
            if invoice_no and frequency[invoice_no]>1:
                issues.append("DUPLICATE_INVOICE_NUMBER")
            if issues:
                reviewed.append([str(source_row),invoice_no," | ".join(issues)])
                continue
            record={
                "original_values":values,
                "original_headers":source_headers,
            }
            projected=export_values_53(record)
            groups["all-invoices"].append(projected)
            kind = _payment_kind(cells[20 if width==53 else 18 if width==35 else 17])
            groups[kind].append(projected)
            balance_col=27 if width==53 else 25 if width==35 else 24
            if _invalid_balance(cells[balance_col]):
                groups["balance-review"].append(projected)

        output=io.BytesIO()
        source_hash=hashlib.sha256(data).hexdigest()
        stamp=datetime.now(timezone.utc).isoformat()
        manifest={
            "schema":"sbi-uploaded-bulk-report/v1",
            "source_kind":"USER_UPLOADED_WORKBOOK_NOT_CERTIFIED_LEDGER",
            "source_sha256":source_hash,
            "source_sheet":sheet.title,
            "source_layout_columns":width,
            "created_utc":stamp,
            "financial_writes":False,
            "reconciliation_executed":False,
            "database_updated":False,
            "classification_basis":"SAVED_PAYMENT_RECEIVED_VALUE_ONLY",
            "caution":"OK means non-zero valid saved payment, not full payment or successful reconciliation.",
            "counts":{
                "source_rows":len(accepted),
                "accepted_unique_invoice_rows":len(groups["all-invoices"]),
                "review_rows":len(reviewed),
                **{k:len(groups[k]) for k in KINDS},
            },
            "files":[]
        }
        with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as result:
            for name,rows in groups.items():
                raw,count=csv_bytes(HEADERS_53,rows)
                filename=name+".csv"
                result.writestr(filename,raw)
                manifest["files"].append({
                    "name":filename,"rows":count,
                    "sha256":hashlib.sha256(raw).hexdigest(),
                })
            flags,flag_count=csv_bytes(REVIEW_HEADERS,reviewed)
            result.writestr("validation-review.csv",flags)
            manifest["files"].append({
                "name":"validation-review.csv",
                "rows":flag_count,"sha256":hashlib.sha256(flags).hexdigest(),
            })
            result.writestr("manifest.json",json.dumps(manifest,indent=2)+"\n")
        payload=output.getvalue()
        if len(payload)>MAX_REPORT_ZIP:
            raise ValueError("Bulk Report ZIP exceeds the export safety limit")
        return payload,manifest
    finally:
        if workbook is not None:
            workbook.close()


@bulk_report.get("/api/bulk-report/status")
def status():
    return jsonify(
        available=True,
        mode="IN_MEMORY_SOURCE_ONLY",
        supported_input=".xlsx",
        accepted_headers=["Invoice Details. 34-column","Invoice Details. 35-column",
                          "Approved 53-column original"],
        max_size_bytes=MAX_UPLOAD,
        max_rows=MAX_ROWS,
        financial_writes=False,
        reconciliation_executed=False,
        database_updated=False,
    )


@bulk_report.post("/api/bulk-report/generate")
def generate():
    # Firebase dashboard session is required by global before_request hook.
    request.max_content_length=MAX_UPLOAD+262144
    if not csrf_valid():
        return jsonify(error="Session origin or CSRF verification failed",
                       financial_writes=False),403
    if request.content_length is None or request.content_length>MAX_UPLOAD+262144:
        return jsonify(error="Excel upload exceeds 8 MiB",
                       financial_writes=False),413
    if set(request.files.keys())!={"file"}:
        return jsonify(error="Select exactly one Excel workbook",
                       financial_writes=False),422
    upload=request.files["file"]
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        return jsonify(error="Bulk Report requires an .xlsx workbook",
                       financial_writes=False),422
    content=upload.stream.read(MAX_UPLOAD+1)
    if not 0<len(content)<=MAX_UPLOAD:
        return jsonify(error="Excel workbook must be non-empty and no more than 8 MiB",
                       financial_writes=False),413
    try:
        payload,manifest=_build(content)
    except (ValueError,InvalidFileException,zipfile.BadZipFile) as error:
        return jsonify(error=str(error)[:240],financial_writes=False),422
    response=Response(payload,content_type="application/zip")
    response.headers["Content-Disposition"]=(
        'attachment; filename="SBI-Bulk-Report-'+manifest["source_sha256"][:12]+'.zip"'
    )
    response.headers["X-Bulk-Report-Summary"]=json.dumps(manifest["counts"],
                                                         separators=(",",":"))
    response.headers["X-Bulk-Report-Mode"]="SOURCE_ONLY_NOT_RECONCILED"
    response.headers["Cache-Control"]="private, no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response
