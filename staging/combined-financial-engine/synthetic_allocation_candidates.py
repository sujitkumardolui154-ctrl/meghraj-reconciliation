"""D-025 isolated SBI allocation *candidate* logic for fabricated fixtures only.

This module never reads files, environment variables, network resources or a
database. There is no CLI upload or write entrypoint. This is NOT the deployed
financial allocator and must NEVER be wired to historical/production records.
"""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENT = Decimal("0.01")
ALLOWED_RATES = (0, 1, 2, 3)
MONTH_PATTERN = re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")
MONEY_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")


class SyntheticAllocationBlocked(ValueError):
    pass


def _must(cond, message):
    if not cond:
        raise SyntheticAllocationBlocked(message)


def _money(raw):
    _must(isinstance(raw, str) and MONEY_PATTERN.fullmatch(raw) is not None,
          "SYNTHETIC_POSITIVE_MONEY_REQUIRED")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise SyntheticAllocationBlocked("SYNTHETIC_MONEY_INVALID") from exc
    _must(amount.is_finite() and amount >= 0, "SYNTHETIC_MONEY_INVALID")
    return amount


def _date(raw):
    _must(isinstance(raw, str) and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", raw),
          "ISO_DATE_REQUIRED")
    try:
        result = date.fromisoformat(raw)
    except ValueError as exc:
        raise SyntheticAllocationBlocked("INVALID_DATE") from exc
    return result


def _months(raw):
    _must(isinstance(raw, list) and bool(raw), "SERVICE_PERIOD_REQUIRED")
    _must(all(isinstance(x, str) and MONTH_PATTERN.fullmatch(x) for x in raw)
          and len(set(raw)) == len(raw), "INVALID_SERVICE_PERIOD")
    return frozenset(raw)


def _sol(raw, *, sbisa=False):
    _must(isinstance(sbisa, bool), "INVALID_SBISA_MARKER")
    if raw == "" and sbisa:
        return "00001"
    _must(isinstance(raw, str) and re.fullmatch(r"[0-9]{1,5}", raw),
          "EXACT_SOL_REQUIRED")
    result = raw.zfill(5)
    if sbisa:
        _must(result == "00001", "SBISA_REQUIRES_SOL_1")
    return result


def _invoice(raw):
    _must(isinstance(raw, dict) and raw.get("source_kind") == "SYNTHETIC",
          "HISTORICAL_OR_REAL_SOURCE_FORBIDDEN")
    key = raw.get("invoice_no")
    _must(isinstance(key, str) and re.fullmatch(r"SYNTH-INV-[A-Z0-9_-]+", key),
          "SYNTHETIC_INVOICE_ID_REQUIRED")
    protected = raw.get("protected")
    credit_note = raw.get("credit_note")
    sbisa = raw.get("sbisa")
    _must(type(protected) is bool and type(credit_note) is bool
          and type(sbisa) is bool, "REVIEW_MARKERS_REQUIRED")
    taxable, cgst, sgst, gross = (
        _money(raw.get(k)) for k in ("taxable", "cgst", "sgst", "gross")
    )
    _must(gross == taxable + cgst + sgst, "SYNTHETIC_GROSS_MISMATCH")
    return {
        "invoice_no": key,
        "sol": _sol(raw.get("sol_id"), sbisa=sbisa),
        "date": _date(raw.get("invoice_date")),
        "months": _months(raw.get("service_months")),
        "taxable": taxable,
        "gross": gross,
        "protected": protected,
        "credit_note": credit_note,
        "sbisa": sbisa,
    }


def _payment(raw):
    _must(isinstance(raw, dict) and raw.get("source_kind") == "SYNTHETIC",
          "HISTORICAL_OR_REAL_SOURCE_FORBIDDEN")
    key = raw.get("payment_id")
    _must(isinstance(key, str) and re.fullmatch(r"SYNTH-PAY-[A-Z0-9_-]+", key),
          "SYNTHETIC_PAYMENT_ID_REQUIRED")
    ref = raw.get("invoice_ref")
    _must(ref is None or isinstance(ref, str)
          and re.fullmatch(r"SYNTH-INV-[A-Z0-9_-]+", ref),
          "INVALID_SYNTHETIC_REFERENCE")
    months = raw.get("narration_months")
    _must(isinstance(months, list), "NARRATION_MONTHS_REQUIRED")
    if months:
        _months(months)
    sbisa = raw.get("sbisa")
    _must(type(sbisa) is bool, "INVALID_SBISA_MARKER")
    credit = _money(raw.get("credit"))
    _must(credit > 0, "POSITIVE_BANK_CREDIT_REQUIRED")
    return {
        "payment_id": key,
        "sol": _sol(raw.get("sol_id"), sbisa=sbisa),
        "date": _date(raw.get("payment_date")),
        "credit": credit,
        "invoice_ref": ref,
        "narration_months": frozenset(months),
        "sbisa": sbisa,
    }


def _net_scenarios(invoice):
    results = {}
    for rate in ALLOWED_RATES:
        deduction = (
            invoice["taxable"] * Decimal(rate) / 100
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        results[rate] = invoice["gross"] - deduction
    return results


def suggest_synthetic_matches(invoices, payments, *, synthetic_mode=False):
    """Return non-authoritative 1-to-1 candidate matches with explicit holds.

    Conservative policy: multiple candidate invoices, multiple payment-to-
    invoice proposals, partials, ambiguous TDS rates, age >180d, contradicting
    narration, unknown identity, protected and credit-note records are held.
    This first stage deliberately does not perform a financial waterfall.
    """
    _must(synthetic_mode is True, "SYNTHETIC_MODE_ONLY")
    _must(isinstance(invoices, list) and isinstance(payments, list),
          "SYNTHETIC_LISTS_REQUIRED")
    ins = [_invoice(row) for row in invoices]
    pays = [_payment(row) for row in payments]
    invoice_counts = Counter(row["invoice_no"] for row in ins)
    payment_counts = Counter(row["payment_id"] for row in pays)
    by_key = {x["invoice_no"]: x for x in ins if invoice_counts[x["invoice_no"]] == 1}
    proposals = []
    holds = []

    def hold(payment, reason):
        holds.append({"payment_id": payment["payment_id"], "reason": reason})

    for pay in pays:
        if payment_counts[pay["payment_id"]] != 1:
            hold(pay, "DUPLICATE_PAYMENT_ID")
            continue
        if pay["invoice_ref"] is not None:
            reference = pay["invoice_ref"]
            if invoice_counts[reference] > 1:
                hold(pay, "DUPLICATE_INVOICE_REFERENCE")
                continue
            selected = [by_key[reference]] if reference in by_key else []
        else:
            selected = [
                x for x in by_key.values() if x["sol"] == pay["sol"]
            ]

        if not selected:
            hold(pay, "INVOICE_REFERENCE_NOT_FOUND" if pay["invoice_ref"]
                 else "NO_SAME_SOL_INVOICE")
            continue

        possible = []
        excluded_reasons = set()
        for inv in selected:
            if inv["sol"] != pay["sol"]:
                excluded_reasons.add("CROSS_SOL_FORBIDDEN")
                continue
            if inv["sbisa"] != pay["sbisa"]:
                excluded_reasons.add("SBISA_IDENTITY_CONFLICT")
                continue
            if inv["protected"]:
                excluded_reasons.add("PROTECTED_INVOICE")
                continue
            if inv["credit_note"]:
                excluded_reasons.add("CREDIT_NOTE_REVIEW")
                continue
            age_days = (pay["date"] - inv["date"]).days
            if age_days < 0 or age_days > 180:
                excluded_reasons.add("PAYMENT_OUTSIDE_180_DAYS")
                continue
            if pay["narration_months"] and not (
                    inv["months"] <= pay["narration_months"]):
                excluded_reasons.add("CONTRADICTORY_SERVICE_PERIOD")
                continue
            possible.append(inv)

        if len(possible) != 1:
            if not possible:
                reason = sorted(excluded_reasons)[0] if excluded_reasons else "NO_ELIGIBLE_INVOICE"
            else:
                reason = "MULTIPLE_SAME_SOL_INVOICES_REVIEW"
            hold(pay, reason)
            continue

        invoice = possible[0]
        valid_rates = [
            rate for rate, expected in _net_scenarios(invoice).items()
            if expected == pay["credit"]
        ]
        if len(valid_rates) != 1:
            if len(valid_rates) > 1:
                hold(pay, "AMBIGUOUS_TDS_RATE")
            elif (pay["credit"] < invoice["gross"]
                  and pay["invoice_ref"] == invoice["invoice_no"]):
                hold(pay, "PARTIAL_PAYMENT_REVIEW_REQUIRED")
            else:
                hold(pay, "UNSUPPORTED_CREDIT_OR_DEDUCTION")
            continue
        proposals.append({
            "payment_id": pay["payment_id"],
            "invoice_no": invoice["invoice_no"],
            "tds_rate_reference": valid_rates[0],
            "credit_reference": str(pay["credit"]),
            "decision": "PROPOSED_FOR_INDEPENDENT_REVIEW",
        })

    refs = Counter(item["invoice_no"] for item in proposals)
    confirmed_candidates = []
    for item in proposals:
        if refs[item["invoice_no"]] > 1:
            hold({"payment_id": item["payment_id"]}, "MULTI_PAYMENT_INVOICE_REVIEW")
        else:
            confirmed_candidates.append(item)

    return {
        "status": "SYNTHETIC_CANDIDATES_FOR_REVIEW_ONLY",
        "candidates": confirmed_candidates,
        "holds": holds,
        "candidate_count": len(confirmed_candidates),
        "hold_count": len(holds),
        "historical_data_processed": False,
        "payment_allocation": "NOT_EXECUTED",
        "financial_write_performed": False,
        "approved_for_settlement": False,
        "production_deployed": False,
    }
