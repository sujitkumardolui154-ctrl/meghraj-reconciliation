"""R26.5 INDEPENDENT arithmetic witness for SYNTHETIC-only R26.4 review.

Not full executable v2.51, not signed independent real-bank QA, not a
financial writer or settlement. Recomputes arithmetic directly from SHA-pinned
SYN-* source/proposal/evidence fixtures, then checks a DIFFERENT R26.4 code path.
No Excel/cloud/database access; no actual bank source or selected master import;
no status setter and no financial Apply pathway.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import re

from sbi_r26_independent_financial_oracle import amount
from sbi_r262_rebuild_candidate_planner import fixture_digest
from sbi_r263_global_allocation_shadow import (
    GlobalGate, Proposal, proposal_digest,
)
from sbi_r264_financial_accounting_shadow import (
    account_synthetic_only, accounting_digest,
)

ZERO = Decimal("0.00")
STAGE = "R265_SYNTHETIC_INDEPENDENT_FINANCIAL_PARITY_ONLY"


class R265Refusal(ValueError):
    """Stable refusal code, no source-row data disclosed."""


def _money(v):
    return amount(v)


def independent_cash_tax_credit_reference(invoices, payments, steps,
                                          tds_evidence, credit_notes):
    """Independent equation; never calls R26.3/R26.4 balance helpers.

    This routine is an **arithmetic witness**, not a proof that proposed
    edges correspond to real bank receipts. All authenticity/eligibility checks
    are left to the R26.3/4 gate and a future full engine/independent QA.
    """
    pay_used = defaultdict(lambda: ZERO)
    inv_cash = defaultdict(lambda: ZERO)
    inv_tax = defaultdict(lambda: ZERO)
    inv_note = defaultdict(lambda: ZERO)
    gst_cash = ZERO
    for step in steps:
        if isinstance(step, GlobalGate):
            continue
        if not isinstance(step, Proposal):
            raise R265Refusal("ONLY_SYNTHETIC_PROPOSAL_STEPS")
        if step.kind == "DNM_REVIEW":
            # Provisional, never a reservation, even in synthetic QA.
            continue
        credit = _money(step.credit_portion)
        pay_used[step.payment_key] += credit
        inv_cash[step.invoice_key] += credit
        if step.kind == "GST_REVIEW":
            gst_cash += credit
    for evidence in tds_evidence:
        inv_tax[evidence.invoice_key] += _money(evidence.withholding)
    for note in credit_notes:
        inv_note[note.invoice_key] += _money(note.credit_gross)

    payment_rows = tuple((
        p.key, str(_money(p.credit)), str(pay_used[p.key]),
        str(_money(p.credit) - pay_used[p.key]),
    ) for p in sorted(payments, key=lambda x: x.key))
    invoice_rows = tuple((
        i.key, str(_money(i.outstanding)),
        str(inv_cash[i.key]), str(inv_tax[i.key]), str(inv_note[i.key]),
        str(_money(i.outstanding) - inv_cash[i.key] - inv_tax[i.key] - inv_note[i.key]),
    ) for i in sorted(invoices, key=lambda x: x.key))

    original_credit = sum((_money(p.credit) for p in payments), ZERO)
    assigned_credit = sum((pay_used[p.key] for p in payments), ZERO)
    credit_left = sum(
        (_money(p.credit) - pay_used[p.key] for p in payments), ZERO
    )
    gross_open = sum((_money(i.outstanding) for i in invoices), ZERO)
    cash = sum(inv_cash.values(), ZERO)
    withholding = sum(inv_tax.values(), ZERO)
    notes = sum(inv_note.values(), ZERO)
    illustrative_gap = sum(
        (_money(i.outstanding) - inv_cash[i.key] - inv_tax[i.key]
         - inv_note[i.key] for i in invoices), ZERO
    )
    return {
        "invoice_rows": invoice_rows,
        "payment_rows": payment_rows,
        "cash": str(cash),
        "tds": str(withholding),
        "credit_notes": str(notes),
        "gst_cash": str(gst_cash),
        "credit_conserved": original_credit == assigned_credit + credit_left,
        "invoice_equation_conserved":
            gross_open == cash + withholding + notes + illustrative_gap,
        "all_illustrative_balances_nonnegative":
            all(_money(row[-1]) >= ZERO for row in invoice_rows),
        "payment_cash_not_overdrawn":
            all(_money(row[-1]) >= ZERO for row in payment_rows),
    }


def release_gate_matrix():
    """Fail-closed regardless of caller-controlled evidence claims."""
    return {
        "stage": "R265_OWNER_RELEASE_EVIDENCE_REGISTER",
        "oct27_master_owner_selected_dev_reference": True,
        "oct27_master_row_exception_approval_complete": False,
        "excluded_149_rows_owner_review_complete": False,
        "complete_master_v251_matrix_v239_executable_certified": False,
        "real_bank_same_source_independent_parity_passed": False,
        "real_v218_writer_monetary_parity_passed": False,
        "real_53_column_report_amount_parity_passed": False,
        "real_staging_firebase_flask_authenticated": False,
        "real_aws_staging_postgres_backup_and_rollback": False,
        "finance_security_owner_signoff": False,
        "financial_apply_locked": True,
        "production_release_authorized": False,
    }


def verify_synthetic_parity(
    invoices, payments, master_rows, steps,
    proofs=(), tds_evidence=(), credit_notes=(), *,
    expected_fixture_sha256, expected_plan_sha256,
    expected_accounting_sha256, financial_apply="LOCKED",
):
    """Read-only arithmetic oracle over exactly hash-pinned synthetic fixtures.

    Only reference math and no-write flags are compared. It does NOT approve
    invoice eligibility or real TDS/credit note certificates. The R26.4 runner
    is separately executed; any mismatch FAILS CLOSED.
    """
    if financial_apply != "LOCKED":
        raise R265Refusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    for key in (expected_fixture_sha256, expected_plan_sha256,
                expected_accounting_sha256):
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise R265Refusal("THREE_EXPLICIT_SHA256_MANIFESTS_REQUIRED")
    # Verify independently before calling the candidate implementation.
    if fixture_digest(invoices, payments, master_rows) != expected_fixture_sha256:
        raise R265Refusal("INDEPENDENT_SOURCE_MASTER_MANIFEST_MISMATCH")
    if proposal_digest(steps, proofs) != expected_plan_sha256:
        raise R265Refusal("INDEPENDENT_PROPOSAL_MANIFEST_MISMATCH")
    if accounting_digest(tds_evidence, credit_notes) != expected_accounting_sha256:
        raise R265Refusal("INDEPENDENT_ACCOUNTING_MANIFEST_MISMATCH")

    candidate = account_synthetic_only(
        invoices, payments, master_rows, steps, proofs, tds_evidence,
        credit_notes, expected_fixture_sha256=expected_fixture_sha256,
        expected_plan_sha256=expected_plan_sha256,
        expected_accounting_sha256=expected_accounting_sha256,
        financial_apply="LOCKED",
    )
    # Never allow a test runner to override the production release lock.
    if (candidate.get("financial_apply_locked") is not True
            or candidate.get("real_bank_payments_allocated") != 0
            or candidate.get("real_financial_database_writes") != 0
            or candidate.get("financial_status") is not None
            or candidate.get("full_master_v251_matrix_v239_certified") is not False
            or candidate.get("real_v218_financial_writer_amount_parity_verified") is not False
            or candidate.get("real_53_column_report_financial_parity_verified") is not False
            or candidate.get("production_release_authorized") is not False):
        raise R265Refusal("UNAUTHORIZED_FINANCIAL_RELEASE_CLAIM")

    if not candidate.get("accounting_candidate_pass"):
        return {
            "stage": STAGE,
            "decision": "R264_BLOCKED_NO_FINANCIAL_PARITY_CLAIM",
            "r264_blockers": tuple(sorted(candidate["blocker_codes"])),
            "independent_arithmetic_pass": False,
            "candidate_amounts_released": False,
            "real_financial_rows_used": False,
            "financial_apply_locked": True,
            "full_v251_certified": False,
        }

    witness = independent_cash_tax_credit_reference(
        invoices, payments, steps, tds_evidence, credit_notes,
    )
    mismatches = set()
    if tuple(candidate["synthetic_invoice_illustrative_rows"]) != witness["invoice_rows"]:
        mismatches.add("INVOICE_BY_INVOICE_CASH_TDS_CREDIT_NOTE_PARITY")
    if tuple(candidate["synthetic_payment_unassigned_rows"]) != witness["payment_rows"]:
        mismatches.add("PAYMENT_BY_PAYMENT_BANK_CREDIT_PARITY")
    for field, target in (
        ("illustrative_cash_total", "cash"),
        ("illustrative_tds_total", "tds"),
        ("illustrative_credit_note_total", "credit_notes"),
        ("illustrative_gst_component_cash_total", "gst_cash"),
    ):
        if candidate.get(field) != witness[target]:
            mismatches.add("AGGREGATE_" + field.upper() + "_MISMATCH")
    for flag in ("credit_conserved", "invoice_equation_conserved",
                 "all_illustrative_balances_nonnegative",
                 "payment_cash_not_overdrawn"):
        if witness[flag] is not True:
            mismatches.add("REFERENCE_" + flag.upper() + "_FAILED")
    if (fixture_digest(invoices, payments, master_rows) != expected_fixture_sha256
            or proposal_digest(steps, proofs) != expected_plan_sha256
            or accounting_digest(tds_evidence, credit_notes) != expected_accounting_sha256):
        mismatches.add("SYNTHETIC_INPUT_CHANGED_DURING_QA")

    return {
        "stage": STAGE,
        "decision": ("PASS_SYNTHETIC_ARITHMETIC_ONLY" if not mismatches
                     else "FAIL_INDEPENDENT_ARITHMETIC_MISMATCH"),
        "mismatch_codes": tuple(sorted(mismatches)),
        "independent_arithmetic_pass": not mismatches,
        "number_of_synthetic_invoices": len(invoices),
        "number_of_synthetic_payments": len(payments),
        "real_financial_rows_used": False,
        "real_v218_writer_monetary_parity_verified": False,
        "finance_release_authorized": False,
        "financial_apply_locked": True,
        "full_v251_certified": False,
    }
