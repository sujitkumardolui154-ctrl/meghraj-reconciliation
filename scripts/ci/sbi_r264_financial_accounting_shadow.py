"""R26.4 synthetic-only financial accounting / independent conservation rehearsal.

Extends the R26.3 global shadow WITHOUT any real bank/source, Excel import,
status writer, database, authentication, or release path. All TDS/credit-note
"evidence" is synthetic and cannot authorize a real financial settlement.

The illustrative gap can be reduced by separately evidenced synthetic TDS
and credit notes; it MUST NOT be called verified receivables or settlement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import re

from sbi_r26_independent_financial_oracle import (
    Invoice, Payment, _synthetic_invoice, _synthetic_payment, amount,
)
from sbi_r262_rebuild_candidate_planner import fixture_digest, blank
from sbi_r263_global_allocation_shadow import (
    GlobalGate, Proposal, SyntheticProof, proposal_digest, shadow_adjudicate,
)

STAGE = "R264_SYNTHETIC_GROSS_TDS_GST_CN_ACCOUNTING_NOT_CERTIFIED"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
TDS_KEY = re.compile(r"SYN-TDS-[0-9]{3,6}\Z")
CN_KEY = re.compile(r"SYN-CN-[0-9]{3,6}\Z")
SYNTHETIC_EVIDENCE = "SYNTHETIC_QA_ONLY"


class R264Refusal(ValueError):
    """Fail-closed structural refusal with no customer-identifying message."""


@dataclass(frozen=True)
class SyntheticTDS:
    key: str
    payment_key: str
    invoice_key: str
    rate_percent: int
    withholding: str
    authority: str = SYNTHETIC_EVIDENCE


@dataclass(frozen=True)
class SyntheticCreditNote:
    key: str
    invoice_key: str
    credit_gross: str
    issue_date: date
    authority: str = SYNTHETIC_EVIDENCE


def accounting_digest(tds_evidence, credit_notes):
    """SHA of exact audit evidence. Never a signature or Finance authorization."""
    return sha256(json.dumps({
        "tds": [asdict(x) for x in sorted(tds_evidence, key=lambda x: x.key)],
        "credit_notes": [asdict(x) for x in sorted(credit_notes, key=lambda x: x.key)],
    }, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _catalog(tds_evidence, credit_notes, by_pay, by_inv):
    if (type(tds_evidence) not in (tuple, list)
            or type(credit_notes) not in (tuple, list)
            or max(len(tds_evidence), len(credit_notes)) > 100):
        raise R264Refusal("SYNTHETIC_ACCOUNTING_EVIDENCE_LIMIT_REQUIRED")
    reasons = set()
    tds_per_invoice = defaultdict(lambda: ZERO)
    notes_per_invoice = defaultdict(lambda: ZERO)
    tds_keys = set()
    cn_keys = set()
    seen_tds_pairs = set()
    for entry in tds_evidence:
        if (not isinstance(entry, SyntheticTDS)
                or not isinstance(entry.key, str) or not TDS_KEY.fullmatch(entry.key)
                or entry.authority != SYNTHETIC_EVIDENCE
                or type(entry.rate_percent) is not int
                or entry.rate_percent not in (0, 1, 2, 3)):
            raise R264Refusal("INVALID_OR_REAL_TDS_EVIDENCE_REFUSED")
        if entry.key in tds_keys:
            reasons.add("DUPLICATE_TDS_EVIDENCE_KEY")
        tds_keys.add(entry.key)
        pair = entry.payment_key, entry.invoice_key
        if pair in seen_tds_pairs:
            reasons.add("REUSED_TDS_PAYMENT_INVOICE_EVIDENCE")
        seen_tds_pairs.add(pair)
        inv = by_inv.get(entry.invoice_key)
        if entry.payment_key not in by_pay or inv is None:
            reasons.add("TDS_UNLINKED_TO_SYNTHETIC_SOURCE")
            continue
        actual = amount(entry.withholding)
        taxable = amount(inv.taxable)
        expected = (taxable * Decimal(entry.rate_percent) / Decimal(100)).quantize(
            CENT, rounding=ROUND_HALF_UP,
        )
        if actual < ZERO or actual != expected:
            reasons.add("TDS_AMOUNT_OR_HALF_UP_RATE_MISMATCH")
        tds_per_invoice[entry.invoice_key] += actual
    for entry in credit_notes:
        if (not isinstance(entry, SyntheticCreditNote)
                or not isinstance(entry.key, str) or not CN_KEY.fullmatch(entry.key)
                or entry.authority != SYNTHETIC_EVIDENCE
                or type(entry.issue_date) is not date):
            raise R264Refusal("INVALID_OR_REAL_CREDIT_NOTE_EVIDENCE_REFUSED")
        if entry.key in cn_keys:
            reasons.add("DUPLICATE_CREDIT_NOTE_KEY")
        cn_keys.add(entry.key)
        inv = by_inv.get(entry.invoice_key)
        if inv is None:
            reasons.add("CREDIT_NOTE_UNLINKED_TO_SYNTHETIC_INVOICE")
            continue
        credit = amount(entry.credit_gross)
        if credit <= ZERO:
            reasons.add("CREDIT_NOTE_NONPOSITIVE")
        if entry.issue_date < inv.issue_date:
            reasons.add("CREDIT_NOTE_BEFORE_INVOICE_ISSUE")
        if not blank(inv.source_s_marker):
            reasons.add("CREDIT_NOTE_AGAINST_PROTECTED_INVOICE")
        notes_per_invoice[entry.invoice_key] += credit
    return reasons, tds_per_invoice, notes_per_invoice


def account_synthetic_only(
    invoices, payments, master_rows, steps, proofs=(), tds_evidence=(),
    credit_notes=(), *, expected_fixture_sha256,
    expected_plan_sha256, expected_accounting_sha256,
    financial_apply="LOCKED",
):
    """Ephemeral, all-or-nothing accounting check after R26.3 global gate.

    No transfer, settlement, ledger write or "OK" status is possible.
    """
    if financial_apply != "LOCKED":
        raise R264Refusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if (not isinstance(expected_accounting_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_accounting_sha256)):
        raise R264Refusal("EXPLICIT_ACCOUNTING_SHA256_REQUIRED")
    if accounting_digest(tds_evidence, credit_notes) != expected_accounting_sha256:
        raise R264Refusal("ACCOUNTING_EVIDENCE_SHA256_MISMATCH")

    # R26.3 verifies source/master digest, exact synthetic IDs, all input
    # evidence graph, global conservation, and waterfall last BEFORE R26.4.
    r263 = shadow_adjudicate(
        invoices, payments, master_rows, steps, proofs,
        expected_fixture_sha256=expected_fixture_sha256,
        expected_plan_sha256=expected_plan_sha256,
        financial_apply="LOCKED",
    )
    by_pay = {p.key: p for p in payments}
    by_inv = {i.key: i for i in invoices}
    # Duplicate IDs never overwrite previous rows and always block full batch.
    if len(by_pay) != len(payments) or len(by_inv) != len(invoices):
        raise R264Refusal("SOURCE_DUPLICATE_IDENTITIES_REFUSED")
    reasons, tds_by_inv, note_by_inv = _catalog(
        tds_evidence, credit_notes, by_pay, by_inv,
    )
    if not r263["atomic_shadow_review_pass"]:
        reasons.add("R263_GLOBAL_LEDGER_BLOCKED")
        reasons.update(r263["blocker_codes"])

    # Never invent accounting when source has zero/negative/non-finite credit.
    if any(amount(p.credit) <= ZERO for p in payments):
        reasons.add("NONPOSITIVE_BANK_CREDIT_REFUSED")

    shadow = tuple(r263["shadow_candidate_edges"])
    cash_pay = defaultdict(lambda: ZERO)
    cash_inv = defaultdict(lambda: ZERO)
    by_method = defaultdict(lambda: ZERO)
    linked = {(p, i) for p, i, _, _ in shadow}
    linked_tds = set()
    for entry in tds_evidence:
        if entry.invoice_key not in by_inv or entry.payment_key not in by_pay:
            continue
        if (entry.payment_key, entry.invoice_key) not in linked:
            reasons.add("TDS_WITHOUT_CASH_RESERVATION")
            continue
        if (entry.payment_key, entry.invoice_key) in linked_tds:
            reasons.add("MULTIPLE_TDS_FOR_ONE_CASH_EDGE")
        linked_tds.add((entry.payment_key, entry.invoice_key))
        pay = by_pay[entry.payment_key]
        if pay.mxp_refs != (entry.invoice_key,):
            reasons.add("TDS_REQUIRES_EXACT_INVOICE_REFERENCE")
        if not any(p == entry.payment_key and i == entry.invoice_key and kind in
                   ("STANDARD", "PARTIAL_REVIEW") for p, i, _, kind in shadow):
            reasons.add("TDS_REQUIRES_STANDARD_OR_PARTIAL_METHOD")

    for p, i, money, method in shadow:
        cash = amount(money)
        cash_pay[p] += cash
        cash_inv[i] += cash
        by_method[method] += cash

    # A single invoice cannot have two full taxable TDS reductions,
    # even across two different linked bank credits.
    tds_invoice_counts = Counter(x.invoice_key for x in tds_evidence)
    if any(n > 1 for n in tds_invoice_counts.values()):
        reasons.add("TDS_CLAIMED_MORE_THAN_ONCE_PER_INVOICE")

    for inv in invoices:
        opening = amount(inv.outstanding)
        if cash_inv[inv.key] + tds_by_inv[inv.key] + note_by_inv[inv.key] > opening:
            reasons.add("GROSS_CASH_TDS_CN_OVERSETTLEMENT")
        if tds_by_inv[inv.key] > (amount(inv.taxable) * Decimal("0.03")).quantize(
                CENT, rounding=ROUND_HALF_UP):
            reasons.add("TDS_INVOICE_RATE_CAP_EXCEEDED")
        gst_component = sum(
            (amount(money) for p, i, money, method in shadow
             if i == inv.key and method == "GST_REVIEW"), ZERO
        )
        if gst_component > amount(inv.cgst) + amount(inv.sgst):
            reasons.add("GST_COMPONENT_EXCEEDS_INVOICE_TAX")
        if note_by_inv[inv.key] > amount(inv.gross):
            reasons.add("CREDIT_NOTE_EXCEEDS_INVOICE_GROSS")
    for pay in payments:
        if cash_pay[pay.key] > amount(pay.credit):
            reasons.add("GLOBAL_CREDIT_OVERSPENT")
    all_cash = sum(cash_inv.values(), ZERO)
    all_tds = sum(tds_by_inv.values(), ZERO)
    all_cn = sum(note_by_inv.values(), ZERO)
    unassigned_cash = sum(
        (amount(p.credit) - cash_pay[p.key] for p in payments), ZERO
    )
    full_cash = sum((amount(p.credit) for p in payments), ZERO)
    if all_cash + unassigned_cash != full_cash:
        reasons.add("GLOBAL_BANK_CREDIT_CONSERVATION_FAILED")

    by_invoice_rows = ()
    by_payment_rows = ()
    if not reasons:
        by_invoice_rows = tuple((
            inv.key, str(amount(inv.outstanding)),
            str(cash_inv[inv.key]), str(tds_by_inv[inv.key]),
            str(note_by_inv[inv.key]),
            str(amount(inv.outstanding) - cash_inv[inv.key]
                - tds_by_inv[inv.key] - note_by_inv[inv.key]),
        ) for inv in sorted(invoices, key=lambda x: x.key))
        by_payment_rows = tuple((
            pay.key, str(amount(pay.credit)), str(cash_pay[pay.key]),
            str(amount(pay.credit) - cash_pay[pay.key]),
        ) for pay in sorted(payments, key=lambda x: x.key))
        illustrative_balance = sum((amount(x[5]) for x in by_invoice_rows), ZERO)
        opening_total = sum((amount(inv.outstanding) for inv in invoices), ZERO)
        if illustrative_balance + all_cash + all_tds + all_cn != opening_total:
            reasons.add("INDEPENDENT_INVOICE_EQUATION_FAILED")
    if reasons:
        by_invoice_rows = ()
        by_payment_rows = ()
    else:
        # Informative no-write scenario only, never an actual paid indicator.
        pass

    return {
        "stage": STAGE,
        "accounting_candidate_pass": not reasons,
        "blocker_codes": tuple(sorted(reasons)),
        "synthetic_invoice_illustrative_rows": by_invoice_rows,
        "synthetic_payment_unassigned_rows": by_payment_rows,
        "illustrative_cash_total": str(all_cash) if not reasons else None,
        "illustrative_tds_total": str(all_tds) if not reasons else None,
        "illustrative_credit_note_total": str(all_cn) if not reasons else None,
        "illustrative_gst_component_cash_total": str(by_method["GST_REVIEW"])
            if not reasons else None,
        "cash_plus_tds_plus_cn_conserved": not reasons,
        "no_actual_payment_or_duplicate_status_classified": True,
        "real_v218_financial_writer_amount_parity_verified": False,
        "real_53_column_report_financial_parity_verified": False,
        "synthetic_only": True,
        "original_source_workbooks_changed": False,
        "authoritative_oct27_master_private_data_imported": False,
        "full_master_v251_matrix_v239_certified": False,
        "financial_apply_locked": True,
        "real_bank_payments_allocated": 0,
        "real_financial_database_writes": 0,
        "financial_status": None,
        "production_release_authorized": False,
    }
