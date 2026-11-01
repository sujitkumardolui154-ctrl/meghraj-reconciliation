"""v1.4.2 payment report classification; no database writes."""
import re
from decimal import Decimal, InvalidOperation
from invoice_source_schema import row_layout

NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
SCIENTIFIC = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)

def classify_payment(value, cell_type):
    if not isinstance(value, str):
        raise ValueError("Stored source value must be text")
    # Excel errors, booleans, dates and unevaluated formulas are not payments.
    if cell_type not in ("n", "s", "str", "inlineStr"):
        return "error-value"
    text = value.strip()
    if not text:
        return "unpaid"
    # Scientific notation is accepted for actual Excel numeric cells only.
    pattern = SCIENTIFIC if cell_type == "n" else NUMBER
    if not pattern.fullmatch(text):
        return "error-value"
    try:
        number = Decimal(text)
    except InvalidOperation:
        return "error-value"
    if not number.is_finite():
        return "error-value"
    return "unpaid" if number == 0 else "ok"

def payment_report_kind(row):
    width, _, payment_index, _, _ = row_layout(row)
    types = row.get("original_cell_types")
    if (
        not isinstance(types, list)
        or len(types) != width
        or not all(isinstance(item, str) for item in types)
    ):
        raise ValueError("Original cell types are missing or incomplete")
    return classify_payment(
        row["original_values"][payment_index], types[payment_index]
    )
