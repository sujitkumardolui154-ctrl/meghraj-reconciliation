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
