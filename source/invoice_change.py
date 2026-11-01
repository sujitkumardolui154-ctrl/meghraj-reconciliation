from collections import Counter
from decimal import Decimal, InvalidOperation

TAGS = (
    "NEW", "UNCHANGED", "PAYMENT_ADDED",
    "PAYMENT_CHANGED", "PAYMENT_CLEARED_REVIEW",
    "CONFLICT",
)

def key(value):
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()

def amount(value):
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Invalid amount")
    try:
        v = Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        raise ValueError("Invalid amount")
    if not v.is_finite() or v.as_tuple().exponent < -2:
        raise ValueError("Invalid amount precision")
    return v.quantize(Decimal("0.01"))

def compare(existing_rows, uploaded_rows):
    existing_rows = list(existing_rows)
    uploaded_rows = list(uploaded_rows)
    old = {}
    duplicate_old = set()

    for row in existing_rows:
        k = key(row.get("Invoice No"))
        if not k:
            continue
        if k in old:
            duplicate_old.add(k)
        else:
            old[k] = row

    counts = Counter(key(r.get("Invoice No")) for r in uploaded_rows)
    details = []

    for row in uploaded_rows:
        k = key(row.get("Invoice No"))
        previous = old.get(k)
        reason = ""
        old_value = None
        new_value = None

        if not k:
            reason = "MISSING_INVOICE_NO"
        elif k in duplicate_old or counts[k] > 1:
            reason = "DUPLICATE_INVOICE_NO"

        try:
            if previous is not None:
                old_value = amount(previous.get("Payment Received"))
            new_value = amount(row.get("Payment Received"))
        except ValueError:
            reason = "INVALID_PAYMENT_AMOUNT"

        if reason:
            tag = "CONFLICT"
        elif previous is None:
            tag = "NEW"
        elif old_value == new_value:
            tag = "UNCHANGED"
        elif old_value is None:
            tag = "PAYMENT_ADDED"
        elif new_value is None:
            tag = "PAYMENT_CLEARED_REVIEW"
        else:
            tag = "PAYMENT_CHANGED"

        details.append({
            "invoice_no": k,
            "tag": tag,
            "previous_payment": str(old_value) if old_value is not None else None,
            "uploaded_payment": str(new_value) if new_value is not None else None,
            "reason": reason,
        })

    tag_counts = Counter(r["tag"] for r in details)
    return {
        "summary": {
            "total_uploaded": len(uploaded_rows),
            **{t: tag_counts[t] for t in TAGS}
        },
        "details": details
    }

if __name__ == "__main__":
    old = [
        {"Invoice No": "MXP1001", "Payment Received": "1000"},
        {"Invoice No": "MXP1002", "Payment Received": "800"},
        {"Invoice No": "MXP1003", "Payment Received": ""},
    ]
    new = [
        {"Invoice No": "MXP1001", "Payment Received": "1000"},
        {"Invoice No": "MXP1002", "Payment Received": "950"},
        {"Invoice No": "MXP1003", "Payment Received": "500"},
        {"Invoice No": "MXP1004", "Payment Received": ""},
    ]
    print(compare(old, new)["summary"])
