"""Read-only, strict-schema CREDIT NOTE projection.

Never modifies source rows, calculates taxes, or changes allocations.
"""

import re
from collections.abc import Mapping

REPORT_HEADERS = (
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
)


CREDIT_NOTE_TOKEN = re.compile(r"(?<!\w)CREDIT\s+NO(?:TE|RTE)(?!\w)", re.IGNORECASE)


def normalize_header(value):
    return re.sub(r"\s+", " ", str(value).strip()).casefold()



def header_mapping(source_headers):
    """Resolve required fields by exact normalized header, not by position."""
    headers = tuple(source_headers)
    if not headers:
        raise ValueError("Empty source schema")


    # SBI_APPROVED_53_POSITIONAL_MAPPING_V1
    # Original invoice source: G = Branch Code, H = Client Name.
    # Reject schema changes rather than guessing financial fields.
    if len(headers) == 53:
        from invoice_source_schema import HEADERS_53

        if headers == tuple(HEADERS_53):
            indexes = (
                1, 2, 3, 4, 5, 6, 7, 11, 12,
                13, 14, 15, 16, 17, 18, 19, 20
            )

            expected = (
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
                "Actual Reciaveable Ammount Deductionof  TDS (Including GST)",
                "Taxable Amount  Less TDS( Without GST",
                "Payment Received ( If With GST or Excluding GST)",
            )

            for index, expected_name in zip(indexes, expected):
                if headers[index] != expected_name:
                    raise ValueError(
                        "SBI source schema mismatch at column "
                        + str(index + 1)
                    )

            return dict(zip(REPORT_HEADERS[:-1], indexes))

    # The approved 35-column source repeats "Branch Code" at G and I.
    # Bind the report to source G (index 6) and preserve I independently.
    # Do not use ambiguous first-match heuristics for financial columns.
    if len(headers) == 35:
        from invoice_source_schema import HEADERS_35
        if headers != tuple(HEADERS_35):
            raise ValueError("Incorrect approved 35-column source headers")
        indexes = (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)
        return dict(zip(REPORT_HEADERS[:-1], indexes))

    positions = {}
    for index, header in enumerate(headers):
        key = normalize_header(header)
        if key:
            positions.setdefault(key, []).append(index)

    missing = []
    ambiguous = []
    result = {}

    for header in REPORT_HEADERS[:-1]:
        matches = positions.get(normalize_header(header), [])

        if not matches:
            missing.append(header)
        elif len(matches) > 1:
            ambiguous.append(header)
        else:
            result[header] = matches[0]

    if missing or ambiguous:
        raise ValueError(
            "Missing required source headers: " + repr(missing)
            + "; Duplicate required source headers: "
            + repr(ambiguous)
        )

    return result


def required_values_from_mapping(row):
    """Ignore unrelated fields but reject ambiguous required fields."""
    required = {
        normalize_header(h): h
        for h in REPORT_HEADERS[:-1]
    }
    found = {}
    duplicates = []

    for key, value in row.items():
        name = normalize_header(key)
        if name not in required:
            continue
        if name in found:
            duplicates.append(required[name])
        else:
            found[name] = value

    missing = [
        h for h in REPORT_HEADERS[:-1]
        if normalize_header(h) not in found
    ]

    if missing or duplicates:
        raise ValueError(
            "Missing row fields: " + repr(missing)
            + "; Ambiguous row fields: " + repr(duplicates)
        )

    return [
        found[normalize_header(h)]
        for h in REPORT_HEADERS[:-1]
    ]

def project_credit_notes(source_headers, source_rows):
    """Return (18-column rows, summary) without source writes."""

    source_headers = tuple(source_headers)
    mapping = header_mapping(source_headers)

    output = []
    invoice_numbers = set()
    credit_note_numbers = set()

    for row in source_rows:
        if isinstance(row, Mapping):
            from invoice_source_schema import HEADERS_53
            from invoice_source_schema import HEADERS_35
            if source_headers in (tuple(HEADERS_53), tuple(HEADERS_35)):
                raise ValueError(
                    "35/53-column source requires positional rows "
                    "to distinguish duplicate field names"
                )
            values = required_values_from_mapping(row)
        else:
            if isinstance(row, (str, bytes)):
                raise ValueError("Invalid source row")

            values_in = tuple(row)

            if len(values_in) != len(source_headers):
                raise ValueError("Source row width mismatch")

            values = [
                values_in[mapping[h]]
                for h in REPORT_HEADERS[:-1]
            ]

        record = dict(zip(REPORT_HEADERS[:-1], values))

        invoice = str(record["Invoice No"] or "").strip()

        if invoice:
            invoice_numbers.add(invoice)

        status = " ".join(
            str(record[REPORT_HEADERS[16]] or "").upper().split()
        )

        is_credit_note = bool(CREDIT_NOTE_TOKEN.search(status))

        record["Credi note"] = (
            "CREDIT NOTE" if is_credit_note else ""
        )

        if is_credit_note and invoice:
            credit_note_numbers.add(invoice)

        output.append(record)

    summary = {
        "source_rows": len(output),
        "unique_invoices": len(invoice_numbers),
        "credit_note_invoices": len(credit_note_numbers),
        "report_columns": len(REPORT_HEADERS),
        "source_modified": False,
    }

    return output, summary
