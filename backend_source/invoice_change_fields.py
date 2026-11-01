"""Read invoice and payment fields safely."""
from decimal import Decimal, InvalidOperation
from invoice_source_schema import invoice_number, row_layout

def payment_received(row):
    return row["original_values"][row_layout(row)[2]]

def normalized_payment(value):
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Invalid payment amount")
    raw = str(value).strip().replace(",", "").replace("₹", "")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("Invalid payment amount")
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Invalid payment precision")
    return amount.quantize(Decimal("0.01"))

def invoice_payment_identity(row):
    return {
        "invoice_no": invoice_number(row),
        "payment_received": payment_received(row),
    }
