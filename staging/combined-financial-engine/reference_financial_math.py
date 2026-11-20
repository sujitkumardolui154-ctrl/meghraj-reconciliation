"""D-023 SBI financial reference calculations; offline read-only, never settlement.

This code does not assign bank credits to invoices. Produces *hypothetical*
0/1/2/3 percent taxable-base TDS scenarios only after strict original invoice
column layout and gross arithmetic checks. Actual approved ledger parity is
a separate mandatory release gate.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "backend_source", ROOT / "staging" / "combined-financial-engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from invoice_source_schema import row_layout, HEADERS_34, HEADERS_35, HEADERS_53
from offline_review import combined_offline_review

CENT = Decimal("0.01")
RATES = (0, 1, 2, 3)


class FinancialReferenceInputError(ValueError):
    pass


def _money(value):
    """Reject unrounded source precision, negative/unknown, Excel formulas and floats."""
    if not isinstance(value, str) or not value.strip():
        raise FinancialReferenceInputError("INVALID_SOURCE_MONEY")
    try:
        amount = Decimal(value.strip())
    except InvalidOperation as exc:
        raise FinancialReferenceInputError("INVALID_SOURCE_MONEY") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(CENT):
        raise FinancialReferenceInputError("INVALID_SOURCE_MONEY")
    return amount


def invoice_reference_scenarios(row):
    """Check original amount columns and compute non-binding TDS scenarios.

    Source fields must match the exact approved 34/35/53-header contract;
    values may not be inferred, silently rounded or overwritten.
    """
    if not isinstance(row, dict):
        raise FinancialReferenceInputError("INVOICE_ROW_REQUIRED")
    try:
        width, *_ = row_layout(row)
    except (ValueError, KeyError, TypeError) as exc:
        raise FinancialReferenceInputError("INVALID_INVOICE_LAYOUT") from exc
    expected = {34: HEADERS_34, 35: HEADERS_35, 53: HEADERS_53}[width]
    if row.get("original_headers") != expected:
        raise FinancialReferenceInputError("SOURCE_HEADERS_REQUIRED")
    taxable_index = {34: 10, 35: 11, 53: 13}[width]
    amounts = {}
    flags = []
    for offset, field in enumerate(("taxable", "cgst", "sgst", "gross")):
        try:
            amounts[field] = _money(row["original_values"][taxable_index + offset])
        except (FinancialReferenceInputError, IndexError, TypeError):
            flags.append("INVALID_" + field.upper())
    if flags:
        return {
            "status": "REVIEW_REQUIRED", "flags": flags,
            "tds_reference_scenarios": {},
            "financial_write_performed": False,
            "approved_for_settlement": False,
        }
    calculated_gross = amounts["taxable"] + amounts["cgst"] + amounts["sgst"]
    if calculated_gross != amounts["gross"]:
        return {
            "status": "REVIEW_REQUIRED", "flags": ["INVOICE_GROSS_MISMATCH"],
            "tds_reference_scenarios": {},
            "financial_write_performed": False,
            "approved_for_settlement": False,
        }
    reference = {}
    for rate in RATES:
        tds = (amounts["taxable"] * Decimal(rate) / Decimal("100")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        reference[str(rate)] = {
            "tds_percent": str(rate),
            "tds_amount": str(tds),
            "with_gst_reference_credit": str(amounts["gross"] - tds),
            "without_gst_reference_credit": str(amounts["taxable"] - tds),
        }
    return {
        "status": "REFERENCE_CALCULATION_ONLY",
        "flags": [],
        "tds_reference_scenarios": reference,
        "financial_write_performed": False,
        "approved_for_settlement": False,
    }


def combined_reference_review(invoice_rows, payment_rows, *,
                              gst_sources=None, gst_master=None,
                              original_gst_records=None):
    """Join D-022 source review and D-023 reference math without allocations."""
    base = combined_offline_review(
        invoice_rows, payment_rows, gst_sources=gst_sources, gst_master=gst_master,
        original_gst_records=original_gst_records,
    )
    counts = Counter()
    row_math = []
    for index, row in enumerate(invoice_rows):
        result = invoice_reference_scenarios(row)
        hold = [
            f for f in base["invoice_row_flags"][index]["flags"]
            if f != "UNVERIFIED_BANK_ALLOCATION"
        ]
        if hold:
            status = "SOURCE_ELIGIBILITY_HOLD"
        elif result["flags"]:
            status = "SOURCE_AMOUNT_REVIEW_REQUIRED"
        else:
            status = "REFERENCE_CALCULATION_ONLY"
        counts[status] += 1
        row_math.append({
            "source_row_ordinal": index + 1,
            "status": status,
            "flags": list(result["flags"]),
        })
    base.update({
        "amount_review_status": "SOURCE_INDEPENDENT_PARITY_NOT_VERIFIED",
        "amount_status_counts": dict(sorted(counts.items())),
        "amount_row_flags": row_math,
        "tds_scenarios": "0_1_2_3_PERCENT_REFERENCE_ONLY",
        "payment_allocation": "NOT_EXECUTED",
        "approved_for_settlement": False,
        "financial_write_performed": False,
        "aws_deployment_performed": False,
    })
    return base
