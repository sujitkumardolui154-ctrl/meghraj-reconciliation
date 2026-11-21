"""Verified SBI historical XLSX *header* profile, used for future NEW-only intake.

This module contains only column labels / coordinates observed from two
read-only reference workbooks. It NEVER opens a workbook or reads historical
financial rows. The live financial proposal engine is separate and remains
synthetic-only. Source data authentication must be provided by another gate.
"""
from __future__ import annotations

from typing import Sequence

PAYMENT_SHEET = "PAYMNENT"
INVOICE_SHEET = "Invoice Details."

# All source header labels from row 1, normalized only for surrounding whitespace.
# No bank transactions, invoice amounts, row contents, identities or historical IDs.
PAYMENT_HEADERS = (
    "Location", "Branch Name", "Txn Date", "Value Date", "Description",
    "Branch Code", "Name", "Debit", "Credit", "Balance", "Cross Tally",
    "Record For Me",
)
INVOICE_HEADERS = (
    "Client Name", "FY", "Invoice Branch", "Invoice Generate Location",
    "Month", "Invoice Date", "Branch Code", "Client Name", "Branch Code",
    "GST NO", "Invoice No", "Taxable Amount", "CGST", "SGST",
    "Total Bill Amount", "Less TDS",
    "Actual Reciaveable Ammount Deductionof  TDS (Including GST)",
    "Taxable Amount  Less TDS( Without GST",
    "Payment Received ( If With GST or Excluding GST)",
    "Payment Received ( If With GST or Excluding GST)_ Payment Date",
    "GST Payment_ Blance", "GST Payment Date",
    "TOTAL Paymnet Received( BASE Amt + GST)",
    "Creit Note Ammount",
    "Total Payment( Base Amt+ GST )-Credit Note & TDS",
    "Outstanding Balance/ Negetive Blance",
    "Mode", "Remraks", "Mail Id", "REMRAKS",
    "Sbi Contcat Number", "Meghraj Contact Number", "Others Remraks",
    "New Invoice Agansit of Credit Note", "Date",
)
# 1-based, source coordinates as verified; missing/renamed headers FAIL CLOSED.
PAYMENT_COLUMNS = {"txn_date": 3, "value_date": 4, "description": 5,
                   "sol_id": 6, "debit": 8, "credit": 9}
INVOICE_COLUMNS = {"month": 5, "invoice_date": 6, "sol_id": 7,
                   "client_name": 8, "invoice_no": 11, "taxable": 12,
                   "cgst": 13, "sgst": 14, "gross": 15,
                   "paid_marker": 19}
# These are source-only coordinate maps, not trusted financial evidence.
KEY_FIELDS = {
    PAYMENT_SHEET: PAYMENT_COLUMNS,
    INVOICE_SHEET: INVOICE_COLUMNS,
}

def _norm(value: object) -> str:
    return " ".join(value.split()) if type(value) is str else ""

def validate_reference_headers(sheet_name: str, row_one: Sequence[object]) -> dict[str, int]:
    """Check only row-1 header structure. No monetary/date row inspection.

    Returns zero-based column offsets to be used ONLY by a future authenticated
    new-only adapter. Do not use this as provenance or authorization to run.
    """
    if sheet_name == PAYMENT_SHEET:
        expected, offsets = PAYMENT_HEADERS, PAYMENT_COLUMNS
    elif sheet_name == INVOICE_SHEET:
        expected, offsets = INVOICE_HEADERS, INVOICE_COLUMNS
    else:
        raise ValueError("WRONG_INPUT_SHEET")
    if type(row_one) not in (list, tuple) or len(row_one) < len(expected):
        raise ValueError("WRONG_INPUT_HEADERS")
    for i, label in enumerate(expected):
        if _norm(row_one[i]) != _norm(label):
            raise ValueError(f"WRONG_INPUT_HEADER_COLUMN_{i + 1}")
    return {key: column_1based - 1 for key, column_1based in offsets.items()}
