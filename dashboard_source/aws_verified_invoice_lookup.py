"""PR129: AWS-only, authenticated and read-only selected invoice lookup.

Called ONLY after the Flask session, CSRF and sbi_report_viewer checks.
Uses existing AWS ADC for HTTPS Firestore GET/runQuery only; never updates any
document or calls the reconciliation engine. Invoice numbers are exact text.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from invoice_source_schema import HEADERS_53, row_layout, export_values_53

PROJECT = "meghraj-reconciliation"
SHA = "433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"
DATASET = SHA + "-report-v1"
ROOT = ("https://firestore.googleapis.com/v1/projects/" + PROJECT
        + "/databases/(default)/documents")
BASELINE = "/dashboard_report_datasets/" + DATASET
IMPORTS = "dashboard_invoice_rows_v140"
RECEIPTS = "/dashboard_import_receipts_v140/"
MAX_INVOICE_IDS = 2000
CHUNK = 30
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
SCIENTIFIC = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)


class VerifiedSourceUnavailable(RuntimeError):
    """Fail closed: source availability/completeness cannot be guaranteed."""


def _unpack(value):
    if not isinstance(value, dict):
        raise VerifiedSourceUnavailable("Invalid Firestore field encoding")
    for k in ("stringValue", "integerValue", "booleanValue", "doubleValue"):
        if k in value:
            if k == "integerValue":
                return int(value[k])
            return value[k]
    if "arrayValue" in value:
        return [_unpack(v) for v in value["arrayValue"].get("values", [])]
    if "nullValue" in value:
        return None
    raise VerifiedSourceUnavailable("Unexpected Firestore field type")


def _document(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), dict):
        raise VerifiedSourceUnavailable("Invalid Firestore document")
    return {key: _unpack(value) for key, value in raw["fields"].items()}


def _get(session, path):
    result = session.get(ROOT + path, timeout=(5, 30), allow_redirects=False)
    if result.status_code != 200:
        raise VerifiedSourceUnavailable("Firestore document unavailable")
    return _document(result.json())


def _query(session, parent, collection, field, op, values):
    """Run only fixed-collection queries. Fail on truncation/errors, never log data."""
    if op == "IN":
        assert isinstance(values, list) and 1 <= len(values) <= CHUNK
        operand = {"arrayValue": {"values": [{"stringValue": v} for v in values]}}
    elif op == "EQUAL":
        assert isinstance(values, str)
        operand = {"stringValue": values}
    else:
        raise VerifiedSourceUnavailable("Unsupported query")
    query = {"structuredQuery": {
        "from": [{"collectionId": collection}],
        "where": {"fieldFilter": {
            "field": {"fieldPath": field}, "op": op, "value": operand}},
    }}
    result = session.post(
        ROOT + parent + ":runQuery", json=query,
        timeout=(5, 60), allow_redirects=False
    )
    if result.status_code != 200:
        raise VerifiedSourceUnavailable("Firestore read query unavailable")
    if len(result.content) > 32 * 1024 * 1024:
        raise VerifiedSourceUnavailable("Source query response exceeds limit")
    entries = result.json()
    if not isinstance(entries, list) or len(entries) > 6000:
        raise VerifiedSourceUnavailable("Invalid source query response")
    matches = []
    for item in entries:
        if not isinstance(item, dict) or item.get("error"):
            raise VerifiedSourceUnavailable("Source query failed")
        doc = item.get("document")
        if doc is None:
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("name"), str):
            raise VerifiedSourceUnavailable("Invalid source query document")
        prefix = (ROOT + parent + "/" + collection + "/")
        # Firestore document names are canonical projects/... rather than URLs.
        canonical_prefix = prefix.removeprefix("https://firestore.googleapis.com/v1/")
        if not doc["name"].startswith(canonical_prefix):
            raise VerifiedSourceUnavailable("Source query returned another collection")
        matches.append((doc["name"].rsplit("/", 1)[-1], _document(doc)))
    return matches


def _metadata(session):
    meta = _get(session, BASELINE)
    if not (
        meta.get("source_sha256") == SHA
        and meta.get("state") == "READY"
        and type(meta.get("rows")) is int and meta["rows"] == 14374
        and meta.get("original_columns_state") == "READY"
        and meta.get("original_column_count") == 53
        and meta.get("original_columns_row_count") == 14374
        and meta.get("original_headers") == HEADERS_53
    ):
        raise VerifiedSourceUnavailable("Baseline verification failed")
    return meta


def _payment_kind(value, cell_type):
    if not isinstance(value, str) or cell_type not in (
        "n", "s", "str", "inlineStr"
    ):
        return "error-value"
    number = value.strip()
    if not number:
        return "unpaid"
    pattern = SCIENTIFIC if cell_type == "n" else NUMBER
    if not pattern.fullmatch(number):
        return "error-value"
    try:
        amt = Decimal(number)
    except InvalidOperation:
        return "error-value"
    if not amt.is_finite() or amt < 0:
        return "error-value"
    return "unpaid" if amt == 0 else "ok"


def _validated_candidate(row, number, *, imported=False, doc_id=""):
    try:
        width, index, payment, balance, headers = row_layout(row)
        values = row["original_values"]
        types = row.get("original_cell_types")
        if (
            not isinstance(types, list) or len(types) != width
            or not all(isinstance(t, str) for t in types)
            or row.get("invoice_no") != number
            or values[index] != number
            or type(row.get("balance_valid")) is not bool
            or type(row.get("source_row")) is not int
            or row["source_row"] < 2
        ):
            return None
        if imported:
            if (
                width not in (34, 35, 53)
                or row.get("finance_processed") is not False
                or doc_id != hashlib.sha256(number.encode("utf-8")).hexdigest()
            ):
                return None
        else:
            if (
                width != 53 or row["source_row"] > 14375
                or row.get("source_sha256") != SHA
                or row.get("original_columns_source_sha256") != SHA
                or row.get("original_headers", HEADERS_53) != HEADERS_53
            ):
                return None
        kind = _payment_kind(values[payment], types[payment])
        return {
            "invoice_no": number,
            "values": export_values_53(row),
            "payment_kind": kind,
            "balance_review": not row["balance_valid"],
        }
    except (ValueError, TypeError, IndexError, KeyError):
        return None


def _completed_import(session, rid, cache):
    """Check receipt completeness, not just a user-controlled source row."""
    if rid in cache:
        return cache[rid]
    if not isinstance(rid, str) or not re.fullmatch(r"[a-f0-9]{32}", rid):
        cache[rid] = None
        return None
    try:
        receipt = _get(session, RECEIPTS + rid)
        count = receipt.get("total_count")
        added = receipt.get("added_count")
        rejected = receipt.get("rejected_count")
        processed = receipt.get("processed_count")
        if not (
            receipt.get("status") == "COMPLETED"
            and receipt.get("finance_processed") is False
            and all(type(v) is int and v >= 0
                    for v in (count, added, rejected, processed))
            and added + rejected == count
            and processed == count
            and isinstance(receipt.get("source_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", receipt["source_sha256"])
            and isinstance(receipt.get("source_sheet"), str)
        ):
            cache[rid] = None
            return None
        records = _query(session, "", IMPORTS, "import_receipt", "EQUAL", rid)
        if len(records) != added:
            cache[rid] = None
            return None
        for doc_id, row in records:
            width, invoice_index, _, _, headers = row_layout(row)
            invoice = row["original_values"][invoice_index]
            if (
                doc_id != hashlib.sha256(invoice.encode("utf-8")).hexdigest()
                or row.get("invoice_no") != invoice
                or row.get("import_receipt") != rid
                or row.get("source_sha256") != receipt["source_sha256"]
                or row.get("source_sheet") != receipt["source_sheet"]
                or receipt.get("source_headers", list(headers)) != list(headers)
                or row.get("finance_processed") is not False
                or type(row.get("source_row")) is not int
                or row["source_row"] < 2
                or not isinstance(row.get("original_cell_types"), list)
                or len(row["original_cell_types"]) != width
            ):
                cache[rid] = None
                return None
        cache[rid] = receipt
        return receipt
    except (VerifiedSourceUnavailable, ValueError, TypeError, KeyError):
        cache[rid] = None
        return None


def lookup_verified_invoices(invoice_numbers, *, session=None):
    """Exact-match validated invoice snapshot -> existing selected-report schema.

    Misses are reported as misses in the VERIFIED SOURCE ONLY; never as proof
    that an invoice does not exist elsewhere. Query failures stop the report.
    """
    if (
        not isinstance(invoice_numbers, (tuple, list))
        or not 1 <= len(invoice_numbers) <= MAX_INVOICE_IDS
        or any(not isinstance(n, str) or not 0 < len(n) <= 128
               or not n.strip() == n or any(ord(ch) < 32 for ch in n)
               for n in invoice_numbers)
        or len(set(invoice_numbers)) != len(invoice_numbers)
    ):
        raise ValueError("Invalid or duplicate invoice selection")

    own_session = session is None
    if own_session:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/datastore"]
        )
        if project not in (None, PROJECT):
            raise VerifiedSourceUnavailable("Unexpected credential project")
        session = AuthorizedSession(credentials)
    try:
        _metadata(session)
        candidates = defaultdict(list)
        cache = {}
        for start in range(0, len(invoice_numbers), CHUNK):
            batch = list(invoice_numbers[start:start + CHUNK])
            for doc_id, row in _query(
                session, BASELINE, "rows", "invoice_no", "IN", batch
            ):
                number = row.get("invoice_no")
                if number not in batch:
                    raise VerifiedSourceUnavailable("Baseline query mismatch")
                candidates[number].append(
                    _validated_candidate(row, number)
                )
            for doc_id, row in _query(
                session, "", IMPORTS, "invoice_no", "IN", batch
            ):
                number = row.get("invoice_no")
                if number not in batch:
                    raise VerifiedSourceUnavailable("Imported query mismatch")
                rid = row.get("import_receipt")
                receipt = _completed_import(session, rid, cache)
                candidate = None
                if (
                    receipt is not None
                    and row.get("source_sha256") == receipt["source_sha256"]
                    and row.get("source_sheet") == receipt["source_sheet"]
                ):
                    candidate = _validated_candidate(
                        row, number, imported=True, doc_id=doc_id
                    )
                candidates[number].append(candidate)

        # Detect snapshot changed during request; a partial mixed-source report
        # is not acceptable.
        _metadata(session)
        matches, review = [], []
        for number in invoice_numbers:
            found = candidates[number]
            if not found:
                review.append({
                    "invoice_no": number,
                    "reason": "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE",
                })
            elif len(found) != 1:
                review.append({
                    "invoice_no": number,
                    "reason": "DUPLICATE_DATABASE_INVOICE_MATCH",
                })
            elif found[0] is None:
                review.append({
                    "invoice_no": number,
                    "reason": "DATABASE_SOURCE_CONFLICT",
                })
            else:
                matches.append(found[0])
        return {
            "version": "invoice-selection-v1",
            "dataset": DATASET,
            "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
            "financial_writes": False,
            "reconciliation_executed": False,
            "database_updated": False,
            "matches": matches,
            "review": review,
            "requested_count": len(invoice_numbers),
            "matched_count": len(matches),
            "review_count": len(review),
        }
    except VerifiedSourceUnavailable:
        raise
    except Exception as exc:
        logging.warning("AWS verified lookup read failed: %s", type(exc).__name__)
        raise VerifiedSourceUnavailable("AWS invoice lookup failed") from None
    finally:
        if own_session:
            session.close()
