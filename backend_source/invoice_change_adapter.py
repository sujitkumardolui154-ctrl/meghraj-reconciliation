"""Read-only existing invoice comparison adapter."""

from collections import Counter

from invoice_source_schema import invoice_number
from invoice_change_fields import (
    payment_received,
    normalized_payment,
)

TAGS = (
    "NEW",
    "UNCHANGED",
    "PAYMENT_ADDED",
    "PAYMENT_CHANGED",
    "PAYMENT_CLEARED_REVIEW",
    "CONFLICT",
)


def compare_existing_invoices(existing_rows, uploaded_rows):
    existing = {}
    duplicates = set()

    for row in existing_rows:
        number = invoice_number(row)
        if number in existing:
            duplicates.add(number)
        else:
            existing[number] = row

    uploads = list(uploaded_rows)
    upload_counts = Counter(invoice_number(r) for r in uploads)
    details = []

    for row in uploads:
        number = invoice_number(row)
        old = existing.get(number)
        reason = ""

        if not number:
            reason = "MISSING_INVOICE_NUMBER"
        elif number in duplicates:
            reason = "DUPLICATE_EXISTING_INVOICE"
        elif upload_counts[number] > 1:
            reason = "DUPLICATE_UPLOADED_INVOICE"

        old_value = None
        new_value = None

        try:
            if old is not None:
                old_value = normalized_payment(
                    payment_received(old)
                )
            new_value = normalized_payment(
                payment_received(row)
            )
        except ValueError:
            reason = "INVALID_PAYMENT_VALUE"

        if reason:
            tag = "CONFLICT"
        elif old is None:
            tag = "NEW"
        elif old_value == new_value:
            tag = "UNCHANGED"
        elif old_value is None:
            tag = "PAYMENT_ADDED"
        elif new_value is None:
            tag = "PAYMENT_CLEARED_REVIEW"
        else:
            tag = "PAYMENT_CHANGED"

        details.append({
            "invoice_no": number,
            "source_row": row.get("source_row"),
            "tag": tag,
            "old_payment": (
                str(old_value) if old_value is not None else None
            ),
            "new_payment": (
                str(new_value) if new_value is not None else None
            ),
            "previous_report": (
                old.get("payment_report") if old else None
            ),
            "balance_review": (
                old.get("balance_valid") is False
                if old else False
            ),
            "reason": reason,
        })

    counts = Counter(d["tag"] for d in details)

    return {
        "summary": {
            "total": len(details),
            **{tag: counts[tag] for tag in TAGS},
        },
        "details": details,
    }
