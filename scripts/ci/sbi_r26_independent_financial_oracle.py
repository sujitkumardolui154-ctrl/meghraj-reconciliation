"""R26 independent SYNTHETIC-ONLY financial evidence oracle.

Not the certified Master v2.51 / Matrix v2.39 engine. Provides pure, limited
adversarial financial invariants; no original Excel, SOL master, Firebase,
PostgreSQL, settlement, invoice writes, or status 'OK' assignment. A PASS from
this module NEVER authorizes financial payment allocation.

The only permitted identifiers are SYN-* fixture references.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENT = Decimal("0.01")
SOL = re.compile(r"[0-9]{1,12}\Z")
INVOICE_ID = re.compile(r"SYN-MXP-[0-9]{3,6}\Z")
PAYMENT_ID = re.compile(r"SYN-PAY-[0-9]{3,6}\Z")
PERIOD = re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")
METHODS = ("STANDARD", "EXCEPTION_REVIEW", "DNM_REVIEW", "GLOBAL_ADJUDICATION", "WATERFALL")
TDS_RATES = (0, 1, 2, 3)


class R26Refusal(ValueError):
    """Return stable refusal reason, never a private financial value."""


def amount(v) -> Decimal:
    """Accept exact two-decimal money only; no binary floats or rounding away evidence."""
    if isinstance(v, (float, bool)) or not isinstance(v, (str, int, Decimal)):
        raise R26Refusal("UNSAFE_MONEY_TYPE")
    try:
        x = Decimal(str(v))
    except (ValueError, InvalidOperation):
        raise R26Refusal("INVALID_MONEY")
    if not x.is_finite() or x != x.quantize(CENT):
        raise R26Refusal("NONFINITE_OR_SUBCENT_MONEY")
    return x


@dataclass(frozen=True)
class Invoice:
    key: str
    sol: str
    client: str
    taxable: str
    cgst: str
    sgst: str
    gross: str
    outstanding: str
    issue_date: date
    service_periods: tuple[str, ...]
    source_s_marker: object = None


@dataclass(frozen=True)
class Payment:
    key: str
    sol: str
    client: str
    credit: str
    bank_date: date
    service_periods: tuple[str, ...]
    mxp_refs: tuple[str, ...]
    original_k: object = None
    gst_narration: bool = False


@dataclass(frozen=True)
class Edge:
    payment_key: str
    invoice_key: str
    reservation: str
    method: str = "STANDARD"


def _valid_periods(values):
    return isinstance(values, tuple) and all(
        isinstance(v, str) and PERIOD.fullmatch(v) for v in values
    )


def _synthetic_invoice(inv: Invoice):
    if not isinstance(inv, Invoice) or not INVOICE_ID.fullmatch(inv.key):
        raise R26Refusal("SYNTHETIC_INVOICE_REQUIRED")
    if not isinstance(inv.sol, str) or (inv.sol and not SOL.fullmatch(inv.sol)):
        raise R26Refusal("INVALID_SYNTHETIC_INVOICE_SOL")
    if not isinstance(inv.client, str) or not inv.client.startswith("SYNTHETIC "):
        raise R26Refusal("SYNTHETIC_INVOICE_CLIENT_REQUIRED")
    if type(inv.issue_date) is not date or not _valid_periods(inv.service_periods):
        raise R26Refusal("INVALID_INVOICE_DATE_OR_PERIOD")
    taxable, cgst, sgst, gross, outstanding = map(
        amount, (inv.taxable, inv.cgst, inv.sgst, inv.gross, inv.outstanding)
    )
    if min(taxable, cgst, sgst, outstanding) < 0 or gross <= 0:
        raise R26Refusal("INVALID_INVOICE_AMOUNTS")
    if taxable + cgst + sgst != gross:
        raise R26Refusal("GROSS_COMPONENTS_NOT_CONSERVED")
    if outstanding > gross:
        raise R26Refusal("OUTSTANDING_OVER_GROSS")
    return taxable, cgst, sgst, gross, outstanding


def _synthetic_payment(pay: Payment):
    if not isinstance(pay, Payment) or not PAYMENT_ID.fullmatch(pay.key):
        raise R26Refusal("SYNTHETIC_PAYMENT_REQUIRED")
    if not isinstance(pay.sol, str) or not SOL.fullmatch(pay.sol):
        raise R26Refusal("INVALID_SYNTHETIC_PAYMENT_SOL")
    if not isinstance(pay.client, str) or not pay.client.startswith("SYNTHETIC "):
        raise R26Refusal("SYNTHETIC_PAYMENT_CLIENT_REQUIRED")
    if type(pay.bank_date) is not date or not _valid_periods(pay.service_periods):
        raise R26Refusal("INVALID_PAYMENT_DATE_OR_PERIOD")
    if not isinstance(pay.mxp_refs, tuple) or any(
        not isinstance(v, str) or not INVOICE_ID.fullmatch(v)
        for v in pay.mxp_refs
    ):
        raise R26Refusal("UNTRUSTED_MXP_REFERENCE")
    if type(pay.gst_narration) is not bool:
        raise R26Refusal("GST_PROVENANCE_MUST_BE_BOOLEAN")
    return amount(pay.credit)


def money_hypotheses(pay: Payment, inv: Invoice) -> tuple[int, ...]:
    """0/1/2/3 percent TDS on taxable, ROUND_HALF_UP; hypothesis only."""
    credit = _synthetic_payment(pay)
    taxable, _, _, gross, _ = _synthetic_invoice(inv)
    matches = []
    for rate in TDS_RATES:
        tds = (taxable * Decimal(rate) / Decimal(100)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        if gross - tds == credit:
            matches.append(rate)
    return tuple(matches)


def pair_review(pay: Payment, inv: Invoice) -> dict:
    """Corroboration and blocker codes, never an authorized financial match."""
    credit = _synthetic_payment(pay)
    _, cgst, sgst, _, outstanding = _synthetic_invoice(inv)
    reasons = set()
    if credit <= 0:
        reasons.add("NONPOSITIVE_CREDIT")
    if not inv.sol:
        reasons.add("SBISA_BLANK_SOL_REQUIRES_APPROVAL")
    elif pay.sol != inv.sol:
        reasons.add("SBISA_EXCEPTION_REQUIRES_DOCUMENTED_APPROVAL"
                    if pay.sol == "1" else "CROSS_SOL_NOT_APPROVED")
    if " ".join(pay.client.casefold().split()) != " ".join(inv.client.casefold().split()):
        reasons.add("CLIENT_IDENTITY_CONFLICT")
    if pay.bank_date < inv.issue_date:
        reasons.add("BANK_BEFORE_INVOICE_DATE")
    if not pay.service_periods or not inv.service_periods:
        reasons.add("SERVICE_PERIOD_MISSING")
    elif not set(inv.service_periods).intersection(pay.service_periods):
        reasons.add("SERVICE_PERIOD_CONFLICT")
    elif not set(inv.service_periods).issubset(pay.service_periods):
        reasons.add("MULTI_MONTH_COVERAGE_INCOMPLETE")
    if pay.mxp_refs != (inv.key,):
        reasons.add("MXP_REFERENCE_MISSING_OR_CONTRADICTORY")
    if inv.source_s_marker is not None and not (
        isinstance(inv.source_s_marker, str) and not inv.source_s_marker.strip()
    ):
        reasons.add("ORIGINAL_INVOICE_S_NONBLANK_PROTECTED")
    if pay.original_k is not None and not (
        isinstance(pay.original_k, str) and not pay.original_k.strip()
    ):
        reasons.add("ORIGINAL_BANK_K_REQUIRES_LEDGER_REVIEW")
    if outstanding == 0:
        reasons.add("NO_REMAINING_OUTSTANDING")
    if credit > outstanding:
        reasons.add("CREDIT_OVER_UNRESERVED_OUTSTANDING")
    rates = money_hypotheses(pay, inv)
    if not rates:
        reasons.add("EXACT_GROSS_NET_TDS_NOT_ESTABLISHED")
    elif len(rates) > 1:
        reasons.add("TDS_HYPOTHESES_NOT_UNIQUE")
    if pay.gst_narration or credit == cgst + sgst:
        reasons.add("GST_COMPONENT_REQUIRES_SEPARATE_LEDGER_PROOF")
    return {
        "stage": "R26_SYNTHETIC_PAIR_REVIEW_ONLY",
        "evidence_decision": "CANDIDATE_INDEPENDENT_REVIEW_ONLY" if not reasons else "HOLD",
        "reason_codes": sorted(reasons),
        "tds_rates_hypotheses_only": rates,
        "payment_allocation_executed": False,
        "financial_status": None,
        "financial_apply_locked": True,
    }


def global_reservation_review(payments, invoices, edges) -> dict:
    """Single hypothetical ledger capacity check. NEVER allocates any credit.

    Edge amounts are intended reservations for a deliberately synthetic graph.
    Phase order is checked: WATERFALL may only come after GLOBAL_ADJUDICATION,
    and no earlier method may be replayed after WATERFALL.
    """
    if not all(isinstance(x, (list, tuple)) for x in (payments, invoices, edges)):
        raise R26Refusal("SYNTHETIC_COLLECTIONS_REQUIRED")
    if max(len(payments), len(invoices), len(edges)) > 200:
        raise R26Refusal("SYNTHETIC_FIXTURE_TOO_LARGE")
    for p in payments:
        _synthetic_payment(p)
    for i in invoices:
        _synthetic_invoice(i)
    keys_p = Counter(x.key for x in payments)
    keys_i = Counter(x.key for x in invoices)
    problems = set()
    if any(n > 1 for n in keys_p.values()):
        problems.add("DUPLICATE_SOURCE_BANK_ROW")
    if any(n > 1 for n in keys_i.values()):
        problems.add("DUPLICATE_SOURCE_INVOICE_NO")
    by_pay = {p.key:p for p in payments}
    by_inv = {i.key:i for i in invoices}
    reserved_credit = defaultdict(lambda: Decimal("0.00"))
    reserved_invoice = defaultdict(lambda: Decimal("0.00"))
    edges_seen = set()
    waterfall_started = False
    global_stage_seen = False
    for edge in edges:
        if not isinstance(edge, Edge):
            raise R26Refusal("SYNTHETIC_EDGE_REQUIRED")
        if edge.method not in METHODS:
            raise R26Refusal("UNAPPROVED_METHOD_NAME")
        if not PAYMENT_ID.fullmatch(edge.payment_key) or not INVOICE_ID.fullmatch(edge.invoice_key):
            raise R26Refusal("NON_SYNTHETIC_EDGE_REFERENCE")
        val = amount(edge.reservation)
        if val <= 0:
            problems.add("NONPOSITIVE_RESERVATION")
        pair = edge.payment_key, edge.invoice_key
        if pair in edges_seen:
            problems.add("DUPLICATE_RESERVATION_EDGE")
        edges_seen.add(pair)
        if edge.method == "GLOBAL_ADJUDICATION":
            if waterfall_started:
                problems.add("GLOBAL_LEDGER_ADJUDICATION_AFTER_WATERFALL")
            global_stage_seen = True
        elif edge.method == "WATERFALL":
            if not global_stage_seen:
                problems.add("WATERFALL_BEFORE_GLOBAL_ADJUDICATION")
            waterfall_started = True
        elif waterfall_started:
            problems.add("WATERFALL_NOT_LAST")
        pay, inv = by_pay.get(edge.payment_key), by_inv.get(edge.invoice_key)
        if pay is None or inv is None:
            problems.add("UNKNOWN_PAYMENT_OR_INVOICE_EDGE")
            continue
        if pay.sol != inv.sol or not inv.sol:
            problems.add("UNAPPROVED_CROSS_SOL_OR_SBISA")
        if " ".join(pay.client.lower().split()) != " ".join(inv.client.lower().split()):
            problems.add("CLIENT_NAME_CONFLICT")
        if inv.source_s_marker is not None and not (
            isinstance(inv.source_s_marker, str) and not inv.source_s_marker.strip()
        ):
            problems.add("PROTECTED_INVOICE_S")
        if pay.original_k is not None and not (
            isinstance(pay.original_k, str) and not pay.original_k.strip()
        ):
            problems.add("PROTECTED_BANK_K")
        if pay.bank_date < inv.issue_date:
            problems.add("BANK_DATE_PRECEDES_INVOICE")
        if not pay.service_periods or not set(inv.service_periods).issubset(pay.service_periods):
            problems.add("UNVERIFIED_SERVICE_PERIOD_COVERAGE")
        if pay.mxp_refs != (inv.key,):
            problems.add("CONTRADICTORY_REFERENCE")
        if val > amount(pay.credit):
            problems.add("SINGLE_RESERVATION_OVER_CREDIT")
        reserved_credit[pay.key] += val
        reserved_invoice[inv.key] += val
    for key, val in reserved_credit.items():
        if val > amount(by_pay[key].credit):
            problems.add("GLOBAL_CREDIT_OVERALLOCATED")
    for key, val in reserved_invoice.items():
        if val > amount(by_inv[key].outstanding):
            problems.add("INVOICE_OVERALLOCATED")
    if any(amount(p.credit) <= 0 for p in payments):
        problems.add("NONPOSITIVE_CREDIT_IN_LEDGER")
    return {
        "stage": "R26_SYNTHETIC_GLOBAL_CAPACITY_REVIEW_ONLY",
        "review_capacity_pass": not problems,
        "reason_codes": sorted(problems),
        "source_payment_count": len(payments),
        "source_invoice_count": len(invoices),
        "candidate_edge_count": len(edges),
        "real_ledger_connected": False,
        "real_payments_allocated": 0,
        "financial_status": None,
        "v251_method_parity_certified": False,
        "financial_apply_locked": True,
    }


def source_delta_gate(source_sha256, previous_sha256) -> dict:
    """No cross-workbook method parity unless hashes truly agree."""
    valid = lambda s: isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s)
    if not valid(source_sha256) or not valid(previous_sha256):
        raise R26Refusal("EXACT_SOURCE_SHA256_REQUIRED")
    equal = source_sha256 == previous_sha256
    return {
        "status": "SAME_SOURCE_CAN_COMPARE_ONLY_AFTER_ORACLE" if equal
                  else "DIFFERENT_SOURCE_NO_FINANCIAL_STATUS_PARITY",
        "source_hashes_identical": equal,
        "automatic_historical_OK_copying": False,
        "v251_certified": False,
        "financial_apply_locked": True,
    }


def release_readiness():
    """No caller-controlled booleans can claim full v2.51 certification."""
    return {
        "stage": "R26_PARTIAL_INDEPENDENT_FINANCIAL_ORACLE",
        "r25_owner_approved_master": False,
        "complete_master_v251_executable_certified": False,
        "matrix_v239_method_parity_certified": False,
        "real_financial_source_ledger_oracle_passed": False,
        "actual_v218_financial_writer_parity_passed": False,
        "real_staging_auth_and_database_passed": False,
        "finance_security_production_signoff": False,
        "financial_apply_locked": True,
        "real_financial_allocation_count": 0,
        "production_release_authorized": False,
    }
