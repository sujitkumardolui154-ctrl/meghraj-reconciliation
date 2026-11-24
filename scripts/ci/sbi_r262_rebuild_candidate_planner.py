"""R26.2 first-pass reconstruction: SYNTHETIC-ONLY candidate planner.

NEVER the certified Master v2.51 / Matrix v2.39 finance engine. There is no
bank workbook importer, status setter, cloud database connector, or apply path.
All input invoice/payment IDs must be SYN-*; all output edges are hypothetical.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import re
import unicodedata

from sbi_r26_independent_financial_oracle import (
    Edge, R26Refusal, amount, pair_review, global_reservation_review,
    _synthetic_invoice, _synthetic_payment,
)

VERSION = "R262_V251_REBUILD_CANDIDATE_NOT_CERTIFIED"
CENT = Decimal("0.01")
SOL_RE = re.compile(r"[0-9]{1,12}\Z")
MAX_FIXTURE_ROWS = 100


class RebuildRefusal(ValueError):
    """Fail-closed constant error code; never includes sensitive source data."""


def norm(value):
    if not isinstance(value, str):
        return ""
    return " ".join(
        unicodedata.normalize("NFKC", value).strip().casefold().split()
    )


def blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def fixture_digest(invoices, payments, master_rows):
    """Synthetic fixture hash only; not fresh-bank-source provenance."""
    raw = {
        "invoices": [asdict(i) for i in sorted(invoices, key=lambda x: x.key)],
        "payments": [asdict(p) for p in sorted(payments, key=lambda x: x.key)],
        "master": sorted([list(pair) for pair in master_rows]),
    }
    return sha256(json.dumps(
        raw, sort_keys=True, separators=(",", ":"), default=str,
    ).encode()).hexdigest()


def _check_inputs(invoices, payments, master_rows, expected_sha):
    if any(type(v) not in (list, tuple) for v in (invoices, payments, master_rows)):
        raise RebuildRefusal("SYNTHETIC_COLLECTIONS_REQUIRED")
    if max(len(invoices), len(payments), len(master_rows)) > MAX_FIXTURE_ROWS:
        raise RebuildRefusal("SYNTHETIC_FIXTURE_TOO_LARGE")
    if not isinstance(expected_sha, str) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_sha
    ):
        raise RebuildRefusal("EXPLICIT_FIXTURE_SHA_REQUIRED")
    for i in invoices:
        _synthetic_invoice(i)
    for p in payments:
        _synthetic_payment(p)
    masters = defaultdict(set)
    for item in master_rows:
        if type(item) not in (tuple, list) or len(item) != 2:
            raise RebuildRefusal("MASTER_SOL_NAME_PAIR_REQUIRED")
        sol, official = item
        if (not isinstance(sol, str) or not SOL_RE.fullmatch(sol)
                or not isinstance(official, str)
                or not official.startswith("SYNTHETIC ")):
            raise RebuildRefusal("SYNTHETIC_MASTER_ONLY")
        masters[sol].add(norm(official))
    if any(len(values) > 1 for values in masters.values()):
        raise RebuildRefusal("CONFLICTING_MASTER_OFFICIAL_NAMES")
    if fixture_digest(invoices, payments, master_rows) != expected_sha:
        raise RebuildRefusal("FIXTURE_SHA256_MISMATCH")
    return {(sol, next(iter(names))) for sol, names in masters.items()}


def _basic_hold(payment, invoice, verified_master):
    if not blank(payment.original_k) or not blank(invoice.source_s_marker):
        return "PROTECTED_ORIGINAL_K_OR_S"
    if payment.gst_narration:
        return "GST_LATER_LEDGER_PROOF_REQUIRED"
    if not invoice.sol or payment.sol != invoice.sol:
        return "SBISA_CROSS_SOL_REQUIRES_AUTHORIZATION"
    if norm(payment.client) != norm(invoice.client):
        return "CLIENT_IDENTITY_CONFLICT"
    if (payment.sol, norm(payment.client)) not in verified_master:
        return "OFFICIAL_MASTER_IDENTITY_UNVERIFIED"
    if payment.bank_date < invoice.issue_date:
        return "BANK_DATE_PRECEDES_INVOICE"
    if not invoice.service_periods or not set(invoice.service_periods).issubset(
        payment.service_periods
    ):
        return "SERVICE_PERIOD_COVERAGE_MISSING"
    if amount(payment.credit) <= 0:
        return "NONPOSITIVE_CREDIT"
    if amount(invoice.outstanding) <= 0:
        return "NO_OUTSTANDING"
    if amount(payment.credit) > amount(invoice.outstanding):
        return "CREDIT_EXCEEDS_OUTSTANDING"
    return ""


def _dnm_review(payment, invoices, verified_master):
    """Nonbinding DNM-01: ±₹10, lead ≤₹1, next ≥₹2 away, age ≤180 days."""
    viable = []
    for invoice in invoices:
        if _basic_hold(payment, invoice, verified_master):
            continue
        age = (payment.bank_date - invoice.issue_date).days
        if age < 0 or age > 180:
            continue
        gross = amount(invoice.gross)
        taxable = amount(invoice.taxable)
        credit = amount(payment.credit)
        delta = min(abs(
            credit - (gross - (
                taxable * Decimal(rate) / Decimal(100)
            ).quantize(CENT, rounding=ROUND_HALF_UP))
        ) for rate in (0, 1, 2, 3))
        if delta <= Decimal("10.00"):
            viable.append((delta, invoice.key))
    viable.sort()
    if not viable:
        return None, "DNM_NO_CANDIDATE_WITHIN_10"
    if viable[0][0] > Decimal("1.00"):
        return None, "DNM_BEST_OVER_1"
    if len(viable) > 1 and viable[1][0] - viable[0][0] < Decimal("2.00"):
        return None, "DNM_COMPETING_RUNNER_UP"
    return viable[0][1], "DNM_REVIEW_ONLY"


def plan_synthetic_only(
    invoices, payments, master_rows, *, expected_fixture_sha256,
    financial_apply="LOCKED",
):
    if financial_apply != "LOCKED":
        raise RebuildRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    masters = _check_inputs(
        invoices, payments, master_rows, expected_fixture_sha256,
    )
    duplicate_invoices = {
        key for key, count in Counter(i.key for i in invoices).items()
        if count > 1
    }
    duplicate_payments = {
        key for key, count in Counter(p.key for p in payments).items()
        if count > 1
    }
    by_invoice = {
        i.key: i for i in invoices if i.key not in duplicate_invoices
    }
    proposals = []
    holds = []
    for payment in sorted(payments, key=lambda p: p.key):
        if payment.key in duplicate_payments:
            holds.append((payment.key, "DUPLICATE_SOURCE_PAYMENT"))
            continue
        if not blank(payment.original_k):
            holds.append((payment.key, "ORIGINAL_BANK_K_PROTECTED"))
            continue
        if amount(payment.credit) <= 0:
            holds.append((payment.key, "NONPOSITIVE_CREDIT"))
            continue
        if payment.gst_narration:
            holds.append((payment.key, "GST_SOURCE_PROOF_REQUIRED"))
            continue
        if len(payment.mxp_refs) > 1:
            holds.append((payment.key, "MULTIPLE_MXP_REFERENCES"))
            continue
        if len(payment.mxp_refs) == 1:
            ref = payment.mxp_refs[0]
            if ref in duplicate_invoices:
                holds.append((payment.key, "DUPLICATE_INVOICE_QUARANTINE"))
                continue
            invoice = by_invoice.get(ref)
            if invoice is None:
                holds.append((payment.key, "EXACT_MXP_REFERENCE_UNAVAILABLE"))
                continue
            reason = _basic_hold(payment, invoice, masters)
            if reason:
                holds.append((payment.key, reason))
                continue
            oracle = pair_review(payment, invoice)
            if oracle["evidence_decision"] != "CANDIDATE_INDEPENDENT_REVIEW_ONLY":
                holds.append((payment.key, "INDEPENDENT_TDS_ORACLE_HOLD"))
                continue
            proposals.append((
                payment.key, invoice.key, str(amount(payment.credit)),
                "EXACT_MXP_TDS_REVIEW",
            ))
            continue
        # No explicit MXP reference: evaluate only DNM hypothesis, never OK.
        key, reason = _dnm_review(payment, invoices, masters)
        if key is None:
            holds.append((payment.key, reason))
        else:
            proposals.append((
                payment.key, key, str(amount(payment.credit)),
                "DNM01_PROVISIONAL_REVIEW",
            ))
    # Global capacity is independently checked on the exact-reference
    # subgraph only. Provisional DNM edges have no authorization to allocate.
    exact = [v for v in proposals if v[3] == "EXACT_MXP_TDS_REVIEW"]
    graph = global_reservation_review(
        list(payments), list(invoices),
        [Edge(p, i, value, "STANDARD") for p, i, value, _ in exact],
    )
    if not graph["review_capacity_pass"]:
        blocked = {row[0] for row in exact}
        proposals = [row for row in proposals if row[0] not in blocked]
        holds.extend((key, "GLOBAL_CAPACITY_REVIEW_HOLD") for key in blocked)
    return {
        "stage": VERSION,
        "synthetic_fixture_sha256": expected_fixture_sha256,
        "payment_rows_reviewed": len(payments),
        "invoice_rows_reviewed": len(invoices),
        "review_candidate_edges": tuple(proposals),
        "payment_holds": tuple(sorted(holds)),
        "global_capacity_exact_reference_only": graph["review_capacity_pass"],
        "dnm_provisional_only": True,
        "partial_waterfall_implemented": False,
        "approved_sbisa_or_cross_sol_implemented": False,
        "complete_v251_v239_certified": False,
        "authoritative_oct27_master_data_loaded": False,
        "real_ledger_connected": False,
        "financial_status": None,
        "real_financial_allocations": 0,
        "production_database_writes": 0,
        "financial_apply_locked": True,
        "production_release_authorized": False,
    }
