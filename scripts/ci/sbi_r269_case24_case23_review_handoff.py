"""Case 2.4 -> Case 2.3 integrated review handoff, strictly non-settlement.

Handoff binds each bank payment row to its immutable single-upload scope,
verified normalized credit, and Case 2.3 review-only manifest. The status
engine may return only hypothetical candidates, never real PAYMNENT Column M.
No historical ledger, IO, database, report or spreadsheet writer is imported.
Caller evidence flags do not constitute external financial certification.
"""
from __future__ import annotations
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from collections import Counter

from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, fresh_workbook_digest,
)
from sbi_r269_case23_master_matrix_adjudicator import STAGE as CASE23_STAGE
from sbi_r269_case24_financial_status_shadow import (
    StatusEvidence, ReviewStatus, classify_shadow,
)

STAGE = "R269_CASE24_SCOPED_FINANCIAL_STATUS_REVIEW_ONLY"


class StatusIntegrationRefusal(ValueError):
    """Fixed codes only; never print bank customer data."""


def _money(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise StatusIntegrationRefusal("SOURCE_BANK_AMOUNT_INVALID")
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise StatusIntegrationRefusal("SOURCE_BANK_AMOUNT_INVALID")
    return amount


def classify_case23_shadow(workbook, case23, *, evidence=(),
                           expected_workbook_digest, financial_apply="LOCKED"):
    """Return one review-only status per bank row, with source-bound holds.

    A supplied true flag is not proof of independent bank/Finance approval.
    Such candidates remain non-committable until separate real-evidence QA.
    """
    if financial_apply != "LOCKED":
        raise StatusIntegrationRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if type(workbook) is not FreshWorkbook or type(case23) is not dict:
        raise StatusIntegrationRefusal("SCOPED_MASTER_AND_MATRIX_REQUIRED")
    if (fresh_workbook_digest(workbook) != expected_workbook_digest
            or case23.get("workbook_digest") != expected_workbook_digest):
        raise StatusIntegrationRefusal("SOURCE_SCOPE_DIGEST_MISMATCH")
    safe = (
        case23.get("stage") == CASE23_STAGE
        and case23.get("upload_id") == workbook.upload_id
        and case23.get("upload_mode") == "INDEPENDENT_FRESH_WORKBOOK"
        and case23.get("financial_apply_locked") is True
        and case23.get("real_database_writes") == 0
        and case23.get("real_bank_payments_reconciled") == 0
        and case23.get("final_payment_status") == "NOT_ASSIGNED"
        and case23.get("financial_status") is None
        and case23.get("production_release_authorized") is False
        and case23.get("full_v251_v239_certified") is False
        and case23.get("matrix_only_proposes_no_approval") is True
        and case23.get("master_owns_only_scoped_cash_reservations") is True
        and case23.get("previous_approved_allocations_imported") is False
        and case23.get("previous_payment_statuses_imported") is False
        and case23.get("bank_rows_in_this_upload") == len(workbook.banks)
        and case23.get("invoice_rows_in_this_upload") == len(workbook.invoices)
    )
    if not safe:
        raise StatusIntegrationRefusal("CASE23_UNCERTIFIED_OR_CHANGED_CONTRACT")
    if type(evidence) is not tuple or any(type(e) is not StatusEvidence for e in evidence):
        raise StatusIntegrationRefusal("IMMUTABLE_STATUS_EVIDENCE_REQUIRED")
    banks = {bank.source_row:bank for bank in workbook.banks}
    if len(banks) != len(workbook.banks) or len(evidence) > len(banks):
        raise StatusIntegrationRefusal("DUPLICATED_BANK_SOURCE_ROW")
    provided = {}
    for ev in evidence:
        if ev.upload_id != workbook.upload_id or ev.bank_source_row not in banks:
            raise StatusIntegrationRefusal("CROSS_UPLOAD_OR_UNKNOWN_BANK_STATUS_EVIDENCE")
        if ev.bank_source_row in provided:
            raise StatusIntegrationRefusal("DUPLICATE_STATUS_EVIDENCE_FOR_ROW")
        if _money(ev.original_credit) != _money(banks[ev.bank_source_row].credit):
            raise StatusIntegrationRefusal("STATUS_CREDIT_NOT_SOURCE_BOUND")
        provided[ev.bank_source_row] = ev
    row_holds = set()
    for item in case23.get("matrix_payment_holds", ()):
        if type(item) not in (tuple,list) or len(item) != 3 or item[0] != workbook.upload_id:
            raise StatusIntegrationRefusal("CROSS_UPLOAD_MATRIX_HOLD")
        row_holds.add(item[1])
    for item in case23.get("unreserved_dnm_candidates", ()):
        if type(item) not in (tuple,list) or len(item) != 4 or item[0] != workbook.upload_id:
            raise StatusIntegrationRefusal("CROSS_UPLOAD_DNM_PROPOSAL")
        row_holds.add(item[1])
    for item in case23.get("globally_held_review_edges", ()):
        if type(item) not in (tuple,list) or len(item) != 3:
            raise StatusIntegrationRefusal("MALFORMED_COMPETING_INVOICE_HOLD")
        row_holds.add(item[0])
    edges = case23.get("review_edges_not_financial_allocations")
    if type(edges) not in (tuple,list):
        raise StatusIntegrationRefusal("MISSING_REVIEW_EDGE_CONTRACT")
    contested = set(case23.get("global_competing_invoice_groups_held", ()))
    edge_rows = set()
    for e in edges:
        if type(e) not in (tuple,list) or len(e) != 4 or e[0] != workbook.upload_id:
            raise StatusIntegrationRefusal("CROSS_UPLOAD_MATRIX_EDGE")
        if e[1] not in banks:
            raise StatusIntegrationRefusal("UNRECOGNIZED_MATRIX_BANK_ROW")
        edge_rows.add(e[1])
        if e[2] in contested:
            row_holds.add(e[1])
    if any(row not in banks for row in row_holds):
        raise StatusIntegrationRefusal("UNKNOWN_HELD_BANK_ROW")
    output = []
    for bank in sorted(workbook.banks, key=lambda b:b.source_row):
        ev = provided.get(bank.source_row) or StatusEvidence(
            workbook.upload_id, bank.source_row, bank.credit)
        # Bank's original K must never be overwritten by a fresh review.
        protected = bank.original_k is not None and str(bank.original_k).strip() != ""
        bad_allocation_proof = ev.allocation_finalized and bank.source_row not in edge_rows
        contradictory_unmatched = ev.certified_no_match and bank.source_row in edge_rows
        contradictory_duplicate = ev.independently_proven_duplicate and bank.source_row in edge_rows
        blocked = (bank.source_row in row_holds or protected or bad_allocation_proof
                   or contradictory_unmatched or contradictory_duplicate)
        ev = replace(ev,
            protected_prior_status=ev.protected_prior_status or protected,
            competing_invoice_or_bank_hold=ev.competing_invoice_or_bank_hold or blocked)
        record = classify_shadow(ev, financial_apply="LOCKED")
        if record["final_column_m_status"] is not None or record["write_column_m"]:
            raise StatusIntegrationRefusal("UNAUTHORIZED_COLUMN_M_CHANGE")
        output.append(record)
    if fresh_workbook_digest(workbook) != expected_workbook_digest:
        raise StatusIntegrationRefusal("WORKBOOK_CHANGED_DURING_REVIEW")
    return {
        "stage":STAGE, "upload_id":workbook.upload_id,
        "workbook_digest":expected_workbook_digest,
        "records":tuple(output),
        "shadow_status_counts":tuple(sorted(Counter(
            item["shadow_status"] for item in output).items())),
        "case23_only_cash_review":True,
        "caller_evidence_not_independently_certified":True,
        "real_status_assignment":False,
        "final_column_m_status":None,
        "real_payment_allocations":0,
        "financial_apply_locked":True,
        "real_database_writes":0,
        "production_release_authorized":False,
        "full_v251_v239_certified":False,
    }
