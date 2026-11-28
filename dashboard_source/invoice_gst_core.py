"""SBI invoice and GST projection contract. No DB or reconciliation writes.

Only verified branch snapshots from the private database are eligible.
This module is intentionally dependency-free and suitable for synthetic QA.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

HEADERS = (
    "FY", "Invoice Branch", "Invoice Generate Location", "Month",
    "Invoice Date", "Branch Code", "Client Name", "Branch Code",
    "GST NO", "Invoice No", "Taxable Amount", "CGST", "SGST",
    "Total Bill Amount", "Error / Verification Flags",
    "Original Extracted Branch Name",
)
CENT = Decimal("0.01")
GSTIN = {"SBI_BANK": "19AAACS8577K3ZK", "SBI_FUND": "19AAACS7339D1ZB"}
INVOICE_PATTERN = re.compile(r"MXP[0-9]{4,10}\Z")
SOL_PATTERN = re.compile(r"[0-9]{1,6}\Z")
LR_PATTERN = re.compile(r"[A-Za-z0-9/-]{1,40}\Z")


class InvoiceError(ValueError):
    pass


def value_text(raw, key, max_length=180):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > max_length:
        raise InvoiceError("INVALID_" + key.upper())
    if any(ord(char) < 32 for char in raw):
        raise InvoiceError("INVALID_" + key.upper())
    return raw.strip()


def money(raw, key, *, positive=False):
    if isinstance(raw, bool) or raw is None or isinstance(raw, float):
        raise InvoiceError("INVALID_" + key.upper())
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise InvoiceError("INVALID_" + key.upper()) from None
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise InvoiceError("INVALID_" + key.upper())
    if amount != amount.quantize(CENT):
        raise InvoiceError("INVALID_" + key.upper())
    return amount


def date_value(raw, key):
    if not isinstance(raw, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
        raise InvoiceError("INVALID_" + key.upper())
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise InvoiceError("INVALID_" + key.upper()) from None


def financial_year(month):
    start = month.year if month.month >= 4 else month.year - 1
    return str(start) + "-" + str(start + 1)


# User-approved service labels: Sept (not Sep) To Oct, within one financial year.
SHORT_SERVICE_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sept", "Oct", "Nov", "Dec",
)


def service_period_label(first, last):
    if first > last:
        raise InvoiceError("SERVICE_PERIOD_REVIEW_REQUIRED")
    if financial_year(first) != financial_year(last):
        raise InvoiceError("CROSS_FINANCIAL_YEAR_REVIEW_REQUIRED")
    if first.year == last.year and first.month == last.month:
        return first.strftime("%B %Y")
    a = SHORT_SERVICE_MONTHS[first.month - 1]
    b = SHORT_SERVICE_MONTHS[last.month - 1]
    if first.year == last.year:
        return a + " To " + b + " " + str(last.year)
    return a + " " + str(first.year) + " To " + b + " " + str(last.year)


def verified_snapshot(branch):
    if not isinstance(branch, dict) or branch.get("verified") is not True:
        raise InvoiceError("BRANCH_MASTER_NOT_VERIFIED")
    client = value_text(branch.get("client_name"), "client_name", 200)
    if client.upper() in {"SBI", "STATE BANK OF INDIA", "REVIEW", "MISSING", "ERROR"}:
        raise InvoiceError("GENERIC_CLIENT_NAME_NOT_ALLOWED")
    cls = branch.get("client_class")
    if cls not in GSTIN or branch.get("gstin") != GSTIN[cls]:
        raise InvoiceError("GSTIN_CLASS_MISMATCH")
    sol = branch.get("sol_id")
    if not isinstance(sol, str) or SOL_PATTERN.fullmatch(sol) is None:
        raise InvoiceError("UNVERIFIED_SOL_ID")
    fields = {
        "branch_key": value_text(branch.get("branch_key"), "branch_key", 100),
        "client_name": client,
        "invoice_branch": value_text(branch.get("invoice_branch"), "invoice_branch", 200),
        "invoice_generate_location": value_text(branch.get("invoice_generate_location"), "invoice_generate_location", 200),
        "original_branch_name": value_text(branch.get("original_branch_name"), "original_branch_name", 200),
        "sol_id": sol,
        "gstin": branch["gstin"],
        "client_class": cls,
        "recipient_title": value_text(branch.get("recipient_title"), "recipient_title", 120),
        "customer_address": value_text(branch.get("customer_address"), "customer_address", 500),
    }
    if branch.get("state_code") != "19":
        raise InvoiceError("OUT_OF_STATE_REQUIRES_SEPARATE_GST_RULE")
    fields["state_code"] = "19"
    return fields


def build_invoice(source, branch):
    """Return unposted, validated invoice draft + canonical annexure.

    Source may contain shipment amounts only. The branch information must
    come from the verified private database; no client-supplied overrides.
    """
    if not isinstance(source, dict):
        raise InvoiceError("INVALID_REQUEST")
    snapshot = verified_snapshot(branch)
    invoice_no = value_text(source.get("invoice_no"), "invoice_no", 20)
    if not INVOICE_PATTERN.fullmatch(invoice_no):
        raise InvoiceError("INVALID_INVOICE_NUMBER")
    first = date_value(source.get("service_from"), "service_from")
    last = date_value(source.get("service_to"), "service_to")
    issued = date_value(source.get("invoice_date"), "invoice_date")
    # Cross-month billing is supported only within a single Indian FY.
    # A cross-FY period requires a separately approved GST/accounting rule.
    service_label = service_period_label(first, last)
    if issued < last:
        raise InvoiceError("INVOICE_DATE_BEFORE_SERVICE_END")
    shipments = source.get("shipments")
    if not isinstance(shipments, list) or not 1 <= len(shipments) <= 5000:
        raise InvoiceError("ANNEXURE_REQUIRED_1_TO_5000")
    clean = []
    keys = set()
    taxable = Decimal("0.00")
    for number, item in enumerate(shipments, start=1):
        if not isinstance(item, dict):
            raise InvoiceError("INVALID_SHIPMENT")
        dispatched = date_value(item.get("dispatch_date"), "dispatch_date")
        if not first <= dispatched <= last:
            raise InvoiceError("DISPATCH_DATE_OUTSIDE_SERVICE_PERIOD")
        lr = value_text(item.get("lr_no"), "lr_no", 40)
        if not LR_PATTERN.fullmatch(lr):
            raise InvoiceError("INVALID_LR_NO")
        key = (dispatched.isoformat(), lr)
        if key in keys:
            raise InvoiceError("DUPLICATE_LR_IN_INVOICE")
        keys.add(key)
        packet_ref = item.get("packet_ref_no") or ""
        if not isinstance(packet_ref, str) or len(packet_ref) > 80:
            raise InvoiceError("INVALID_PACKET_REF_NO")
        consignee = value_text(item.get("consignee"), "consignee", 200)
        try:
            weight = Decimal(str(item.get("weight_kg")))
        except (InvalidOperation, ValueError):
            raise InvoiceError("INVALID_WEIGHT") from None
        if (not weight.is_finite() or weight <= 0
                or weight.as_tuple().exponent < -3
                or weight > Decimal("999999999.999")):
            raise InvoiceError("INVALID_WEIGHT")
        amount = money(item.get("amount"), "shipment_amount", positive=True)
        taxable += amount
        clean.append({
            "line_no": number, "dispatch_date": dispatched.isoformat(),
            "lr_no": lr, "packet_ref_no": packet_ref,
            "consignee": consignee, "weight_kg": str(weight),
            "amount": str(amount),
        })
    if taxable > Decimal("999999999999.99"):
        raise InvoiceError("INVOICE_AMOUNT_TOO_LARGE")
    cgst = (taxable * Decimal("0.09")).quantize(CENT, rounding=ROUND_HALF_UP)
    sgst = (taxable * Decimal("0.09")).quantize(CENT, rounding=ROUND_HALF_UP)
    total = taxable + cgst + sgst
    return {
        **snapshot, "invoice_no": invoice_no,
        "service_from": first.isoformat(), "service_to": last.isoformat(),
        "invoice_date": issued.isoformat(),
        "service_month": service_label,
        # Stable start-month report index for backward compatibility.
        # Never duplicate a multi-month invoice into both GST months.
        "service_month_key": first.strftime("%Y-%m"),
        "multi_month_period": (first.year, first.month) != (last.year, last.month),
        "gst_period_policy": (
            "MULTI_MONTH_REVIEW_REQUIRED"
            if (first.year, first.month) != (last.year, last.month)
            else "SINGLE_MONTH"
        ),
        "fy": financial_year(first),
        "taxable": str(taxable.quantize(CENT)),
        "cgst": str(cgst), "sgst": str(sgst), "total": str(total),
        "shipment_count": len(clean), "shipments": clean,
        "status": "PREVIEW", "financial_execution_enabled": False,
        "reconciliation_applied": False,
    }


def gst_row(record):
    """Exact 16-column approved Workstream D v2.7 export order."""
    if record.get("status") != "FINALIZED":
        raise InvoiceError("DRAFT_NOT_EXPORTABLE")
    if record.get("verification_flags"):
        raise InvoiceError("UNVERIFIED_INVOICE_NOT_EXPORTABLE")
    values = (
        record["fy"], record["invoice_branch"],
        record["invoice_generate_location"], record["service_month"],
        record["invoice_date"], record["sol_id"], record["client_name"],
        record["sol_id"], record["gstin"], record["invoice_no"],
        record["taxable"], record["cgst"], record["sgst"],
        record["total"], "", record["original_branch_name"],
    )
    if len(values) != 16:
        raise InvoiceError("GST_CONTRACT_LENGTH_MISMATCH")
    return tuple(str(value) for value in values)


def safe_excel_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text
