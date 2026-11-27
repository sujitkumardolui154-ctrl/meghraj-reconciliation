"""Read-only historical invoice discovery for the credit-note lookup screen.

PR129's pinned 53-column Firestore dataset can prove a report row was
retrieved, but not that an issued invoice is eligible for a *new* credit note.
Never treat a report row, nonzero payment, or empty credit marker as proof
of a complete credit ledger, filing state or approved recipient identity.

There are NO writes to Firestore, PostgreSQL or reconciliation.
"""
from decimal import Decimal, InvalidOperation
import re

from invoice_source_schema import HEADERS_53


class HistoricalInvoiceEvidenceUnavailable(RuntimeError):
    pass


MONEY = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
NUMERIC_SOL = re.compile(r"\d{1,6}\Z")
INVOICE_NUMBER = re.compile(r"MXP[0-9]{4,10}\Z")
REVIEW_REASONS = frozenset((
    "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE",
    "DUPLICATE_DATABASE_INVOICE_MATCH",
    "DATABASE_SOURCE_CONFLICT",
))
SOURCE_KIND = "VERIFIED_READ_ONLY_REPORT_SOURCE"
REVIEW_STATUS = "HISTORICAL_REPORT_REVIEW_REQUIRED"


def _text(values, index):
    value = values[index]
    return value.strip() if isinstance(value, str) else ""


def _source_money(value):
    if not value or not MONEY.fullmatch(value):
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite() or result < 0:
        return None
    # Historical Excel float artifacts can differ from exact cents. Do not
    # silently make an accounting decision from such values.
    quantized = result.quantize(Decimal("0.01"))
    if abs(result - quantized) > Decimal("0.00000001"):
        return None
    return str(quantized)


def project_historical_evidence(requested, source):
    """Return complete lookup review; never a credit-eligible invoice object.

    The source must be the existing approved verified lookup contract.
    Completeness and duplicates are independently checked here too.
    """
    if (
        not isinstance(requested, list)
        or not 1 <= len(requested) <= 1000
        or len(requested) != len(set(requested))
        or any(not isinstance(n, str) or not INVOICE_NUMBER.fullmatch(n)
               for n in requested)
    ):
        raise ValueError("INVALID_HISTORICAL_INVOICE_SELECTION")
    if not isinstance(source, dict) or any(
        source.get(k) is not False
        for k in ("financial_writes", "reconciliation_executed", "database_updated")
    ):
        raise HistoricalInvoiceEvidenceUnavailable("SOURCE_READONLY_ATTESTATION_MISSING")
    if (
        source.get("version") != "invoice-selection-v1"
        or source.get("source_kind") != SOURCE_KIND
        or not isinstance(source.get("dataset"), str)
        or not source.get("dataset")
        or not isinstance(source.get("matches"), list)
        or not isinstance(source.get("review"), list)
        or source.get("requested_count") != len(requested)
        or source.get("matched_count") != len(source["matches"])
        or source.get("review_count") != len(source["review"])
        or len(source["matches"]) + len(source["review"]) != len(requested)
    ):
        raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_LOOKUP_CONTRACT_INVALID")

    found = {}
    requested_set = set(requested)
    for item in source["matches"]:
        if not isinstance(item, dict):
            raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_MATCH_INVALID")
        number, values = item.get("invoice_no"), item.get("values")
        if (number not in requested_set or number in found
            or not isinstance(values, list) or len(values) != len(HEADERS_53)
            or not all(isinstance(v, str) for v in values)
            or values[12] != number
            or item.get("payment_kind") not in ("unpaid", "ok", "error-value")
            or type(item.get("balance_review")) is not bool):
            raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_MATCH_CONFLICT")
        flags = []
        invoice_date = _text(values, 5)
        month = _text(values, 4)
        gstin = _text(values, 11)
        taxable = _source_money(_text(values, 13))
        cgst = _source_money(_text(values, 14))
        sgst = _source_money(_text(values, 15))
        gross = _source_money(_text(values, 16))
        if not invoice_date:
            flags.append("INVOICE_DATE_SOURCE_MISSING")
        if not month:
            flags.append("SERVICE_PERIOD_SOURCE_MISSING")
        if taxable is None or cgst is None or sgst is None or gross is None:
            flags.append("SOURCE_FINANCIAL_VALUE_REQUIRES_REVIEW")
        elif (Decimal(taxable)+Decimal(cgst)+Decimal(sgst)
              != Decimal(gross)):
            flags.append("SOURCE_TAX_TOTAL_CONFLICT")
        original_sol = _text(values, 6)
        modeled_sol = _text(values, 8)
        if (not NUMERIC_SOL.fullmatch(original_sol)
            or (modeled_sol and modeled_sol != original_sol)):
            flags.append("SOURCE_SOL_ID_NOT_INDEPENDENTLY_VERIFIED")
        source_client = _text(values, 7)
        model_client = _text(values, 9)
        if not source_client or source_client.upper() in (
            "SBI", "STATE BANK OF INDIA", "REVIEW", "MISSING", "ERROR"
        ) or (model_client and model_client != source_client):
            flags.append("SOURCE_CLIENT_NAME_REQUIRES_REVIEW")
        if gstin not in ("19AAACS8577K3ZK", "19AAACS7339D1ZB"):
            flags.append("CUSTOMER_GSTIN_NOT_VERIFIED")
        if _source_money(_text(values, 25)) not in (None, "0.00"):
            flags.append("HISTORICAL_CREDIT_NOTE_AMOUNT_PRESENT")
        if _text(values, 25) and _source_money(_text(values, 25)) is None:
            flags.append("HISTORICAL_CREDIT_NOTE_AMOUNT_INVALID")
        if item["payment_kind"] != "unpaid":
            flags.append("HISTORICAL_PAYMENT_EVIDENCE_REQUIRES_REVIEW")
        if item["balance_review"]:
            flags.append("HISTORICAL_BALANCE_REVIEW_REQUIRED")
        found[number] = {
            "invoice_no": number, "status": REVIEW_STATUS,
            "credit_note_eligible": False,
            "source_kind": SOURCE_KIND,
            "invoice_date_source": invoice_date or None,
            "service_month_source": month or None,
            "client_name_source": source_client or None,
            "model_client_name_source": model_client or None,
            "sol_id_source": original_sol or None,
            "model_sol_id_source": modeled_sol or None,
            "customer_gstin_source": gstin or None,
            "taxable_source": taxable,
            "cgst_source": cgst, "sgst_source": sgst,
            "total_source": gross,
            "source_review_flags": flags,
            "blocked_because": (
                "HISTORICAL_CREDIT_LEDGER_AND_TAX_FILING_NOT_CERTIFIED"
            ),
        }
    for item in source["review"]:
        if not isinstance(item, dict):
            raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_REVIEW_INVALID")
        number, reason = item.get("invoice_no"), item.get("reason")
        if (number not in requested_set or number in found
            or reason not in REVIEW_REASONS):
            raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_REVIEW_CONFLICT")
        found[number] = {
            "invoice_no": number, "status": reason,
            "credit_note_eligible": False, "source_kind": SOURCE_KIND,
            "blocked_because": reason,
        }
    if set(found) != requested_set:
        raise HistoricalInvoiceEvidenceUnavailable("HISTORICAL_LOOKUP_INCOMPLETE")
    return {
        "records": [found[number] for number in requested],
        "dataset": source["dataset"], "source_kind": SOURCE_KIND,
        "history_review_only": True, "credit_note_eligible": False,
        "financial_writes": False,
    }


def lookup_historical_evidence(numbers, *, verified_lookup=None):
    """Fetch via existing PR129 read-only source; return review-only evidence.

    A valid report row NEVER authorizes insertion into credit_note_lines.
    """
    if verified_lookup is None:
        from aws_verified_invoice_lookup import lookup_verified_invoices
        verified_lookup = lookup_verified_invoices
    try:
        report = verified_lookup(numbers)
    except Exception:
        raise HistoricalInvoiceEvidenceUnavailable(
            "HISTORICAL_REPORT_SOURCE_UNAVAILABLE"
        ) from None
    return project_historical_evidence(numbers, report)
