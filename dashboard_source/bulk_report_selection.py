"""In-memory combined Bulk Report built from exact, verified DB invoice matches.

The uploaded workbook supplies ONLY invoice IDs; all 53-column rows must come
from the protected verified read-only backend. Missing/conflicting IDs go to a
separate lookup review worksheet. No financial writes or reconciliation.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from invoice_source_schema import HEADERS_53
from sbi_reporting_bundle import csv_bytes

GROUPS = ("all-invoices", "unpaid", "ok", "error-value", "balance-review")
LOOKUP_HEADERS = ("Invoice No", "Reason")
INPUT_REVIEW_HEADERS = ("Source Row", "Invoice No", "Review Flag")
ALLOWED_LOOKUP_REASONS = frozenset((
    "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE",
    "DUPLICATE_DATABASE_INVOICE_MATCH",
    "DATABASE_SOURCE_CONFLICT",
))


def build_selection_zip(selection, backend_result, upload_sha256: str):
    if not isinstance(backend_result, dict):
        raise ValueError("Verified invoice lookup response is missing")
    if any(backend_result.get(key) is not False for key in (
        "financial_writes", "reconciliation_executed", "database_updated"
    )):
        raise ValueError("Verified invoice lookup financial-safety flags invalid")
    if (backend_result.get("version") != "invoice-selection-v1"
        or backend_result.get("source_kind") != "VERIFIED_READ_ONLY_REPORT_SOURCE"
        or not isinstance(backend_result.get("dataset"), str)
        or not backend_result["dataset"]
        or not isinstance(backend_result.get("matches"), list)
        or not isinstance(backend_result.get("review"), list)):
        raise ValueError("Verified invoice lookup response is invalid")

    requested = selection.invoice_numbers
    ids = set(requested)
    if (backend_result.get("requested_count") != len(requested)
        or backend_result.get("matched_count") != len(backend_result["matches"])
        or backend_result.get("review_count") != len(backend_result["review"])
        or len(backend_result["matches"]) + len(backend_result["review"]) != len(requested)):
        raise ValueError("Invoice lookup does not account for every requested ID")

    resolved = set()
    groups = {kind: [] for kind in GROUPS}
    for row in backend_result["matches"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid verified invoice row")
        number, values = row.get("invoice_no"), row.get("values")
        kind = row.get("payment_kind")
        if (number not in ids or number in resolved
            or not isinstance(values, list) or len(values) != 53
            or not all(isinstance(v, str) for v in values)
            or values[12] != number
            or kind not in ("unpaid", "ok", "error-value")
            or type(row.get("balance_review")) is not bool):
            raise ValueError("Selected invoice row has incomplete or conflicting source")
        resolved.add(number)
        groups["all-invoices"].append(values)
        groups[kind].append(values)
        if row["balance_review"]:
            groups["balance-review"].append(values)

    lookup_review = []
    for row in backend_result["review"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid lookup review")
        number, reason = row.get("invoice_no"), row.get("reason")
        if (number not in ids or number in resolved
            or reason not in ALLOWED_LOOKUP_REASONS):
            raise ValueError("Unexpected or duplicate lookup review")
        resolved.add(number)
        lookup_review.append([number, reason])
    if resolved != ids:
        raise ValueError("Invoice lookup result omits requested invoices")

    # Preserve requested invoice order in all report sheets.
    rank = {number: index for index, number in enumerate(requested)}
    for rows in groups.values():
        rows.sort(key=lambda values: rank[values[12]])
    lookup_review.sort(key=lambda row: rank[row[0]])

    input_review = [[str(n), number, reason] for n, number, reason in selection.review]
    manifest = {
        "schema": "sbi-database-selected-bulk-report/v1",
        "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
        "dataset": backend_result["dataset"],
        "uploaded_selection_sha256": upload_sha256,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "financial_writes": False,
        "reconciliation_executed": False,
        "database_updated": False,
        "classification_basis": "SAVED_PAYMENT_RECEIVED_VALUE_FROM_VERIFIED_REPORT_SOURCE",
        "caution": "OK denotes a valid nonzero saved payment, not reconciliation or complete settlement.",
        "counts": {
            "requested": len(requested),
            "matched": len(groups["all-invoices"]),
            "lookup_review": len(lookup_review),
            "input_review": len(input_review),
            **{kind: len(groups[kind]) for kind in GROUPS},
        },
        "files": [],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        def add(name, headers, rows):
            raw, count = csv_bytes(headers, rows)
            archive.writestr(name, raw)
            manifest["files"].append({
                "name": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "rows": count,
            })
        for kind in GROUPS:
            add(kind + ".csv", HEADERS_53, groups[kind])
        add("validation-review.csv", INPUT_REVIEW_HEADERS, input_review)
        add("lookup-review.csv", LOOKUP_HEADERS, lookup_review)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")

    if output.tell() > 64 * 1024 * 1024:
        raise ValueError("Selected report ZIP exceeds safety limit")
    return output.getvalue(), manifest
