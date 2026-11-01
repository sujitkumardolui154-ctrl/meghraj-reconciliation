"""SBI_AUTHORIZED_CREDIT_REPORT_V1.

Inert until the main app explicitly calls create_credit_note_blueprint(authorize).
The authorize callback must return literal True for the current request.
Do not attach without verified application authentication and permission tests.
"""
import csv
import hashlib
import io
import json
import os
import re
from html import escape
from urllib.parse import urlparse
from flask import Blueprint, Response, abort, jsonify

_ALLOWED_BUCKET = "meghraj-sbi-reports-private-109590290120"
_EXPECTED_HEADER_COUNT = 18


def _read_snapshot():
    from google.cloud import storage
    uri = os.environ.get("SBI_CREDIT_GCS_PREFIX", "")
    parts = urlparse(uri)
    key = parts.path.strip("/")
    if parts.scheme != "gs" or parts.netloc != _ALLOWED_BUCKET:
        raise ValueError("Private report bucket mismatch")
    if not re.fullmatch(r"credit-note/snapshot-\d{8}T\d{6}Z", key):
        raise ValueError("Unapproved report snapshot path")
    client = storage.Client(project="meghraj-reconciliation")
    bucket = client.bucket(parts.netloc)
    man = json.loads(bucket.blob(key + "/manifest.json").download_as_bytes(timeout=30))
    raw = bucket.blob(key + "/report.csv").download_as_bytes(timeout=60)
    conflicts = bucket.blob(key + "/conflicts.csv").download_as_bytes(timeout=30)
    if hashlib.sha256(raw).hexdigest() != man.get("report_sha256"):
        raise ValueError("CREDIT NOTE snapshot hash mismatch")
    if man.get("release_status") != "REVIEW_REQUIRED":
        raise ValueError("Unexpected release classification")
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = next(rows, [])
    if len(header) != _EXPECTED_HEADER_COUNT:
        raise ValueError("Invalid report column width")
    if header[16].strip().lower().startswith("payment received") is False:
        raise ValueError("Column U position not verified")
    if header[17] != "Credi note":
        raise ValueError("Column R header mismatch")
    count = 0
    for line in rows:
        if len(line) != _EXPECTED_HEADER_COUNT:
            raise ValueError("Report row has unexpected column width")
        count += 1
    if count != man.get("all_invoice_rows"):
        raise ValueError("Manifest row count mismatch")
    if not (isinstance(man.get("credit_note_unique_invoices"), int)
            and isinstance(man.get("credit_note_confirmed_unique_invoices"), int)
            and isinstance(man.get("conflicting_duplicate_invoice_numbers"), int)):
        raise ValueError("Missing verified report counts")
    if man["credit_note_confirmed_unique_invoices"] > man["credit_note_unique_invoices"]:
        raise ValueError("Conflicting report totals")
    return man, raw, conflicts


def create_credit_note_blueprint(authorize):
    """Return a Blueprint; never assume an authenticated session."""
    if not callable(authorize):
        raise ValueError("Explicit application authorization callback required")
    bp = Blueprint("sbi_credit_note_auth", __name__)

    @bp.before_request
    def _enforce_authorization():
        try:
            allowed = authorize()
        except Exception:
            abort(403)
        if allowed is not True:
            abort(403)

    @bp.get("/reports/credit-note/summary")
    def summary():
        try:
            meta, _, _ = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        fields = ("all_invoice_rows", "credit_note_unique_invoices",
                  "credit_note_confirmed_unique_invoices",
                  "conflicting_duplicate_invoice_numbers",
                  "completed_import_rows", "report_sha256")
        result = {f: meta.get(f) for f in fields}
        result.update(release_status="REVIEW_REQUIRED", snapshot_only=True,
                      import_completeness="NOT_CERTIFIED",
                      financial_execution="RESTRICTED")
        response = jsonify(result)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.get("/reports/credit-note.csv")
    @bp.get("/reports/credit-note/conflicts.csv")
    def csv_report():
        from flask import request
        try:
            _, report, review = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        conflict_request = request.path.endswith("/conflicts.csv")
        raw = review if conflict_request else report
        name = "SBI_CREDIT_NOTE_CONFLICT_REVIEW.csv" if conflict_request else "SBI_CREDIT_NOTE_ALL_INVOICES.csv"
        return Response(raw, mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="' + name + '"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-SBI-Report-Status": "REVIEW_REQUIRED"})

    @bp.get("/reports/credit-note/ui")
    def ui():
        try:
            meta, _, _ = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        numbers = (meta["all_invoice_rows"], meta["credit_note_unique_invoices"],
                   meta["credit_note_confirmed_unique_invoices"],
                   meta["conflicting_duplicate_invoice_numbers"])
        vals = [escape(str(number)) for number in numbers]
        html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>SBI CREDIT NOTE — Read-only review</title>'
                '<main><h2>CREDIT NOTE Report — Verified Snapshot</h2>'
                '<p>All invoice rows: ' + vals[0] + '</p>'
                '<p>Observed CREDIT NOTE invoices: ' + vals[1] + '</p>'
                '<p>Unambiguous CREDIT NOTE invoices: ' + vals[2] + '</p>'
                '<p>Conflicting invoice numbers: ' + vals[3] + '</p>'
                '<p><a href="/reports/credit-note.csv">Download report CSV</a></p>'
                '<p><a href="/reports/credit-note/conflicts.csv">Download conflict review</a></p>'
                '<p>REVIEW_REQUIRED. Imports not certified. Financial execution restricted.</p>'
                '</main></html>')
        return Response(html, mimetype="text/html", headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'",
            "X-Frame-Options": "DENY"})

    return bp
