"""D-001 batch-wide duplicate gate for GST preview; strictly read-only.

Caller must independently retrieve authentic original_records from protected
source. Metadata and comparison checks do not establish authentic provenance.
"""
from collections import Counter
from gst_preview import gst_preview


def _invoice_key(row):
    if not isinstance(row, dict):
        raise ValueError("INVALID_BATCH_ROW")
    value = row.get("invoice_no")
    return value.strip() if isinstance(value, str) else ""


def gst_batch_preview(sources, master, original_records):
    """Every repeated invoice in input OR original evidence is held for review.

    Exact keys only. Never deduplicate, discard or silently choose one row.
    Missing originals are never treated as independently source-verified.
    """
    if not isinstance(sources, list) or not isinstance(original_records, list):
        raise ValueError("BATCH_AND_ORIGINAL_RECORDS_REQUIRED")
    if not isinstance(master, list):
        raise ValueError("PRIVATE_MASTER_REQUIRED")
    input_counts = Counter(_invoice_key(row) for row in sources)
    original_counts = Counter(_invoice_key(row) for row in original_records)
    originals = {_invoice_key(row): row for row in original_records
                 if _invoice_key(row) and original_counts[_invoice_key(row)] == 1}
    results = []
    for row in sources:
        key = _invoice_key(row)
        duplicate = bool(key and (input_counts[key] > 1 or original_counts[key] > 1))
        original = originals.get(key) if original_counts[key] == 1 else None
        result = gst_preview(
            row, master, original_record=original,
            seen_invoices={key} if duplicate else set(),
        )
        results.append(result)
    return {
        "rows": results,
        "row_count": len(results),
        "review_required": sum(x["status"] == "REVIEW_REQUIRED" for x in results),
        "financial_write_performed": False,
        "approved_for_posting": False,
    }
