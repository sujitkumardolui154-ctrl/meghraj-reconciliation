"""CREDIT NOTE read-only HTTP response builder.

Authentication must be enforced by the existing report router
before invoking this module.
"""

from flask import Response, jsonify
from invoice_source_schema import HEADERS_53
from credit_note_csv import build_credit_note_csv


def build_credit_note_response(kind, source_rows):
    """Build an authenticated-router-ready report response."""

    if kind not in ("csv", "summary"):
        raise ValueError("Unsupported CREDIT NOTE report type")

    data, summary = build_credit_note_csv(
        HEADERS_53,
        source_rows,
    )

    if kind == "summary":
        response = jsonify(summary)
    else:
        response = Response(
            data,
            status=200,
            mimetype="text/csv",
        )
        response.headers["Content-Disposition"] = (
            'attachment; filename="SBI_CREDIT_NOTE.csv"'
        )

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return response
