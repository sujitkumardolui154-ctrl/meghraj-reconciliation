"""Independent staging-only SBI original invoice S marker precedence gate.

Original 35-column source S = payment-received marker; on approved 53-column
report projection it is U. Bank payment is PAYMNENT!I; source status is L.
This is a read-only eligibility *comparison*, never settlement authority.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def classify_original_s(value, *, cell_type="n", formula=False):
    """Only actual Excel numeric zero is a legitimate legacy-zero marker.

    A formula with stale cached zero, a text '0', a date or an Excel error
    must not be silently treated as verifiably unpaid.
    """
    if formula:
        return "FORMULA_NEEDS_RECALC"
    if value is None or str(value) == "":
        return "BLANK"
    if cell_type not in ("n", ""):
        return "TEXT_OR_ERROR"
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return "INVALID_VALUE"
    if not number.is_finite():
        return "INVALID_VALUE"
    return "NUMERIC_ZERO" if number == 0 else "NUMERIC_NONZERO"


def normalize_sol_text(value):
    """Normalize numeric code for comparison, but never edit its raw text."""
    if not isinstance(value, str):
        raise ValueError("SOL identifier must be source text")
    code = value.strip()
    return str(int(code)) if code.isascii() and code.isdecimal() else ""


def ordinary_tds_matches(*, bank_credit, invoice_gross, taxable):
    """Hypothetical rates only; never asserts statutory withholding."""
    try:
        credit, gross, base = (Decimal(str(x)) for x in
                               (bank_credit, invoice_gross, taxable))
    except (InvalidOperation, ValueError) as err:
        raise ValueError("Invalid financial source amount") from err
    if not all(x.is_finite() for x in (credit, gross, base)):
        raise ValueError("Nonfinite source amount")
    if credit <= 0 or gross <= 0 or base < 0:
        raise ValueError("Nonpositive bank or invoice amount")
    found = []
    for rate in (0, 1, 2, 3):
        withheld = (base * Decimal(rate) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        expected = gross - withheld
        if abs(credit - expected) <= Decimal("0.01"):
            found.append(str(rate))
    return tuple(found)


def shadow_review(
    *,
    invoice_marker, marker_cell_type, marker_is_formula,
    bank_source_status, bank_sol, invoice_sol,
    bank_date, invoice_issue_date, bank_credit, invoice_gross, taxable,
    source_master_verified=False, prior_ledger_verified=False,
    contradictory_reference=False, competing_claim=False,
):
    """Return conservative, non-mutating dual-policy review evidence.

    Dates must be ISO yyyy-mm-dd strings verified by the caller. No method
    assigns an invoice-paid marker, a bank status OK, or a ledger reservation.
    A passing result means eligible for independent MASTER review only.
    """
    import datetime
    kind = classify_original_s(
        invoice_marker, cell_type=marker_cell_type, formula=marker_is_formula
    )
    strict = kind == "BLANK"
    legacy = kind in ("BLANK", "NUMERIC_ZERO")
    reasons = []
    if bank_source_status.strip().upper() == "OK":
        reasons.append("PROTECT_HISTORICAL_BANK_L_OK")
    if not legacy:
        reasons.append("INVOICE_SOURCE_S_NOT_ELIGIBLE")
    if legacy and not strict:
        reasons.append("CONFLICT_V212_ZERO_V251_BLANK")
    bank_key, invoice_key = normalize_sol_text(bank_sol), normalize_sol_text(invoice_sol)
    if not bank_key or bank_key != invoice_key:
        reasons.append("SOL_TEXT_CODE_MISMATCH")
    if not source_master_verified:
        reasons.append("APPROVED_SOL_MASTER_NOT_VERIFIED")
    try:
        bank_day = datetime.date.fromisoformat(bank_date)
        invoice_day = datetime.date.fromisoformat(invoice_issue_date)
        if bank_day < invoice_day:
            reasons.append("BANK_PREDATES_INVOICE")
    except (ValueError, TypeError):
        reasons.append("DATE_EVIDENCE_NOT_VERIFIED")
    try:
        tds = ordinary_tds_matches(
            bank_credit=bank_credit,
            invoice_gross=invoice_gross,
            taxable=taxable
        )
    except ValueError:
        tds = ()
        reasons.append("FINANCIAL_AMOUNTS_INVALID")
    if not tds:
        reasons.append("OTHER_OWNER_APPROVED_METHOD_REQUIRED_OR_NO_AMOUNT_MATCH")
    if contradictory_reference:
        reasons.append("CONTRADICTORY_INVOICE_REFERENCE")
    if competing_claim:
        reasons.append("GLOBAL_COMPETING_PAYMENT_OR_INVOICE")
    if not prior_ledger_verified:
        reasons.append("PRIOR_ALLOCATION_LEDGER_NOT_VERIFIED")

    hard = {"PROTECT_HISTORICAL_BANK_L_OK", "INVOICE_SOURCE_S_NOT_ELIGIBLE",
            "SOL_TEXT_CODE_MISMATCH", "APPROVED_SOL_MASTER_NOT_VERIFIED",
            "BANK_PREDATES_INVOICE", "DATE_EVIDENCE_NOT_VERIFIED",
            "FINANCIAL_AMOUNTS_INVALID", "CONTRADICTORY_INVOICE_REFERENCE",
            "GLOBAL_COMPETING_PAYMENT_OR_INVOICE",
            "PRIOR_ALLOCATION_LEDGER_NOT_VERIFIED"}
    eligible_for_further_review = legacy and not any(x in hard for x in reasons)
    return {
        "source_s_marker_class": kind,
        "strict_blank_policy_candidate": strict,
        "historical_zero_or_blank_policy_candidate": legacy,
        "policy_precedence_resolved": not (legacy and not strict),
        "hypothetical_tds_rates": tds,
        "review_state": (
            "CANDIDATE_FOR_MASTER_REVIEW_ONLY"
            if eligible_for_further_review else "BLOCKED_OR_PROTECTED_REVIEW"
        ),
        "reasons": tuple(reasons),
        "finance_decision": "NOT_VERIFIED",
        "new_allocation_approved": False,
        "source_cells_mutated": False,
    }
