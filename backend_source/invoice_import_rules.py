
"""Dashboard v1.4.0: add-only invoice validation."""
from collections import Counter
from invoice_source_schema import row_layout, invoice_number

INVALID_INVOICES = {"", "NA", "N/A"}

def classify_rows(rows, existing_invoices):
    """Rows contain source_row and 53 original_values; no database writes."""
    existing = set(existing_invoices)
    counts = Counter()
    for row in rows:
        values = row.get("original_values")
        try:
            invoice = invoice_number(row)
        except ValueError:
            continue
        counts[invoice] += 1

    accepted = []
    rejected = []
    for row in rows:
        values = row.get("original_values")
        invoice = ""
        reasons = []

        try:
            row_layout(row)
            valid = True
        except ValueError:
            valid = False

        if not valid:
            reasons.append("INVALID_SOURCE_COLUMN_ROW")
        else:
            invoice = invoice_number(row)
            if invoice.strip().upper() in INVALID_INVOICES:
                reasons.append("MISSING_OR_INVALID_INVOICE_NUMBER")
            elif invoice != invoice.strip():
                reasons.append("INVOICE_NUMBER_HAS_SURROUNDING_SPACES")
            elif any(ord(char) < 32 for char in invoice):
                reasons.append("INVOICE_NUMBER_HAS_CONTROL_CHARACTERS")
            else:
                if invoice in existing:
                    reasons.append("INVOICE_ALREADY_EXISTS")
                if counts[invoice] > 1:
                    reasons.append("DUPLICATE_IN_UPLOADED_FILE")

        if reasons:
            rejected.append({
                "source_row": row.get("source_row"),
                "invoice_no": invoice,
                "reasons": reasons,
            })
        else:
            accepted.append(row)

    return {"accepted": accepted, "rejected": rejected}
