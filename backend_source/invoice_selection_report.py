"""Strict read-only lookup for arbitrary-order uploaded invoice-number lists.

This never treats a user-supplied ID as invoice evidence, never allocates
payments, and never replaces missing source fields with fabricated amounts.
The caller must enforce authenticated report-viewer authorization before
calling the private Cloud Run endpoint.
"""
from __future__ import annotations

import logging
from collections import defaultdict

MAX_SELECTION = 2000
PAYMENT_KINDS = {"unpaid", "ok", "error-value"}


def select_verified_invoices(requested, verified_rows):
    """Filter already verified v1.4.2 baseline + completed import records.

    Return exact-match rows in requested order and an independent review list.
    Conflicting or duplicate database matches are excluded and require review.
    """
    if (not isinstance(requested, list)
        or not 1 <= len(requested) <= MAX_SELECTION
        or any(not isinstance(value, str)
               or not 0 < len(value) <= 128
               or not value.strip() == value
               or any(ord(char) < 32 for char in value)
               for value in requested)
        or len(set(requested)) != len(requested)):
        raise ValueError("Provide 1 to 2000 distinct exact text invoice numbers")

    wanted = set(requested)
    matches = defaultdict(list)
    for row in verified_rows:
        number = row.get("invoice_no")
        if number not in wanted:
            continue
        matches[number].append(row)

    found, review = [], []
    for number in requested:
        candidates = matches[number]
        if not candidates:
            review.append({"invoice_no": number, "reason": "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE"})
            continue
        if len(candidates) > 1:
            review.append({"invoice_no": number, "reason": "DUPLICATE_DATABASE_INVOICE_MATCH"})
            continue
        row = candidates[0]
        original = row.get("export_values")
        kind = row.get("payment_report")
        if (not isinstance(original, list)
            or len(original) != 53
            or not all(isinstance(x, str) for x in original)
            or original[12] != number
            or kind not in PAYMENT_KINDS
            or type(row.get("balance_valid")) is not bool):
            review.append({"invoice_no": number, "reason": "DATABASE_SOURCE_CONFLICT"})
            continue
        found.append({
            "invoice_no": number,
            "values": original,
            "payment_kind": kind,
            "balance_review": not row["balance_valid"],
            "source_sheet": row.get("source_sheet", ""),
            "source_row": row.get("source_row"),
        })
    if len(found) + len(review) != len(requested):
        raise ValueError("Invoice lookup accountability mismatch")
    return {"matches": found, "review": review,
            "requested_count": len(requested),
            "matched_count": len(found),
            "review_count": len(review)}


def handle_invoice_selection(request):
    """Private Cloud Run route; Firebase report authorization is at gateway."""
    from flask import jsonify
    if request.method != "POST":
        return jsonify(error="Method not allowed"), 405
    if request.content_length is None or request.content_length > 512 * 1024:
        return jsonify(error="Invoice selection payload too large"), 413
    if not request.is_json:
        return jsonify(error="JSON request required"), 415
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body.keys()) != {"invoice_numbers"}:
        return jsonify(error="Invoice number selection required"), 422
    try:
        invoice_numbers = body["invoice_numbers"]
        # Reject invalid selection before any financial report reads.
        select_verified_invoices(invoice_numbers, [])
    except (ValueError, TypeError):
        return jsonify(error="Invalid or duplicate invoice numbers"), 422

    try:
        from google.cloud import firestore
        from report_api import DATASET, load_report_rows_v142
        db = firestore.Client(project="meghraj-reconciliation")
        baseline, imported = load_report_rows_v142(db)
        result = select_verified_invoices(invoice_numbers, baseline + imported)
        response = jsonify(
            version="invoice-selection-v1",
            dataset=DATASET,
            source_kind="VERIFIED_READ_ONLY_REPORT_SOURCE",
            reconciliation_executed=False,
            financial_writes=False,
            database_updated=False,
            **result,
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        logging.exception("Verified invoice selection source unavailable")
        return jsonify(error="Verified invoice source unavailable; report stopped"), 503
