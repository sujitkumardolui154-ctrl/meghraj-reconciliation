"""SBI R26.9 Case 2.1 — deterministic core *dry-run* cash conservation ledger.

Master v2.51 owns the allocation register. Matrix v2.39 supplies proposed
edges only. This module enforces source identifiers, available cash and invoice
cash capacity for controlled dry-run simulations; it has NO banking, XLSX,
database, status-writer or production Apply interfaces.

This is NOT the approved full v2.51/v2.39 reconciliation engine: matching
eligibility, actual TDS, GST/credit notes, DNM adjudication, duplicate payment
proof, watermark/prior settlements and Finance signoff require later stages.
All cash-gap values are cash coverage ONLY, not certified receivables.

No confidential SBI customer row is required or bundled into CI.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
ALLOWED_PRIOR = frozenset({
    "EXACT_MXP_REVIEW", "SAME_SOL_REVIEW", "PARTIAL_REVIEW",
    "GST_COMPONENT_REVIEW", "SBISA_REVIEW", "CROSS_SOL_REVIEW",
})
WATERFALL = "WATERFALL_REVIEW"
DISALLOWED_PROVISIONAL = frozenset({"DNM_PROVISIONAL", "DNM01_PROVISIONAL_NO_RESERVATION"})
STAGE = "R269_CASE21_CORE_CASH_LEDGER_DRY_RUN_ONLY"


class LedgerRefusal(ValueError):
    """Constant refusal; no sensitive customer or amount printed."""


def money(raw):
    if type(raw) not in (str, Decimal):
        raise LedgerRefusal("EXACT_DECIMAL_MONEY_REQUIRED")
    try:
        value = Decimal(raw.strip() if isinstance(raw, str) else raw)
    except (InvalidOperation, ValueError):
        raise LedgerRefusal("INVALID_FINANCIAL_MONEY")
    if not value.is_finite() or value != value.quantize(CENT):
        raise LedgerRefusal("NONFINITE_OR_SUBPAISE_MONEY_REFUSED")
    return value.quantize(CENT)


def _blank(raw):
    return raw is None or type(raw) is str and not raw.strip()


@dataclass(frozen=True)
class InvoiceCapacity:
    invoice_no: str
    source_row: int
    gross: str
    original_s: object = None


@dataclass(frozen=True)
class BankCapacity:
    bank_key: str
    source_row: int
    credit: str
    original_k: object = None


@dataclass(frozen=True)
class MatrixProposal:
    bank_key: str
    invoice_no: str
    portion: str
    method: str
    evidence_ref: str


@dataclass(frozen=True)
class GlobalAdjudicationBoundary:
    marker: str = "GLOBAL_ADJUDICATION_BEFORE_WATERFALL"


def plan_digest(steps):
    """Stable audit fingerprint, NOT cryptographic Finance authorization."""
    return sha256(json.dumps(
        [{"kind": type(x).__name__, **asdict(x)} for x in steps],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def dry_run_cash_ledger(
    invoices, banks, steps, *,
    source_sha256, master_sha256, expected_plan_sha256,
    financial_apply="LOCKED",
):
    """Run all candidate reservations atomically without durable financial writes.

    The returned shadow ledger has no classification authority. Any violation
    raises LedgerRefusal and no candidate allocation result is returned.
    """
    if financial_apply != "LOCKED":
        raise LedgerRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if any(type(x) is not str or not SHA256.fullmatch(x)
           for x in (source_sha256, master_sha256, expected_plan_sha256)):
        raise LedgerRefusal("THREE_EXPLICIT_SHA256_MANIFESTS_REQUIRED")
    if (type(invoices) not in (tuple, list) or type(banks) not in (tuple, list)
            or type(steps) not in (tuple, list)
            or len(invoices) > 50000 or len(banks) > 50000
            or len(steps) > 100000):
        raise LedgerRefusal("RECORD_LIST_OR_SIZE_LIMIT")
    if plan_digest(steps) != expected_plan_sha256:
        raise LedgerRefusal("ALLOCATION_PLAN_SHA256_MISMATCH")

    iv, pay, invoice_rows, payment_rows = {}, {}, set(), set()
    for x in invoices:
        if (type(x) is not InvoiceCapacity
                or type(x.invoice_no) is not str or not x.invoice_no.startswith("MXP")
                or type(x.source_row) is not int or x.source_row < 2):
            raise LedgerRefusal("INVALID_INVOICE_IDENTITY")
        if x.invoice_no in iv or x.source_row in invoice_rows:
            raise LedgerRefusal("DUPLICATE_INVOICE_IDENTITY")
        if not _blank(x.original_s):
            raise LedgerRefusal("PROTECTED_INVOICE_S_NONBLANK")
        if money(x.gross) <= ZERO:
            raise LedgerRefusal("NONPOSITIVE_INVOICE_GROSS")
        iv[x.invoice_no] = x
        invoice_rows.add(x.source_row)

    for x in banks:
        if (type(x) is not BankCapacity
                or type(x.bank_key) is not str or not x.bank_key.strip()
                or type(x.source_row) is not int or x.source_row < 2):
            raise LedgerRefusal("INVALID_BANK_IDENTITY")
        if x.bank_key in pay or x.source_row in payment_rows:
            raise LedgerRefusal("DUPLICATE_BANK_IDENTITY")
        if not _blank(x.original_k):
            raise LedgerRefusal("PROTECTED_BANK_K_NONBLANK")
        if money(x.credit) <= ZERO:
            raise LedgerRefusal("NONPOSITIVE_BANK_CREDIT")
        pay[x.bank_key] = x
        payment_rows.add(x.source_row)

    credited = defaultdict(lambda: ZERO)
    invoiced = defaultdict(lambda: ZERO)
    edge_pairs = set()
    edges = []
    boundary_count = 0
    phase = "PRE_GLOBAL"

    for index, step in enumerate(steps, 1):
        if type(step) is GlobalAdjudicationBoundary:
            if boundary_count != 0 or step.marker != "GLOBAL_ADJUDICATION_BEFORE_WATERFALL":
                raise LedgerRefusal("GLOBAL_ADJUDICATION_REPEATED_OR_INVALID")
            boundary_count += 1
            phase = "WATERFALL_ONLY"
            continue
        if type(step) is not MatrixProposal:
            raise LedgerRefusal("UNKNOWN_MATRIX_PROPOSAL")
        if (type(step.method) is not str or
                step.method in DISALLOWED_PROVISIONAL):
            raise LedgerRefusal("PROVISIONAL_DNM_CANNOT_RESERVE_CASH")
        if step.method not in ALLOWED_PRIOR | {WATERFALL}:
            raise LedgerRefusal("UNAPPROVED_ALLOCATION_METHOD")
        if phase == "PRE_GLOBAL" and step.method == WATERFALL:
            raise LedgerRefusal("WATERFALL_BEFORE_GLOBAL_ADJUDICATION")
        if phase == "WATERFALL_ONLY" and step.method != WATERFALL:
            raise LedgerRefusal("EARLIER_METHOD_AFTER_WATERFALL_BOUNDARY")
        if step.bank_key not in pay or step.invoice_no not in iv:
            raise LedgerRefusal("UNKNOWN_BANK_OR_INVOICE_ID")
        if type(step.evidence_ref) is not str or not step.evidence_ref.strip():
            raise LedgerRefusal("EXPLICIT_CANDIDATE_EVIDENCE_REF_REQUIRED")
        pair = (step.bank_key, step.invoice_no)
        if pair in edge_pairs:
            raise LedgerRefusal("DUPLICATE_BANK_INVOICE_EDGE")
        portion = money(step.portion)
        if portion <= ZERO:
            raise LedgerRefusal("NONPOSITIVE_CASH_ALLOCATION")
        if credited[step.bank_key] + portion > money(pay[step.bank_key].credit):
            raise LedgerRefusal("BANK_CREDIT_CAPACITY_EXCEEDED")
        if invoiced[step.invoice_no] + portion > money(iv[step.invoice_no].gross):
            raise LedgerRefusal("INVOICE_CASH_CAPACITY_EXCEEDED")
        credited[step.bank_key] += portion
        invoiced[step.invoice_no] += portion
        edge_pairs.add(pair)
        edges.append((
            index, step.bank_key, step.invoice_no, str(portion),
            step.method, step.evidence_ref,
        ))

    if boundary_count != 1:
        raise LedgerRefusal("GLOBAL_ADJUDICATION_BOUNDARY_REQUIRED")

    bank_rows = tuple((
        x.bank_key, x.source_row, str(money(x.credit)),
        str(credited[x.bank_key]), str(money(x.credit)-credited[x.bank_key]),
    ) for x in sorted(banks, key=lambda x: x.source_row))
    inv_rows = tuple((
        x.invoice_no, x.source_row, str(money(x.gross)),
        str(invoiced[x.invoice_no]), str(money(x.gross)-invoiced[x.invoice_no]),
    ) for x in sorted(invoices, key=lambda x: x.source_row))

    bank_total = sum((money(x.credit) for x in banks), ZERO)
    bank_reserved = sum(credited.values(), ZERO)
    bank_unused = sum((money(x.credit) - credited[x.bank_key] for x in banks), ZERO)
    inv_total = sum((money(x.gross) for x in invoices), ZERO)
    inv_reserved = sum(invoiced.values(), ZERO)
    inv_cash_gap = sum((money(x.gross) - invoiced[x.invoice_no] for x in invoices), ZERO)
    if (bank_reserved != inv_reserved
            or bank_total != bank_reserved + bank_unused
            or inv_total != inv_reserved + inv_cash_gap):
        raise LedgerRefusal("INDEPENDENT_GLOBAL_CASH_CONSERVATION_FAILURE")
    return {
        "stage": STAGE,
        "source_sha256": source_sha256,
        "master_sha256": master_sha256,
        "plan_sha256": expected_plan_sha256,
        "shadow_edges": tuple(edges),
        "shadow_bank_rows": bank_rows,
        "shadow_invoice_cash_rows": inv_rows,
        "shadow_reserved_cash_total": str(bank_reserved),
        "shadow_unassigned_credit_total": str(bank_unused),
        "shadow_cash_coverage_gap_not_receivable": str(inv_cash_gap),
        "bank_global_cash_conserved": True,
        "invoice_global_cash_conserved": True,
        "one_global_boundary_before_waterfall": True,
        "source_files_edited": False,
        "financial_status": None,
        "real_bank_allocations": 0,
        "real_database_writes": 0,
        "complete_master_v251_matrix_v239_certified": False,
        "financial_apply_locked": True,
        "production_release_authorized": False,
    }
