"""Case 2.4: shadow status classification, not a financial writer.

Master v2.51/Matrix v2.39 are not certified. This module accepts separately
verified evidence and returns a recommendation only; it cannot modify Column M.
Never infer paid status from a Matrix candidate or cash-capacity dry run.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

class ReviewStatus(str, Enum):
    OK_CANDIDATE = "OK_CANDIDATE"
    SUSPENSE_CANDIDATE = "SUSPENSE_CANDIDATE"
    DUPLICATE_CANDIDATE = "DUPLICATE_PAYMENT_CANDIDATE"
    HOLD = "REVIEW_REQUIRED"

@dataclass(frozen=True)
class StatusEvidence:
    upload_id: str
    bank_source_row: int
    original_credit: str
    source_verified: bool = False
    unique_bank_event_verified: bool = False
    independently_proven_duplicate: bool = False
    duplicate_reference_verified: bool = False
    allocation_finalized: bool = False
    independent_allocation_oracle_passed: bool = False
    invoice_and_sol_verified: bool = False
    service_period_verified: bool = False
    tds_gst_credit_note_verified: bool = False
    fully_accounted_credit: bool = False
    competing_invoice_or_bank_hold: bool = False
    protected_prior_status: bool = False
    unresolved_exception: bool = False
    certified_no_match: bool = False

def classify_shadow(evidence: StatusEvidence, *, financial_apply: str = "LOCKED") -> dict:
    if financial_apply != "LOCKED":
        raise ValueError("FINANCIAL_APPLY_MUST_REMAIN_LOCKED")
    if type(evidence) is not StatusEvidence:
        raise TypeError("STATUS_EVIDENCE_REQUIRED")
    if not evidence.upload_id or type(evidence.bank_source_row) is not int or evidence.bank_source_row < 2:
        raise ValueError("INVALID_SCOPED_BANK_IDENTITY")
    if any(type(getattr(evidence, field)) is not bool for field in (
        "source_verified", "unique_bank_event_verified", "independently_proven_duplicate",
        "duplicate_reference_verified", "allocation_finalized",
        "independent_allocation_oracle_passed", "invoice_and_sol_verified",
        "service_period_verified", "tds_gst_credit_note_verified",
        "fully_accounted_credit", "competing_invoice_or_bank_hold",
        "protected_prior_status", "unresolved_exception", "certified_no_match")):
        raise ValueError("INVALID_BOOLEAN_EVIDENCE")
    try:
        credit = Decimal(evidence.original_credit)
    except (InvalidOperation, TypeError, ValueError):
        credit = None
    valid_credit = (credit is not None and credit.is_finite() and credit > 0
                    and credit == credit.quantize(Decimal("0.01")))
    status, reason = ReviewStatus.HOLD, "INSUFFICIENT_OR_CONFLICTING_EVIDENCE"
    if not valid_credit or not evidence.source_verified:
        reason = "INVALID_OR_UNVERIFIED_BANK_SOURCE"
    elif evidence.protected_prior_status or evidence.competing_invoice_or_bank_hold or evidence.unresolved_exception:
        reason = "PROTECTED_OR_CONTESTED_RECORD"
    elif evidence.independently_proven_duplicate:
        if evidence.duplicate_reference_verified and not evidence.allocation_finalized:
            status, reason = ReviewStatus.DUPLICATE_CANDIDATE, "INDEPENDENT_DUPLICATE_PROOF"
        else:
            reason = "CONTRADICTORY_DUPLICATE_PROOF"
    elif evidence.duplicate_reference_verified:
        reason = "DUPLICATE_EVIDENCE_INCONSISTENT"
    elif all((
        evidence.unique_bank_event_verified, evidence.allocation_finalized,
        evidence.independent_allocation_oracle_passed, evidence.invoice_and_sol_verified,
        evidence.service_period_verified, evidence.tds_gst_credit_note_verified,
        evidence.fully_accounted_credit,
    )):
        status, reason = ReviewStatus.OK_CANDIDATE, "ALL_INDEPENDENT_SETTLEMENT_GATES"
    elif evidence.certified_no_match and not evidence.allocation_finalized and evidence.unique_bank_event_verified:
        status, reason = ReviewStatus.SUSPENSE_CANDIDATE, "VERIFIED_NO_MATCH"
    return {
        "upload_id": evidence.upload_id,
        "bank_source_row": evidence.bank_source_row,
        "shadow_status": status.value,
        "reason_code": reason,
        "write_column_m": False,
        "final_column_m_status": None,
        "review_only": True,
        "full_v251_v239_certified": False,
        "financial_apply_locked": True,
        "real_database_writes": 0,
    }
