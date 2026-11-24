"""R26.3 GLOBAL LEDGER / FULL-PARTIAL / WATERFALL shadow: SYNTHETIC ONLY.

NO Excel reader; NO external/production database, filesystem, API or credentials.
Every invoice/payment must carry a SYN-* ID and come from a small caller-pinned
synthetic fixture. "Proof" tokens are fictitious QA markers, NEVER real approvals.
This module builds a candidate *in-memory simulation* and cannot produce an OK
or Duplicate Payment status, a production ledger entry or financial Apply.

Not certified Master v2.51 / Matrix v2.39. Not a substitute for full real-data
independent financial parity, approved cross-SOL/SBISA/GST/partial evidence,
real v2.18 writer, user/Finance signoff or staging rollback.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
import json
import re

from sbi_r26_independent_financial_oracle import (
    R26Refusal, _synthetic_invoice, _synthetic_payment, amount,
    money_hypotheses,
)
from sbi_r262_rebuild_candidate_planner import _check_inputs, norm, blank

STAGE = "R263_SYNTHETIC_GLOBAL_LEDGER_WATERFALL_ONLY"
PROPOSAL_KINDS = frozenset((
    "STANDARD", "PARTIAL_REVIEW", "GST_REVIEW", "SBISA_REVIEW",
    "CROSS_SOL_REVIEW", "WATERFALL", "DNM_REVIEW",
))
PROOF_KINDS = frozenset(("PARTIAL", "GST", "SBISA", "CROSS_SOL", "WATERFALL"))
PROOF_ID = re.compile(r"SYN-PROOF-[0-9]{3,6}\Z")
GATE_ID = re.compile(r"SYN-GATE-[0-9]{3,6}\Z")
MAX_ROWS = 100
ZERO = Decimal("0.00")


class R263Refusal(ValueError):
    """Strict synthetic schema/manifest refusal (constant reason code)."""


@dataclass(frozen=True)
class SyntheticProof:
    key: str
    kind: str
    payment_key: str
    invoice_key: str
    # Fixed sentinel is informational only, never an owner authorization.
    authority: str = "SYNTHETIC_QA_ONLY"


@dataclass(frozen=True)
class Proposal:
    payment_key: str
    invoice_key: str
    credit_portion: str
    kind: str = "STANDARD"
    proof_key: str = ""


@dataclass(frozen=True)
class GlobalGate:
    key: str = "SYN-GATE-001"


def proposal_digest(steps, proofs):
    """Explicit manifest of the exact candidate graph, separate from fixture SHA."""
    payload = {
        "steps": [asdict(x) for x in steps],
        "kinds": [type(x).__name__ for x in steps],
        "proofs": [asdict(x) for x in sorted(proofs, key=lambda p: p.key)],
    }
    return sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def _strict_proof_catalog(proofs, payments, invoices):
    if type(proofs) not in (list, tuple) or len(proofs) > MAX_ROWS:
        raise R263Refusal("SYNTHETIC_PROOF_LIST_REQUIRED")
    out = {}
    for proof in proofs:
        if (not isinstance(proof, SyntheticProof)
                or not PROOF_ID.fullmatch(proof.key)
                or proof.kind not in PROOF_KINDS
                or proof.authority != "SYNTHETIC_QA_ONLY"):
            raise R263Refusal("REAL_OR_UNSUPPORTED_PROOF_REFUSED")
        if proof.key in out:
            raise R263Refusal("DUPLICATE_SYNTHETIC_PROOF_ID")
        if proof.payment_key not in payments or proof.invoice_key not in invoices:
            raise R263Refusal("UNLINKED_SYNTHETIC_PROOF")
        out[proof.key] = proof
    return out


def _proof(proposal, catalog, wanted):
    if not proposal.proof_key:
        return False
    item = catalog.get(proposal.proof_key)
    return bool(
        item is not None and item.kind == wanted
        and item.payment_key == proposal.payment_key
        and item.invoice_key == proposal.invoice_key
    )


def _pair_hold(pay, inv, master, *, kind, proof_catalog, proposal):
    """Returns *first* conservative reason; no bank matching or state mutation."""
    credit = amount(pay.credit)
    portion = amount(proposal.credit_portion)
    if credit <= ZERO or portion <= ZERO:
        return "NONPOSITIVE_CREDIT_OR_PORTION"
    if not blank(pay.original_k) or not blank(inv.source_s_marker):
        return "ORIGINAL_K_OR_S_PROTECTED"
    if pay.bank_date < inv.issue_date:
        return "BANK_DATE_BEFORE_INVOICE"
    if not inv.service_periods or not set(inv.service_periods).issubset(pay.service_periods):
        return "SERVICE_PERIOD_NOT_FULLY_VERIFIED"
    if len(pay.mxp_refs) > 1:
        return "MULTIPLE_MXP_REFERENCES"
    if pay.mxp_refs and pay.mxp_refs != (inv.key,):
        return "CONTRADICTORY_MXP_REFERENCE"
    if kind == "DNM_REVIEW":
        return "DNM_PROVISIONAL_NO_SHADOW_RESERVATION"
    # A string identity is *never* normalized by adding or stripping zeros.
    pay_verified = (pay.sol, norm(pay.client)) in master
    inv_verified = (inv.sol, norm(inv.client)) in master
    if kind == "SBISA_REVIEW":
        if (pay.sol != "1" or inv.sol or not pay_verified
                or norm(pay.client) != norm(inv.client)
                or not _proof(proposal, proof_catalog, "SBISA")):
            return "SBISA_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED"
    elif kind == "CROSS_SOL_REVIEW":
        if (not pay.sol or not inv.sol or pay.sol == inv.sol
                or not pay_verified or not inv_verified
                or not _proof(proposal, proof_catalog, "CROSS_SOL")):
            return "CROSS_SOL_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED"
    else:
        if pay.sol != inv.sol or not pay.sol or not pay_verified or not inv_verified:
            return "SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED"
        if norm(pay.client) != norm(inv.client):
            return "CLIENT_NAME_CONFLICT"
    if pay.gst_narration and kind != "GST_REVIEW":
        return "GST_NARRATION_MUST_BE_SEPARATELY_ADJUDICATED"
    if kind == "GST_REVIEW":
        if (not pay.gst_narration
                or not _proof(proposal, proof_catalog, "GST")):
            return "GST_COMPONENT_DOCUMENTARY_PROOF_REQUIRED"
        if portion > amount(inv.cgst) + amount(inv.sgst):
            return "GST_PORTION_EXCEEDS_INVOICE_GST"
    elif kind == "PARTIAL_REVIEW":
        if not _proof(proposal, proof_catalog, "PARTIAL"):
            return "PARTIAL_RECEIPT_DOCUMENTARY_PROOF_REQUIRED"
        if not pay.mxp_refs:
            return "PARTIAL_EXACT_REFERENCE_REQUIRED"
    elif kind == "WATERFALL":
        if pay.mxp_refs or not _proof(proposal, proof_catalog, "WATERFALL"):
            return "WATERFALL_REFERENCE_OR_APPROVAL_MISSING"
    elif kind == "STANDARD":
        if pay.mxp_refs != (inv.key,):
            return "STANDARD_EXACT_REFERENCE_REQUIRED"
        # TDS amounts are invoice-level; partials need separately reviewed proof.
        if len(money_hypotheses(pay, inv)) != 1:
            return "EXACT_TDS_HYPOTHESIS_NOT_UNIQUE"
        if portion != credit:
            return "STANDARD_EDGE_MUST_COVER_EXACT_CREDIT"
    return ""


def shadow_adjudicate(
    invoices, payments, master_rows, steps, proofs=(),
    *, expected_fixture_sha256, expected_plan_sha256,
    financial_apply="LOCKED",
):
    """All-or-nothing candidate ledger simulation; no durable reservations.

    A GlobalGate separates prior evidence candidates from waterfall-only
    candidates. Any invalid/overallocated input *atomically rejects* all
    shadow edges. DNM suggestions are never reserved, even in synthetic QA.
    This is not a financial settlement algorithm or authorization.
    """
    if financial_apply != "LOCKED":
        raise R263Refusal("FINANCIAL_APPLY_CANNOT_BE_UNLOCKED")
    verified_master = _check_inputs(
        invoices, payments, master_rows, expected_fixture_sha256,
    )
    if type(steps) not in (list, tuple) or len(steps) > MAX_ROWS:
        raise R263Refusal("SYNTHETIC_PLAN_STEPS_REQUIRED")
    if not isinstance(expected_plan_sha256, str) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_plan_sha256
    ):
        raise R263Refusal("EXPLICIT_PLAN_SHA256_REQUIRED")
    by_pay = {x.key: x for x in payments}
    by_inv = {x.key: x for x in invoices}
    proof_catalog = _strict_proof_catalog(proofs, by_pay, by_inv)
    # Validate *all* step types before digest: malformed payloads are refused.
    for step in steps:
        if isinstance(step, GlobalGate):
            if not GATE_ID.fullmatch(step.key):
                raise R263Refusal("INVALID_SYNTHETIC_GLOBAL_GATE")
        elif isinstance(step, Proposal):
            if step.kind not in PROPOSAL_KINDS:
                raise R263Refusal("UNKNOWN_SIMULATED_METHOD")
            if not isinstance(step.proof_key, str):
                raise R263Refusal("INVALID_PROOF_KEY")
            if step.payment_key not in by_pay or step.invoice_key not in by_inv:
                raise R263Refusal("UNKNOWN_SYNTHETIC_SOURCE_REFERENCE")
            amount(step.credit_portion)
        else:
            raise R263Refusal("INVALID_PLAN_STEP_TYPE")
    if proposal_digest(steps, proofs) != expected_plan_sha256:
        raise R263Refusal("PLAN_SHA256_MISMATCH")
    blockers = set()
    if any(n > 1 for n in Counter(x.key for x in invoices).values()):
        blockers.add("DUPLICATE_SOURCE_INVOICE")
    if any(n > 1 for n in Counter(x.key for x in payments).values()):
        blockers.add("DUPLICATE_SOURCE_PAYMENT")
    pre_gate = True
    gate_seen = False
    gate_count = 0
    candidate_edges = []
    dnm_held = 0
    seen_pairs = set()
    for step in steps:
        if isinstance(step, GlobalGate):
            gate_count += 1
            gate_seen = True
            pre_gate = False
            if gate_count > 1:
                blockers.add("GLOBAL_GATE_REPEATED")
            continue
        if step.kind == "WATERFALL":
            if pre_gate:
                blockers.add("WATERFALL_BEFORE_GLOBAL_GATE")
        elif not pre_gate:
            blockers.add("EARLIER_MATCHING_AFTER_GLOBAL_GATE")
        pay, inv = by_pay[step.payment_key], by_inv[step.invoice_key]
        pair = (step.payment_key, step.invoice_key)
        if pair in seen_pairs:
            blockers.add("REPEATED_PAYMENT_INVOICE_EDGE")
        seen_pairs.add(pair)
        reason = _pair_hold(
            pay, inv, verified_master, kind=step.kind,
            proof_catalog=proof_catalog, proposal=step,
        )
        if reason:
            if step.kind == "DNM_REVIEW" and reason == "DNM_PROVISIONAL_NO_SHADOW_RESERVATION":
                dnm_held += 1
            else:
                blockers.add(reason)
            continue
        candidate_edges.append(step)
    if not gate_seen:
        blockers.add("GLOBAL_GATE_MISSING")
    by_payment_amount = defaultdict(lambda: ZERO)
    by_invoice_amount = defaultdict(lambda: ZERO)
    for edge in candidate_edges:
        money = amount(edge.credit_portion)
        by_payment_amount[edge.payment_key] += money
        by_invoice_amount[edge.invoice_key] += money
    for key, value in by_payment_amount.items():
        if value > amount(by_pay[key].credit):
            blockers.add("SHADOW_PAYMENT_CREDIT_OVERALLOCATED")
    for key, value in by_invoice_amount.items():
        if value > amount(by_inv[key].outstanding):
            blockers.add("SHADOW_INVOICE_OUTSTANDING_OVERALLOCATED")
    if blockers:
        # Atomic ALL-OR-NONE: no half-approved entries escape a conflict.
        candidate_edges = []
        by_payment_amount.clear()
        by_invoice_amount.clear()
    remaining_pay = tuple(
        (p.key, str(amount(p.credit) - by_payment_amount[p.key]))
        for p in sorted(payments, key=lambda x: x.key)
    ) if not blockers else ()
    remaining_inv = tuple(
        (i.key, str(amount(i.outstanding) - by_invoice_amount[i.key]))
        for i in sorted(invoices, key=lambda x: x.key)
    ) if not blockers else ()
    return {
        "stage": STAGE,
        "synthetic_only": True,
        "fixture_sha256": expected_fixture_sha256,
        "plan_sha256": expected_plan_sha256,
        "atomic_shadow_review_pass": not blockers,
        "blocker_codes": tuple(sorted(blockers)),
        "shadow_candidate_edges": tuple(
            (e.payment_key, e.invoice_key, str(amount(e.credit_portion)), e.kind)
            for e in candidate_edges
        ),
        "shadow_credit_balance": remaining_pay,
        "shadow_invoice_cash_coverage_gap": remaining_inv,
        "tds_withheld_not_recognized_as_cash_or_invoice_settlement": True,
        "dnm_provisional_edges_held": dnm_held,
        "global_gate_checked": gate_count == 1,
        "original_source_records_changed": False,
        "full_partial_simulation_only": True,
        "sbisa_cross_sol_gst_proofs_are_fictitious": True,
        "authoritative_oct27_master_data_loaded": False,
        "complete_master_v251_matrix_v239_certified": False,
        "real_bank_payments_allocated": 0,
        "real_invoice_status_updates": 0,
        "real_database_writes": 0,
        "financial_status": None,
        "financial_apply_locked": True,
        "production_release_authorized": False,
    }
