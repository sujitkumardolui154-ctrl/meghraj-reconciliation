"""Verified credit-note projection from authoritative immutable invoice rows.

Original invoice identity/date/month/taxable and tax class are NEVER supplied
by the user; caller loads them from the approved PostgreSQL invoice registry.
No accounting, payment, GST-filing or reconciliation writes in this module.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENT = Decimal("0.01")
NUMBER_RE = re.compile(r"MXP/([0-9]{4})-([0-9]{4})/([0-9]{1,6})\Z")
INVOICE_RE = re.compile(r"MXP[0-9]{4,10}\Z")
GSTIN_BY_CLASS = {"SBI_BANK": "19AAACS8577K3ZK",
                  "SBI_FUND": "19AAACS7339D1ZB"}


class CreditNoteError(ValueError):
    pass


def credit_money(value, field):
    if isinstance(value, bool) or isinstance(value, float) or value is None:
        raise CreditNoteError("INVALID_" + field.upper())
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CreditNoteError("INVALID_" + field.upper()) from None
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(CENT):
        raise CreditNoteError("INVALID_" + field.upper())
    return amount


def financial_year(d):
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{start+1}"


def credit_note_request(payload):
    if not isinstance(payload, dict):
        raise CreditNoteError("INVALID_REQUEST")
    number = payload.get("credit_note_no")
    if not isinstance(number, str):
        raise CreditNoteError("INVALID_CREDIT_NOTE_NUMBER")
    match = NUMBER_RE.fullmatch(number)
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise CreditNoteError("INVALID_CREDIT_NOTE_NUMBER")
    raw_date = payload.get("credit_note_date")
    if not isinstance(raw_date, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) is None:
        raise CreditNoteError("INVALID_CREDIT_NOTE_DATE")
    try:
        issued = date.fromisoformat(raw_date)
    except ValueError:
        raise CreditNoteError("INVALID_CREDIT_NOTE_DATE") from None
    if financial_year(issued) != f"{match.group(1)}-{match.group(2)}":
        raise CreditNoteError("CREDIT_NOTE_FINANCIAL_YEAR_MISMATCH")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
        raise CreditNoteError("CREDIT_NOTE_REASON_REQUIRED")
    if any(ord(x) < 32 for x in reason):
        raise CreditNoteError("INVALID_CREDIT_NOTE_REASON")
    rows = payload.get("entries")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise CreditNoteError("CREDIT_NOTE_ENTRIES_REQUIRED")
    clean = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CreditNoteError("INVALID_CREDIT_ENTRY")
        invoice_no = row.get("invoice_no")
        if not isinstance(invoice_no, str) or INVOICE_RE.fullmatch(invoice_no) is None:
            raise CreditNoteError("INVALID_SOURCE_INVOICE_NO")
        if invoice_no in seen:
            raise CreditNoteError("DUPLICATE_INVOICE_IN_CREDIT_NOTE")
        seen.add(invoice_no)
        clean.append({
            "invoice_no": invoice_no,
            "credited_taxable": credit_money(row.get("credited_taxable"), "credit_amount")
        })
    return {
        "credit_note_no": number, "credit_note_date": issued.isoformat(),
        "fy": financial_year(issued), "reason": reason.strip(), "entries": clean,
    }


def build_credit_note(request_data, invoice_rows, previous_credits):
    """Build a read-only preview, ensuring no invoice is over-credited.

    invoice_rows: dict mapping invoice_no -> immutable verified database row.
    previous_credits: dict mapping invoice_no -> Decimal sum already finalized.
    All rows must be loaded from the SAME committed DB snapshot for preview,
    or under invoice-number advisory locks for finalize.
    """
    req = credit_note_request(request_data)
    output = []
    identity = None
    taxable_sum = Decimal("0.00")
    for n, entry in enumerate(req["entries"], start=1):
        number = entry["invoice_no"]
        invoice = invoice_rows.get(number)
        if not invoice:
            raise CreditNoteError("SOURCE_INVOICE_NOT_FOUND_OR_NOT_IMPORTED_" + number)
        if invoice.get("status") != "FINALIZED" or invoice.get("verification_flags"):
            raise CreditNoteError("SOURCE_INVOICE_NOT_VERIFIED_" + number)
        if invoice.get("cancelled") is True:
            raise CreditNoteError("SOURCE_INVOICE_CANCELLED_" + number)
        snapshot = invoice.get("master_snapshot")
        if not isinstance(snapshot, dict):
            raise CreditNoteError("SOURCE_MASTER_SNAPSHOT_NOT_VERIFIED_" + number)
        invoice_class = snapshot.get("client_class")
        gstin = invoice.get("gstin")
        if invoice_class not in GSTIN_BY_CLASS or gstin != GSTIN_BY_CLASS[invoice_class]:
            raise CreditNoteError("SOURCE_CUSTOMER_GSTIN_CONFLICT_" + number)
        # The uploaded 508-line reference is an SBI BANK (not SBI FUND) note.
        customer_key = (invoice_class, gstin)
        if identity is None:
            identity = customer_key
        elif identity != customer_key:
            raise CreditNoteError("MIXED_CUSTOMER_GSTIN_NOT_ALLOWED")
        try:
            original_date = date.fromisoformat(str(invoice["invoice_date"]))
        except ValueError:
            raise CreditNoteError("SOURCE_INVOICE_DATE_INVALID_" + number) from None
        if original_date > date.fromisoformat(req["credit_note_date"]):
            raise CreditNoteError("CREDIT_NOTE_PRECEDES_SOURCE_INVOICE_" + number)
        original_taxable = credit_money(invoice.get("taxable"), "source_taxable")
        prior = Decimal(str(previous_credits.get(number, "0.00")))
        if prior < 0 or prior > original_taxable:
            raise CreditNoteError("SOURCE_PRIOR_CREDIT_CONFLICT_" + number)
        credited = entry["credited_taxable"]
        if credited > original_taxable - prior:
            raise CreditNoteError("CREDIT_AMOUNT_EXCEEDS_REMAINING_" + number)
        month = invoice.get("service_month")
        if not isinstance(month, str) or not month.strip():
            raise CreditNoteError("SOURCE_SERVICE_MONTH_MISSING_" + number)
        sol = invoice.get("sol_id")
        if not isinstance(sol, str) or re.fullmatch(r"[0-9]{1,6}", sol) is None:
            raise CreditNoteError("SOURCE_SOL_UNVERIFIED_" + number)
        client = invoice.get("client_name")
        if not isinstance(client, str) or not client.strip() or client.upper() in (
            "SBI", "STATE BANK OF INDIA", "REVIEW", "ERROR"
        ):
            raise CreditNoteError("SOURCE_CLIENT_UNVERIFIED_" + number)
        taxable_sum += credited
        output.append({
            "line_no": n, "sac_code": "996812", "invoice_no": number,
            "invoice_date": original_date.isoformat(), "service_month": month,
            "branch_key": invoice["branch_key"], "client_name": client,
            "sol_id": sol, "gstin": gstin,
            "original_taxable": str(original_taxable),
            "prior_credited": str(prior),
            "remaining_before": str(original_taxable-prior),
            "credited_taxable": str(credited),
            "invoice_snapshot": {
                "invoice_no": number, "invoice_date": original_date.isoformat(),
                "service_month": month, "branch_key": invoice["branch_key"],
                "client_name": client, "sol_id": sol, "gstin": gstin,
                "original_taxable": str(original_taxable),
            },
        })
    cgst = (taxable_sum * Decimal(".09")).quantize(CENT, rounding=ROUND_HALF_UP)
    sgst = (taxable_sum * Decimal(".09")).quantize(CENT, rounding=ROUND_HALF_UP)
    total = taxable_sum + cgst + sgst
    return {
        "credit_note_no": req["credit_note_no"],
        "credit_note_date": req["credit_note_date"],
        "fy": req["fy"], "reason": req["reason"],
        "customer_class": identity[0],
        "customer_gstin": identity[1],
        "customer_name": "STATE BANK OF INDIA"
            if identity[0] == "SBI_BANK" else "SBI FUND MANAGEMENT LTD",
        "state_code": "19", "sac_code": "996812",
        "line_count": len(output), "lines": output,
        "taxable": str(taxable_sum.quantize(CENT)),
        "cgst": str(cgst), "sgst": str(sgst), "total": str(total),
        "status": "PREVIEW", "ledger_posted": False,
        "gst_filing_updated": False, "reconciliation_applied": False,
    }
