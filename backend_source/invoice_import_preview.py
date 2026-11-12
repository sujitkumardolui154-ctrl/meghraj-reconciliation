from invoice_source_schema import invoice_number

"""Dashboard v1.4.0 import preview; no database writes."""
from collections import Counter
from invoice_excel_parser import parse_excel
from invoice_import_rules import classify_rows
from credit_note_import_preview import summarize_invoice_upload_credit_notes

def build_preview(filename, data, existing_invoices):
    parsed = parse_excel(filename, data)
    existing = set(existing_invoices)
    counts = Counter(
        invoice_number(row) for row in parsed["rows"]
    )
    counts.update(
        row["invoice_no"] for row in parsed["rejected"]
        if row["invoice_no"]
    )

    classified = classify_rows(parsed["rows"], existing)
    rejected = [dict(row, reasons=list(row["reasons"]))
                for row in parsed["rejected"]]
    rejected.extend(classified["rejected"])
    accepted = []

    for row in classified["accepted"]:
        invoice = invoice_number(row)
        if counts[invoice] > 1:
            rejected.append({
                "source_row": row["source_row"],
                "invoice_no": invoice,
                "reasons": ["DUPLICATE_IN_UPLOADED_FILE"],
            })
        else:
            accepted.append(row)

    for row in rejected:
        invoice = row["invoice_no"]
        reasons = row["reasons"]
        if counts[invoice] > 1 and "DUPLICATE_IN_UPLOADED_FILE" not in reasons:
            reasons.append("DUPLICATE_IN_UPLOADED_FILE")
        if invoice in existing and "INVOICE_ALREADY_EXISTS" not in reasons:
            reasons.append("INVOICE_ALREADY_EXISTS")

    rejected.sort(key=lambda row: row["source_row"])
    return {
        "version": "1.4.0",
        "sheet": parsed["sheet"],
        "headers": parsed["headers"],
        "accepted": accepted,
        "rejected": rejected,
        "summary": {
            "total": len(accepted) + len(rejected),
            "ready_to_add": len(accepted),
            "rejected": len(rejected),
        },
        "credit_note_review": summarize_invoice_upload_credit_notes(parsed["rows"]),
        "database_changed": False,
    }
