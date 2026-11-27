"""Source layouts supported by the database importer."""
import json
from pathlib import Path

HEADERS_53 = json.loads(
    Path(__file__).with_name("invoice_import_contract.json").read_text()
)["headers"]
if len(HEADERS_53) != 53:
    raise ValueError("Invalid baseline header contract")

# Original source has no inserted model identity columns or model audit columns.
HEADERS_34 = HEADERS_53[:8] + HEADERS_53[11:37]
# Admin-approved original: an additional Branch Code at zero-based index 8.
# Keep both identity columns and their values; never silently drop one.
HEADERS_35 = HEADERS_34[:8] + ["Branch Code"] + HEADERS_34[8:]


def sheet_layout(name, headers):
    if headers == HEADERS_53:
        return 53, 12
    if name == "Invoice Details." and headers == HEADERS_34:
        return 34, 9
    if name == "Invoice Details." and headers == HEADERS_35:
        return 35, 10
    return None


def row_layout(row):
    values = row.get("original_values")
    if not isinstance(values, list):
        raise ValueError("Invalid source values")
    width = len(values)
    if width == 35:
        expected, invoice, payment, balance = HEADERS_35, 10, 18, 25
        if row.get("original_headers") != expected:
            raise ValueError("Missing or incorrect approved 35-column source headers")
    elif width == 34:
        expected, invoice, payment, balance = HEADERS_34, 9, 17, 24
        if row.get("original_headers") != expected:
            raise ValueError("Missing or incorrect 34-column source headers")
    elif width == 53:
        expected, invoice, payment, balance = HEADERS_53, 12, 20, 27
    else:
        raise ValueError("Unsupported source column count")
    if "original_headers" in row and row["original_headers"] != expected:
        raise ValueError("Source headers do not match the row layout")
    if not all(isinstance(value, str) for value in values):
        raise ValueError("Source values must be stored as text")
    return width, invoice, payment, balance, expected


def invoice_number(row):
    return row["original_values"][row_layout(row)[1]]


def export_values_53(row):
    """Project an approved source layout into the legacy 53-column report.

    Preserve both original Branch Code fields in the 35-column source.
    Synthetic/model fields are blank; never fabricate reconciliation data.
    """
    width, _, _, _, _ = row_layout(row)
    values = row["original_values"]
    if width == 53:
        return list(values)
    output = [""] * 53
    output[:8] = values[:8]
    if width == 35:
        output[10] = values[8]  # Second original Branch Code
        output[11:37] = values[9:]
    else:  # Approved 34-column source
        output[11:37] = values[8:]
    return output
