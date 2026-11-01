"""Read-only CREDIT NOTE CSV export.

Preserves approved column order. Prevents spreadsheet-formula
execution in exported text cells without changing source records.
"""

import csv
import io
import re

from credit_note_53_adapter import (
    REPORT_HEADERS,
    project_credit_notes,
)

NUMBER = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)")


def safe_csv_cell(value):
    if value is None:
        return ""

    text = str(value)
    trimmed = text.lstrip()

    if trimmed.startswith(("=", "+", "@", "\t", "\r", "\n")):
        return "'" + text

    if trimmed.startswith("-") and not NUMBER.fullmatch(trimmed):
        return "'" + text

    return text


def build_credit_note_csv(source_headers, source_rows):
    """Generate complete CSV bytes and invoice-count summary."""

    rows, summary = project_credit_notes(
        source_headers,
        source_rows,
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")

    writer.writerow(REPORT_HEADERS)

    for record in rows:
        writer.writerow([
            safe_csv_cell(record[header])
            for header in REPORT_HEADERS
        ])

    return output.getvalue().encode("utf-8-sig"), summary
