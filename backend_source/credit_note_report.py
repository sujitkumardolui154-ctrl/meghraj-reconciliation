"""Read-only CREDIT NOTE report builder."""

HEADERS = [
    "FY",
    "Invoice Branch",
    "Invoice Generate Location",
    "Month",
    "Invoice Date",
    "Branch Code",
    "Client Name",
    "GST NO",
    "Invoice No",
    "Taxable Amount",
    "CGST",
    "SGST",
    "Total Bill Amount",
    "Less TDS",
    "Actual Reciaveable Ammount Deductionof TDS (Including GST)",
    "Taxable Amount Less TDS (Without GST)",
    "Payment Received (If With GST or Excluding GST)",
    "Credi note",
]

SOURCE_HEADERS = HEADERS[:-1]
PAYMENT_FIELD = SOURCE_HEADERS[-1]


def generate_credit_note_report(source_rows):
    """Preserve original values and identify explicit CREDIT NOTE records."""
    result = []
    all_invoices = set()
    credit_note_invoices = set()
    missing_invoice_numbers = 0

    for source in source_rows:
        if not isinstance(source, dict):
            raise ValueError("Source record must be a dictionary")

        missing = [h for h in SOURCE_HEADERS if h not in source]
        if missing:
            raise ValueError("Missing source headers: " + ", ".join(missing))

        invoice = str(source["Invoice No"] or "").strip()

        if invoice:
            all_invoices.add(invoice)
        else:
            missing_invoice_numbers += 1

        status = " ".join(
            str(source[PAYMENT_FIELD] or "").upper().split()
        )

        is_credit_note = status == "CREDIT NOTE"

        row = {h: source[h] for h in SOURCE_HEADERS}
        row["Credi note"] = (
            "CREDIT NOTE" if is_credit_note else ""
        )

        if is_credit_note and invoice:
            credit_note_invoices.add(invoice)

        result.append(row)

    summary = {
        "total_source_rows": len(result),
        "unique_invoices": len(all_invoices),
        "credit_note_invoices": len(credit_note_invoices),
        "missing_invoice_numbers": missing_invoice_numbers,
        "source_records_modified": 0,
    }

    return result, summary
