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



def _validate_snapshot_counts(raw, manifest):
    """Verify report financial-status counts without relying on manifest totals.

    Only the original Invoice No and the derived CREDIT NOTE marker are read.
    Every mismatch fails closed. This is integrity checking, not settlement.
    """
    if not isinstance(manifest, dict):
        raise ValueError("Invalid report manifest")
    try:
        text = raw.decode("utf-8-sig")
    except (UnicodeError, AttributeError) as exc:
        raise ValueError("Invalid report encoding") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, [])
    if len(header) != _EXPECTED_HEADER_COUNT or header[8] != "Invoice No":
        raise ValueError("Invalid report header")
    if not header[16].strip().lower().startswith("payment received"):
        raise ValueError("Column U position not verified")
    if header[17] != "Credi note":
        raise ValueError("Column R header mismatch")

    invoice_states = {}
    marked = set()
    row_count = 0
    for row in reader:
        if len(row) != _EXPECTED_HEADER_COUNT:
            raise ValueError("Report row has unexpected column width")
        row_count += 1
        invoice = row[8].strip()
        marker = row[17]
        if marker not in ("", "CREDIT NOTE"):
            raise ValueError("Unknown CREDIT NOTE marker")
        if not invoice:
            continue  # blank invoice numbers are counted, not invented
        state = marker == "CREDIT NOTE"
        invoice_states.setdefault(invoice, set()).add(state)
        if state:
            marked.add(invoice)

    conflicted = {
        invoice for invoice, states in invoice_states.items()
        if len(states) > 1
    }
    actual = {
        "all_invoice_rows": row_count,
        "credit_note_unique_invoices": len(marked),
        "credit_note_confirmed_unique_invoices": len(marked - conflicted),
        "conflicting_duplicate_invoice_numbers": len(conflicted),
    }
    for name, value in actual.items():
        expected = manifest.get(name)
        if type(expected) is not int or expected != value:
            raise ValueError("CREDIT NOTE manifest mismatch: " + name)
    if manifest.get("release_status") != "REVIEW_REQUIRED":
        raise ValueError("Unexpected release classification")
    return actual

def _verify_conflicts_digest(raw, manifest):
    """Require an authenticated snapshot manifest to cover the conflict CSV.

    A missing or invalid digest never authorizes confidential conflict-review
    output. This guard uses only raw bytes and a SHA-256 field; no invoice data.
    """
    digest = manifest.get("conflicts_sha256") if isinstance(manifest, dict) else None
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("CREDIT NOTE conflict-review SHA-256 missing or invalid")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("CREDIT NOTE conflict-review hash mismatch")


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
    _validate_snapshot_counts(raw, man)
    # Never release conflicts.csv without a validated manifest digest.
    # Historical snapshots without this field remain unavailable until
    # independently regenerated and verified; no silent hash bypass.
    _verify_conflicts_digest(conflicts, man)
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
