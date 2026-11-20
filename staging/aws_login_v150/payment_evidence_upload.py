"""Firebase-guarded, nonfinancial SBI Excel payment-evidence intake.

Only three fixed Excel columns: Description, SOL ID, Credit Amount.
This module STAGES immutable evidence files for review; it NEVER reconciles,
allocates, edits invoice/payment ledgers, or invokes a financial engine.
"""
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import uuid
import zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, Response, g, jsonify, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from dashboard_sessions import csrf_valid

payment_evidence = Blueprint("sbi_payment_evidence", __name__)

HEADERS = ("Description", "SOL ID", "Credit Amount")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 100_000
MAX_ROWS = 30000
MAX_PREVIEW = 50
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
RECEIPT_RE = re.compile(r"^[a-f0-9]{32}$")
BAD_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store():
    raw = os.environ.get("SBI_PAYMENT_EVIDENCE_DIR", "")
    base = Path(raw)
    if not raw or not base.is_absolute() or base.is_symlink() or not base.is_dir():
        raise OSError("Private payment evidence storage not configured")
    info = base.stat()
    if (info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise OSError("Private payment evidence permissions are invalid")
    return base


def _connection(base):
    dbpath = base / "receipts.sqlite3"
    if dbpath.is_symlink():
        raise OSError("Unsafe receipt index")
    conn = sqlite3.connect(str(dbpath), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS receipts ("
        "id TEXT PRIMARY KEY, owner_uid TEXT NOT NULL, "
        "filename TEXT NOT NULL, source_name TEXT NOT NULL, "
        "sha256 TEXT NOT NULL, created_utc TEXT NOT NULL,"
        "source_rows INTEGER NOT NULL, valid_rows INTEGER NOT NULL,"
        "review_rows INTEGER NOT NULL, credit_total TEXT NOT NULL,"
        "status TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_receipts_owner_hash "
        "ON receipts(owner_uid, sha256)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_receipts_owner_date "
        "ON receipts(owner_uid, created_utc DESC)"
    )
    conn.commit()
    os.chmod(dbpath, 0o600)
    return conn


def _zip_guard(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1500:
                raise ValueError("Excel archive has too many parts")
            if sum(e.file_size for e in entries) > MAX_ZIP_UNCOMPRESSED:
                raise ValueError("Excel workbook expands beyond the size limit")
            for entry in entries:
                name = entry.filename
                if (name.startswith("/") or "\\" in name or
                    ".." in Path(name).parts or
                    (entry.compress_size and
                     entry.file_size > max(1_000_000, entry.compress_size * 1000))):
                    raise ValueError("Unsafe Excel archive structure")
            if "[Content_Types].xml" not in archive.namelist():
                raise ValueError("Not a valid Excel .xlsx workbook")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("Invalid or unsupported Excel file; use .xlsx template") from exc


def _norm_description(cell):
    if cell.data_type == "f":
        return "", ["FORMULA_NOT_ALLOWED"]
    value = cell.value
    if value is None or not str(value).strip():
        return "", ["DESCRIPTION_MISSING"]
    desc = str(value).strip()
    if len(desc) > 1000:
        return desc[:1000], ["DESCRIPTION_TOO_LONG"]
    return desc, []


def _norm_sol(cell):
    if cell.data_type == "f":
        return "", ["FORMULA_NOT_ALLOWED"]
    value = cell.value
    if value is None or not str(value).strip():
        return "", ["SOL_ID_MISSING"]
    if isinstance(value, bool):
        return "", ["SOL_ID_INVALID"]
    if isinstance(value, (int, float)):
        if not float(value).is_integer():
            return str(value), ["SOL_ID_INVALID"]
        return str(int(value)), ["SOL_ID_MUST_BE_TEXT_REVIEW_LEADING_ZEROS"]
    sol = str(value).strip()
    if len(sol) > 40 or not re.fullmatch(r"[A-Za-z0-9_-]+", sol):
        return sol[:40], ["SOL_ID_INVALID"]
    return sol, []


def _norm_credit(cell):
    if cell.data_type == "f":
        return "", ["FORMULA_NOT_ALLOWED"]
    value = cell.value
    if isinstance(value, bool) or value is None:
        return "", ["CREDIT_AMOUNT_INVALID"]
    cleaned = str(value).replace(",", "").strip()
    if cleaned.startswith("₹"):
        cleaned = cleaned[1:].strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return "", ["CREDIT_AMOUNT_INVALID"]
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        return "", ["CREDIT_AMOUNT_PRECISION_INVALID"]
    if abs(amount) >= Decimal("10000000000000"):
        return "", ["CREDIT_AMOUNT_OUT_OF_RANGE"]
    flags = []
    if amount <= 0:
        flags.append("NON_POSITIVE_CREDIT_REVIEW")
    return format(amount.quantize(Decimal("0.01")), ".2f"), flags


def _parse(data):
    _zip_guard(data)
    try:
        workbook = load_workbook(
            io.BytesIO(data), read_only=True,
            data_only=False, keep_links=False,
        )
    except Exception as exc:
        raise ValueError("Cannot read Excel workbook; use fixed .xlsx template") from exc
    try:
        sheet = workbook["PAYMENT EVIDENCE"] if "PAYMENT EVIDENCE" in workbook else workbook.active
        header = list(next(sheet.iter_rows(min_row=1, max_row=1, max_col=4), ()))
        actual = tuple(str(c.value).strip() if c.value is not None else "" for c in header[:3])
        if actual != HEADERS or (len(header) > 3 and header[3].value not in (None, "")):
            raise ValueError(
                "Incorrect headers. A1=Description, B1=SOL ID, C1=Credit Amount; "
                "remove other columns and use the fixed template."
            )
        total = Decimal("0")
        reviewed = valid = count = 0
        issue_counts = Counter()
        duplicates = set()
        preview = []
        for row_number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=4), start=2):
            if all(cell.value in (None, "") for cell in cells):
                continue
            count += 1
            if count > MAX_ROWS:
                raise ValueError("More than 30,000 evidence rows; split the workbook")
            desc, f1 = _norm_description(cells[0])
            sol, f2 = _norm_sol(cells[1])
            credit, f3 = _norm_credit(cells[2])
            issues = f1 + f2 + f3
            if cells[3].value not in (None, ""):
                issues.append("EXTRA_COLUMN_NOT_ALLOWED")
            key = (desc, sol, credit)
            if key in duplicates:
                issues.append("REPEATED_SOURCE_ROW_REVIEW")
            else:
                duplicates.add(key)
            if issues:
                reviewed += 1
                issue_counts.update(issues)
            else:
                valid += 1
                total += Decimal(credit)
            if len(preview) < MAX_PREVIEW:
                preview.append({
                    "excel_row": row_number,
                    "description": desc,
                    "sol_id": sol,
                    "credit_amount": credit,
                    "review_flags": sorted(set(issues)),
                    "status": "REVIEW" if issues else "VALID",
                })
        if count == 0:
            raise ValueError("No payment evidence rows found under the fixed header")
        return {
            "source_rows": count, "valid_rows": valid,
            "review_rows": reviewed, "valid_credit_total": format(total, ".2f"),
            "review_flag_counts": dict(issue_counts),
            "preview": preview,
            "preview_limit": MAX_PREVIEW,
            "header": list(HEADERS),
        }
    finally:
        workbook.close()


def _metadata(row):
    return {
        "receipt_id": row["id"],
        "source_name": row["source_name"],
        "source_sha256": row["sha256"],
        "created_utc": row["created_utc"],
        "source_rows": row["source_rows"],
        "valid_rows": row["valid_rows"],
        "review_rows": row["review_rows"],
        "valid_credit_total": row["credit_total"],
        "status": row["status"],
        "financial_writes": False,
        "reconciliation_executed": False,
    }


@payment_evidence.get("/api/payment-evidence/template")
def download_template():
    wb = Workbook()
    sheet = wb.active
    sheet.title = "PAYMENT EVIDENCE"
    sheet.append(list(HEADERS))
    sheet.freeze_panes = "A2"
    for col, width in (("A", 60), ("B", 20), ("C", 22)):
        sheet.column_dimensions[col].width = width
        cell = sheet[f"{col}1"]
        cell.fill = PatternFill("solid", fgColor="15344D")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 28
    for row in range(2, 202):
        sheet[f"B{row}"].number_format = "@"
        sheet[f"C{row}"].number_format = "#,##0.00"
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output, as_attachment=True,
        download_name="SBI_Payment_Evidence_Fixed_Header_Template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@payment_evidence.post("/api/payment-evidence/upload")
def upload_evidence():
    request.max_content_length = MAX_REQUEST_BYTES
    if not csrf_valid():
        return jsonify(error="Same-origin session CSRF check failed"), 403
    if not request.mimetype == "multipart/form-data":
        return jsonify(error="Upload must use multipart Excel file"), 415
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="Choose an Excel file"), 400
    name = (uploaded.filename or "").replace("\\", "/").split("/")[-1].strip()
    if not name.lower().endswith(".xlsx") or len(name) > 120:
        return jsonify(error="Use .xlsx format; old .xls files require conversion"), 422
    payload = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        return jsonify(error="Excel file exceeds 8 MiB size limit"), 413
    try:
        parsed = _parse(payload)
    except ValueError as exc:
        return jsonify(error=str(exc), fixed_headers=list(HEADERS)), 422
    try:
        base = _store()
        digest = hashlib.sha256(payload).hexdigest()
        owner = str(g.dil_user.uid)
        with closing(_connection(base)) as conn:
            found = conn.execute(
                "SELECT id FROM receipts WHERE owner_uid=? AND sha256=?",
                (owner, digest),
            ).fetchone()
            if found:
                return jsonify(error="This evidence workbook was already staged",
                               receipt_id=found["id"]), 409
        receipt_id = uuid.uuid4().hex
        leaf = receipt_id + ".xlsx"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(base / leaf), flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            with closing(_connection(base)) as conn, conn:
                conn.execute(
                    "INSERT INTO receipts "
                    "(id,owner_uid,filename,source_name,sha256,created_utc,"
                    "source_rows,valid_rows,review_rows,credit_total,status)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (receipt_id, owner, leaf, name, digest, _utc(),
                     parsed["source_rows"], parsed["valid_rows"],
                     parsed["review_rows"], parsed["valid_credit_total"],
                     "REVIEW_REQUIRED" if parsed["review_rows"] else "STAGED_FOR_REVIEW"),
                )
        except Exception:
            (base / leaf).unlink(missing_ok=True)
            raise
        return jsonify(
            **parsed, receipt_id=receipt_id,
            source_sha256=digest,
            staging_status="REVIEW_REQUIRED" if parsed["review_rows"] else "STAGED_FOR_REVIEW",
            financial_writes=False,
            reconciliation_executed=False,
            financial_data_connected=False,
        ), 201
    except sqlite3.IntegrityError:
        return jsonify(error="Duplicate evidence workbook; no changes made"), 409
    except (OSError, sqlite3.Error):
        return jsonify(error="Private payment staging storage unavailable"), 503


@payment_evidence.get("/api/payment-evidence/uploads")
def list_evidence():
    try:
        with closing(_connection(_store())) as conn:
            records = conn.execute(
                "SELECT * FROM receipts WHERE owner_uid=? "
                "ORDER BY created_utc DESC, id DESC LIMIT 20",
                (str(g.dil_user.uid),),
            ).fetchall()
        return jsonify(
            evidence=[_metadata(item) for item in records],
            financial_writes=False, reconciliation_executed=False,
        )
    except (OSError, sqlite3.Error):
        return jsonify(error="Private payment staging storage unavailable"), 503


@payment_evidence.get("/api/payment-evidence/uploads/<receipt_id>")
def receipt_preview(receipt_id):
    if not RECEIPT_RE.fullmatch(receipt_id):
        return jsonify(error="Invalid evidence receipt ID"), 404
    try:
        base = _store()
        with closing(_connection(base)) as conn:
            row = conn.execute(
                "SELECT * FROM receipts WHERE id=? AND owner_uid=?",
                (receipt_id, str(g.dil_user.uid)),
            ).fetchone()
        if row is None:
            return jsonify(error="Evidence receipt not found"), 404
        if row["filename"] != receipt_id + ".xlsx":
            return jsonify(error="Evidence storage contract invalid"), 503
        path = base / row["filename"]
        if path.is_symlink() or not path.is_file():
            return jsonify(error="Stored evidence unavailable"), 503
        contents = path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != row["sha256"]:
            return jsonify(error="Stored evidence digest changed"), 503
        parsed = _parse(contents)
        return jsonify({**_metadata(row), **parsed})
    except ValueError:
        return jsonify(error="Stored evidence workbook invalid"), 503
    except (OSError, sqlite3.Error):
        return jsonify(error="Private payment staging storage unavailable"), 503
