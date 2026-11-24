"""Opt-in PostgreSQL payment-evidence bridge for a *separate* SBI staging app.

This module does not authenticate users. It wraps the existing Flask upload view,
which must continue to enforce Firebase session, owner, and original CSRF rules.
A durable SQLite receipt precedes the PG write; a duplicate-retry can recover an
interrupted PG delivery without mutating the original immutable evidence.

Do NOT enable on the production app. Only the isolated QA container/database is
permitted by the enforced target guard. No reconciliation/allocations run here.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import re
import uuid
import zipfile
from decimal import Decimal, InvalidOperation
from functools import wraps
from xml.etree import ElementTree as ET

from flask import jsonify, request

QA_DATABASE = "sbi_ft04g_clean_0e858f93"
QA_HOST = "sbi-synthetic-postgres-38-31"
QA_WRITER = "sbi_ft04q_ingest"
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 50_000
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COLS = ("Description", "SOL ID", "Credit Amount")


class ContractError(ValueError):
    """Reject source data that cannot be faithfully and safely imported."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_row(row: dict[str, str]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _credit_paise(text: str) -> int:
    try:
        v = Decimal(str(text).strip()) * 100
        if not v.is_finite() or v != v.to_integral_value() or v <= 0 or v > 10**15:
            raise ContractError("Invalid positive payment amount or excess precision")
        return int(v)
    except (ValueError, InvalidOperation) as e:
        raise ContractError("Invalid positive payment amount") from e


def _safe_sheet_path(archive: zipfile.ZipFile) -> str:
    """Resolve the first workbook sheet, not blindly sheet1.xml."""
    names = set(archive.namelist())
    for n in ("[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
        if n not in names:
            raise ContractError("Invalid Excel structure")
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = workbook.findall(".//x:sheets/x:sheet", NS)
    if not sheets:
        raise ContractError("Excel contains no worksheet")
    relid = sheets[0].get("{%s}id" % REL_NS)
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = None
    for relation in relations.findall("{%s}Relationship" % PKG_REL_NS):
        if relation.get("Id") == relid:
            if relation.get("TargetMode") == "External":
                raise ContractError("External workbook target is unsupported")
            target = relation.get("Target", "")
            break
    if not target:
        raise ContractError("Worksheet relationship missing")
    resolved = (target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target)))
    if not resolved.startswith("xl/") or resolved not in names:
        raise ContractError("Unsafe or missing worksheet target")
    return resolved


def _cell_value(cell: ET.Element, strings: list[str]) -> str:
    if cell.find("x:f", NS) is not None:
        raise ContractError("Formula cells are not accepted as payment evidence")
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        return "".join((x.text or "") for x in cell.findall(".//x:is//x:t", NS))
    v = cell.findtext("x:v", default="", namespaces=NS)
    if kind == "s":
        try:
            return strings[int(v)]
        except (ValueError, IndexError) as e:
            raise ContractError("Broken shared string index") from e
    if kind in ("e", "b"):
        raise ContractError("Error/boolean cell is invalid payment evidence")
    return v


def payment_rows(payload: bytes) -> list[tuple[int, dict[str, str], int]]:
    """Read all validated three-column XLSX data rows; preserve source row IDs."""
    if len(payload) > MAX_BYTES or len(payload) < 8:
        raise ContractError("Excel must be between 8 bytes and 8 MiB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as e:
        raise ContractError("Invalid XLSX archive") from e
    with archive:
        info = archive.infolist()
        if len(info) > 10000 or sum(z.file_size for z in info) > 128 * 1024 * 1024:
            raise ContractError("Unsupported XLSX archive size")
        if any(z.flag_bits & 1 for z in info):
            raise ContractError("Encrypted XLSX is unsupported")
        sheet = _safe_sheet_path(archive)
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join((t.text or "") for t in si.findall(".//x:t", NS)) for si in root.findall("x:si", NS)]
        root = ET.fromstring(archive.read(sheet))
        seen = set()
        headers = None
        rows = []
        last_row = 0
        for element in root.findall(".//x:sheetData/x:row", NS):
            try:
                n = int(element.get("r", "0"))
            except ValueError as e:
                raise ContractError("Invalid source Excel row number") from e
            if n <= last_row or n < 1:
                raise ContractError("Non-monotonic source row numbers")
            last_row = n
            cells = ["", "", ""]
            for c in element.findall("x:c", NS):
                location = c.get("r", "")
                match = re.fullmatch(r"([A-Z]+)([0-9]+)", location)
                if not match or int(match.group(2)) != n or location in seen:
                    raise ContractError("Ambiguous spreadsheet cell coordinate")
                seen.add(location)
                letters = match.group(1)
                index = 0
                for ch in letters:
                    index = index * 26 + ord(ch) - 64
                value = _cell_value(c, strings)
                if index > 3:
                    if value.strip():
                        raise ContractError("Unexpected data outside approved three-column format")
                    continue
                cells[index - 1] = value
            if n == 1:
                headers = cells
                if tuple(headers) != COLS:
                    raise ContractError("Header mismatch: Description | SOL ID | Credit Amount")
                continue
            if not any(v.strip() for v in cells):
                continue
            if headers is None:
                raise ContractError("Missing row-one header")
            if not cells[0].strip():
                raise ContractError("Blank payment narration in row %s" % n)
            amount = _credit_paise(cells[2])
            row = dict(zip(COLS, cells))
            rows.append((n, row, amount))
            if len(rows) > MAX_ROWS:
                raise ContractError("Too many payment rows")
        if headers is None or not rows:
            raise ContractError("No valid payment evidence rows")
    return rows


def _db_connect():
    """The guard intentionally makes this module incapable of writing main DB."""
    if os.environ.get("SBI_PG_PAYMENT_BRIDGE_ENABLED") != "staging-only":
        raise RuntimeError("Staging bridge is disabled")
    if (os.environ.get("PGHOST") != QA_HOST or
        os.environ.get("PGDATABASE") != QA_DATABASE or
        os.environ.get("PGUSER") != QA_WRITER):
        raise RuntimeError("Staging PostgreSQL identity mismatch")
    try:
        import psycopg as dbdriver
    except ImportError:
        import psycopg2 as dbdriver
    conn = dbdriver.connect(connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute("""SELECT current_database(),current_user,
            has_table_privilege(current_user,'sbi.payments','INSERT'),
            has_table_privilege(current_user,'sbi.payments','UPDATE'),
            has_table_privilege(current_user,'sbi.payments','DELETE')""")
        if tuple(cur.fetchone()) != (QA_DATABASE, QA_WRITER, True, False, False):
            conn.close()
            raise RuntimeError("PostgreSQL writer privileges not stage-only")
    return conn


def _existing(cur, digest: str, expected: list[tuple[int, dict[str, str], int]]) -> bool:
    cur.execute("""SELECT b.id FROM sbi.import_batches b
        WHERE b.source_system='excel' AND b.source_kind='payment'
        AND b.source_sha256=%s""", (digest,))
    batches = cur.fetchall()
    if not batches:
        return False
    if len(batches) != 1:
        raise RuntimeError("Ambiguous source batch")
    cur.execute("""SELECT r.source_row_number,r.row_sha256,p.credit_paise,
        p.description,p.sol_id FROM sbi.payment_source_rows r
        JOIN sbi.payments p ON p.source_row_id=r.id
        WHERE r.batch_id=%s ORDER BY r.source_row_number""", (batches[0][0],))
    actual = [(int(n), str(h), int(v), str(d), s or "") for n, h, v, d, s in cur.fetchall()]
    wanted = [(n, _sha(_json_row(row).encode("utf-8")), paise,
               row["Description"], row["SOL ID"]) for n, row, paise in expected]
    if actual != wanted:
        raise RuntimeError("Prior source evidence differs: manual review required")
    return True


def persist_payment(payload: bytes, original_parser) -> str:
    """Commit a new batch or verify identical source row evidence, never update."""
    parsed = original_parser(payload)
    rows = payment_rows(payload)
    # We don't guess which source records failed the existing application's
    # validation. Partial imports need a row-level approval mapping first.
    if parsed.get("review_rows") or parsed.get("valid_rows") != len(rows):
        raise ContractError("Existing parser marked some rows for review; no PostgreSQL write")
    digest = _sha(payload)
    conn = _db_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                cur.execute("SET LOCAL lock_timeout = '2s'")
                if _existing(cur, digest, rows):
                    return "ALREADY_RECORDED"
                batch_id = str(uuid.uuid4())
                cur.execute("""INSERT INTO sbi.import_batches
                    (id,source_system,source_kind,original_file_name,source_sha256)
                    VALUES (%s,'excel','payment',%s,%s)""",
                    (batch_id, "stage-payment-evidence.xlsx", digest))
                for number, row, paise in rows:
                    source_id = str(uuid.uuid4())
                    original = _json_row(row)
                    cur.execute("""INSERT INTO sbi.payment_source_rows
                        (id,batch_id,source_row_number,original_values,row_sha256)
                        VALUES (%s,%s,%s,%s::jsonb,%s)""",
                        (source_id, batch_id, number, original, _sha(original.encode("utf-8"))))
                    cur.execute("""INSERT INTO sbi.payments
                        (id,source_row_id,description,sol_id,credit_paise)
                        VALUES (%s,%s,%s,%s,%s)""",
                        (str(uuid.uuid4()), source_id, row["Description"], row["SOL ID"], paise))
        return "COMMITTED"
    finally:
        conn.close()


def attach(app):
    """Replace just the registered POST view in a *staging* Flask app."""
    if os.environ.get("SBI_PG_PAYMENT_BRIDGE_ENABLED") != "staging-only":
        raise RuntimeError("Stage-only bridge must be enabled explicitly")
    if (os.environ.get("PGHOST"), os.environ.get("PGDATABASE"), os.environ.get("PGUSER")) != (QA_HOST, QA_DATABASE, QA_WRITER):
        raise RuntimeError("Unsafe database target")
    import payment_evidence_upload as original_module
    candidates = [r for r in app.url_map.iter_rules()
                  if r.rule == "/api/payment-evidence/upload" and "POST" in r.methods]
    if len(candidates) != 1:
        raise RuntimeError("Exactly one original payment upload route is required")
    endpoint = candidates[0].endpoint
    original_view = app.view_functions[endpoint]
    if getattr(original_view, "_sbi_pg_bridge", False):
        raise RuntimeError("Bridge already installed")

    @wraps(original_view)
    def wrapped(*args, **kwargs):
        # This executes the original Flask authentication, CSRF, parsing, SQLite
        # receipt and duplicate logic. The bridge never circumvents them.
        response = app.make_response(original_view(*args, **kwargs))
        if response.status_code not in (200, 201, 409):
            return response
        if response.status_code == 409:
            msg = (response.get_json(silent=True) or {}).get("error", "")
            if not isinstance(msg, str) or not any(
                text in msg.lower() for text in ("already staged", "duplicate evidence workbook")
            ):
                return response
        uploaded = request.files.get("file")
        if uploaded is None:
            return response
        try:
            uploaded.stream.seek(0)
            payload = uploaded.stream.read(MAX_BYTES + 1)
            state = persist_payment(payload, original_module._parse)
        except ContractError:
            # Receipt is already durably staged in SQLite: leave it for owner
            # review; do not pretend any database record was reconciled.
            return jsonify(error="PG_STAGE_SOURCE_REVIEW", postgres_ingested=False), 422
        except Exception:
            app.logger.exception("Staging PostgreSQL delivery failed; original SQLite receipt retained")
            return jsonify(error="PG_STAGE_SYNC_PENDING", postgres_ingested=False), 503
        if response.status_code == 409:
            # Preserve the original HTTP duplicate semantics.
            response.headers["X-QA-Postgres-Status"] = state
            return response
        response.headers["X-QA-Postgres-Status"] = state
        return response

    wrapped._sbi_pg_bridge = True
    app.view_functions[endpoint] = wrapped
    return endpoint
