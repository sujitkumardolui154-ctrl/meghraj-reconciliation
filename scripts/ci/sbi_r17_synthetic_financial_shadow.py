"""R17 independent synthetic-only financial hypothesis / conservation QA.

NOT a recovered or certified Master v2.51 engine. NEVER financial reconciliation,
bank settlement, invoice status setting, production writer, or database access.
Only synthetic-prefixed fixtures may enter. Output contains no source identifiers
or amounts. This source intentionally lives in scripts/ci, not backend routes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENT = Decimal("0.01")
TDS_RATES = (0, 1, 2, 3)
SOL_RE = re.compile(r"[0-9]{1,12}\Z")
PERIOD_RE = re.compile(r"20[0-9]{2}-(0[1-9]|1[0-2])\Z")


class SyntheticOnlyRefusal(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def refuse(reason):
    raise SyntheticOnlyRefusal(reason)


def money(value, *, allow_rounding=False):
    if isinstance(value, bool) or isinstance(value, float) or value is None:
        refuse("MONEY_TYPE_UNSAFE")
    if not isinstance(value, (str, int, Decimal)):
        refuse("MONEY_TYPE_UNSAFE")
    try:
        val = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        refuse("MONEY_NOT_DECIMAL")
    if not val.is_finite():
        refuse("MONEY_NOT_FINITE")
    rounded = val.quantize(CENT, rounding=ROUND_HALF_UP)
    if not allow_rounding and rounded != val:
        refuse("MONEY_MORE_THAN_TWO_DECIMALS")
    return rounded


def nonblank(value):
    return value is not None and not (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class SyntheticInvoice:
    key: str
    sol: str
    client: str
    taxable: str
    gross: str
    gst: str
    outstanding: str
    issued_at: date | None
    service_periods: tuple[str, ...]
    original_s_marker: object = None


@dataclass(frozen=True)
class SyntheticPayment:
    key: str
    sol: str
    client: str
    credit: str
    booked_at: date | None
    narration_refs: tuple[str, ...]
    service_periods: tuple[str, ...]
    gst_component_only: bool = False
    original_bank_status: str = ""


@dataclass(frozen=True)
class SyntheticReservation:
    payment_key: str
    invoice_key: str
    amount: str


def _check_periods(periods):
    if not isinstance(periods, tuple) or any(
        not isinstance(p, str) or not PERIOD_RE.fullmatch(p) for p in periods
    ):
        refuse("SYNTHETIC_PERIOD_FORMAT_INVALID")


def _check_invoice(inv):
    if not isinstance(inv, SyntheticInvoice) or not re.fullmatch(
        r"SYN-MXP-[0-9]{3,6}", inv.key
    ):
        refuse("SYNTHETIC_INVOICE_KEY_REQUIRED")
    if inv.sol and not SOL_RE.fullmatch(inv.sol):
        refuse("SYNTHETIC_SOL_INVALID")
    if not isinstance(inv.client, str) or not inv.client.startswith("SYNTHETIC "):
        refuse("SYNTHETIC_CLIENT_REQUIRED")
    if inv.issued_at is not None and type(inv.issued_at) is not date:
        refuse("SYNTHETIC_DATE_INVALID")
    _check_periods(inv.service_periods)
    taxable = money(inv.taxable)
    gross = money(inv.gross)
    gst = money(inv.gst)
    outstanding = money(inv.outstanding)
    if taxable < 0 or gst < 0 or gross <= 0 or outstanding < 0:
        refuse("SYNTHETIC_INVOICE_AMOUNTS_INVALID")
    if gross < taxable:
        refuse("SYNTHETIC_GROSS_BELOW_TAXABLE")
    if outstanding > gross:
        refuse("SYNTHETIC_OUTSTANDING_EXCEEDS_GROSS")
    return taxable, gross, gst, outstanding


def _check_payment(pay):
    if not isinstance(pay, SyntheticPayment) or not re.fullmatch(
        r"SYN-PAY-[0-9]{3,6}", pay.key
    ):
        refuse("SYNTHETIC_PAYMENT_KEY_REQUIRED")
    if not SOL_RE.fullmatch(pay.sol):
        refuse("SYNTHETIC_SOL_INVALID")
    if not isinstance(pay.client, str) or not pay.client.startswith("SYNTHETIC "):
        refuse("SYNTHETIC_CLIENT_REQUIRED")
    if pay.booked_at is not None and type(pay.booked_at) is not date:
        refuse("SYNTHETIC_DATE_INVALID")
    if not isinstance(pay.narration_refs, tuple) or any(
        not isinstance(x, str) or not re.fullmatch(r"SYN-MXP-[0-9]{3,6}", x)
        for x in pay.narration_refs
    ):
        refuse("SYNTHETIC_REFERENCE_INVALID")
    if type(pay.gst_component_only) is not bool:
        refuse("SYNTHETIC_GST_FLAG_INVALID")
    if not isinstance(pay.original_bank_status, str):
        refuse("SYNTHETIC_SOURCE_STATUS_INVALID")
    _check_periods(pay.service_periods)
    return money(pay.credit)


def _normalized_client(value):
    return " ".join(value.casefold().split())


def exact_tds_hypotheses(pay, inv):
    """Decimal HALF_UP hypotheses only; rates aren't verified withholding."""
    credit = _check_payment(pay)
    taxable, gross, _, _ = _check_invoice(inv)
    found = []
    for rate in TDS_RATES:
        deduction = (taxable * Decimal(rate) / Decimal(100)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        expected = gross - deduction
        if credit == expected:
            found.append(rate)
    return tuple(found)


def review_one_payment_invoice(pay, inv):
    """Return risk codes only. NO OK / SUSPENSE / invoice allocation."""
    credit = _check_payment(pay)
    taxable, gross, gst, outstanding = _check_invoice(inv)
    blockers = set()
    if credit <= 0:
        blockers.add("NONPOSITIVE_BANK_CREDIT")
    if nonblank(pay.original_bank_status):
        blockers.add("BANK_SOURCE_STATUS_REQUIRES_INDEPENDENT_VERIFICATION")
    if nonblank(inv.original_s_marker):
        blockers.add("INVOICE_S_NONBLANK_PROTECTED")
    if not inv.sol:
        blockers.add("SBISA_BLANK_SOL_DOCUMENTARY_REVIEW")
    elif pay.sol != inv.sol:
        blockers.add(
            "SBISA_COLLECTING_SOL_REVIEW"
            if pay.sol == "1"
            else "UNAPPROVED_CROSS_SOL"
        )
    if _normalized_client(pay.client) != _normalized_client(inv.client):
        blockers.add("CLIENT_IDENTITY_NOT_VERIFIED")
    if not pay.booked_at or not inv.issued_at:
        blockers.add("SOURCE_DATE_EVIDENCE_MISSING")
    elif pay.booked_at < inv.issued_at:
        blockers.add("BANK_DATE_PRECEDES_INVOICE")
    if not pay.service_periods or not inv.service_periods:
        blockers.add("SERVICE_PERIOD_UNVERIFIED")
    elif not set(pay.service_periods).intersection(inv.service_periods):
        blockers.add("SERVICE_PERIOD_CONFLICT")
    elif not set(inv.service_periods).issubset(pay.service_periods):
        blockers.add("MULTIMONTH_SERVICE_COVERAGE_UNVERIFIED")
    if not pay.narration_refs:
        blockers.add("EXACT_MXP_REFERENCE_NOT_PROVEN")
    elif pay.narration_refs != (inv.key,):
        blockers.add("CONTRADICTORY_OR_MULTIPLE_MXP_REFERENCES")
    if credit > outstanding:
        blockers.add("CREDIT_EXCEEDS_INVOICE_OUTSTANDING")
    if outstanding == 0:
        blockers.add("NO_UNPAID_BALANCE")
    if credit == gst or pay.gst_component_only:
        blockers.add("GST_COMPONENT_REQUIRES_SEPARATE_LEDGER_PROOF")

    rates = exact_tds_hypotheses(pay, inv)
    if not rates:
        blockers.add("EXACT_GROSS_TDS_AMOUNT_NOT_PROVEN")
    elif len(rates) > 1:
        blockers.add("COMPETING_TDS_RATE_HYPOTHESES")
    # A mathematically exact credit is never an approved financial match.
    return {
        "stage": "R17_SYNTHETIC_HYPOTHESIS_ONLY",
        "tds_rate_hypotheses_not_approved": list(rates),
        "decision": "HOLD_FOR_REVIEW" if blockers else "CANDIDATE_FOR_INDEPENDENT_REVIEW",
        "blocker_codes": sorted(blockers),
        "financial_status": None,
        "payment_allocated": False,
        "invoice_updated": False,
        "financial_apply_locked": True,
    }


def dnm01_review(best_delta, runner_up_delta, age_days, *, contradictory_ref=False):
    """Test conservative DNM gates without claiming DNM-01 settlement parity."""
    if type(age_days) is not int or age_days < 0:
        refuse("DNM_SOURCE_DATE_EVIDENCE_REQUIRED")
    if type(contradictory_ref) is not bool:
        refuse("DNM_CONTRADICTION_FLAG_REQUIRED")
    best = abs(money(best_delta))
    second = abs(money(runner_up_delta))
    blockers = []
    if age_days > 180:
        blockers.append("DNM_OVER_180_DAYS")
    if best > Decimal("10.00"):
        blockers.append("DNM_OUTSIDE_10_RUPEE_SEARCH")
    if best > Decimal("1.00"):
        blockers.append("DNM_BEST_NOT_WITHIN_1_RUPEE")
    if second - best < Decimal("2.00"):
        blockers.append("DNM_RUNNER_UP_NOT_SEPARATED_BY_2_RUPEES")
    if contradictory_ref:
        blockers.append("DNM_CONTRADICTORY_MXP_REFERENCE")
    return {
        "decision": "HOLD_FOR_REVIEW" if blockers else "DNM_HYPOTHESIS_REVIEW_ONLY",
        "blocker_codes": blockers,
        "financial_status": None,
        "allocation_executed": False,
        "financial_apply_locked": True,
    }


def audit_shadow_reservations(payments, invoices, proposals):
    """Pure global *capacity* diagnostic for proposed synthetic edges.

    No matching or applying. A positive capacity audit never certifies any
    matching method, approved ledger, transaction, or financial permission.
    """
    if not isinstance(payments, (list, tuple)) or not isinstance(invoices, (list, tuple)):
        refuse("SYNTHETIC_INPUT_COLLECTION_REQUIRED")
    if not isinstance(proposals, (list, tuple)):
        refuse("SYNTHETIC_PROPOSAL_COLLECTION_REQUIRED")
    for pay in payments:
        _check_payment(pay)
    for inv in invoices:
        _check_invoice(inv)
    seen_pays = Counter(p.key for p in payments)
    seen_invoices = Counter(i.key for i in invoices)
    problems = set()
    if any(n > 1 for n in seen_pays.values()):
        problems.add("DUPLICATE_BANK_SOURCE_ROW")
    if any(n > 1 for n in seen_invoices.values()):
        problems.add("DUPLICATE_INVOICE_NUMBER")
    pays = {p.key: p for p in payments}
    invs = {i.key: i for i in invoices}
    by_payment = defaultdict(lambda: Decimal("0.00"))
    by_invoice = defaultdict(lambda: Decimal("0.00"))
    edge_keys = set()
    for edge in proposals:
        if not isinstance(edge, SyntheticReservation):
            refuse("SYNTHETIC_RESERVATION_TYPE_REQUIRED")
        if not re.fullmatch(r"SYN-PAY-[0-9]{3,6}", edge.payment_key):
            refuse("SYNTHETIC_PAYMENT_KEY_REQUIRED")
        if not re.fullmatch(r"SYN-MXP-[0-9]{3,6}", edge.invoice_key):
            refuse("SYNTHETIC_INVOICE_KEY_REQUIRED")
        value = money(edge.amount)
        if value <= 0:
            problems.add("NONPOSITIVE_PROPOSED_RESERVATION")
        if (edge.payment_key, edge.invoice_key) in edge_keys:
            problems.add("DUPLICATE_PROPOSED_EDGE")
        edge_keys.add((edge.payment_key, edge.invoice_key))
        pay, inv = pays.get(edge.payment_key), invs.get(edge.invoice_key)
        if pay is None or inv is None:
            problems.add("UNKNOWN_SOURCE_ROW_OR_INVOICE")
            continue
        if nonblank(inv.original_s_marker):
            problems.add("INVOICE_S_NONBLANK_PROTECTED")
        if not inv.sol or pay.sol != inv.sol:
            problems.add("SBISA_OR_CROSS_SOL_UNAPPROVED")
        if _normalized_client(pay.client) != _normalized_client(inv.client):
            problems.add("CLIENT_IDENTITY_CONFLICT")
        if money(pay.credit) <= 0:
            problems.add("NONPOSITIVE_BANK_CREDIT")
        if pay.original_bank_status.strip():
            problems.add("PRIOR_BANK_STATUS_NOT_REVALIDATED")
        by_payment[edge.payment_key] += value
        by_invoice[edge.invoice_key] += value
    for key, total in by_payment.items():
        if total > money(pays[key].credit):
            problems.add("PAYMENT_CREDIT_OVER_RESERVED")
    for key, total in by_invoice.items():
        if total > money(invs[key].outstanding):
            problems.add("INVOICE_BALANCE_OVER_RESERVED")
    return {
        "stage": "R17_SYNTHETIC_CAPACITY_CHECK_ONLY",
        "source_payment_rows": len(payments),
        "source_invoice_rows": len(invoices),
        "hypothesis_edges_seen": len(proposals),
        "capacity_constraints_passed": not problems,
        "blocker_codes": sorted(problems),
        "amounts_and_source_ids_exposed": False,
        "financial_statuses_written": False,
        "real_payment_allocations": 0,
        "authoritative_ledger_connected": False,
        "financial_database_connected": False,
        "v251_method_parity_certified": False,
        "financial_apply_locked": True,
    }
