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


def sheet_layout(name, headers):
    if headers == HEADERS_53:
        return 53, 12
    if name == "Invoice Details." and headers == HEADERS_34:
        return 34, 9
    return None


def row_layout(row):
    values = row.get("original_values")
    if not isinstance(values, list):
        raise ValueError("Invalid source values")
    width = len(values)
    if width == 34:
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
