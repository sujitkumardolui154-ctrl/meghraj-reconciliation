"""Pure, read-only integrity guards for completed invoice report imports.

No database clients, credential access, or financial mutations.
"""


def validate_receipt_source_positions(entries):
    """Require unique physical workbook row positions per completed receipt.

    Each entry is (document_id, row_mapping). A receipt represents one source
    worksheet, and two imported invoices cannot originate from the same row.
    Invoice-number uniqueness alone does not enforce this property.
    """
    positions = set()
    for _, row in entries:
        position = row.get("source_row")
        if type(position) is not int or position < 2:
            raise ValueError("Completed import has an invalid source row")
        if position in positions:
            raise ValueError("Completed import has duplicate source rows")
        positions.add(position)
    return len(positions)


APPROVED_INVOICE_SHEET = "Invoice Details."


def validate_completed_receipt_source_sheet(receipt, entries):
    """Accept only the approved source worksheet for completed imports.

    The receipt and all of its persisted invoice rows must identify the
    approved worksheet exactly. Never normalize or silently substitute names.
    """
    if not isinstance(receipt, dict) or receipt.get("source_sheet") != APPROVED_INVOICE_SHEET:
        raise ValueError("Completed import has an unapproved source sheet")
    for _, row in entries:
        if not isinstance(row, dict) or row.get("source_sheet") != APPROVED_INVOICE_SHEET:
            raise ValueError("Completed import row has an unapproved source sheet")
    return len(entries)
