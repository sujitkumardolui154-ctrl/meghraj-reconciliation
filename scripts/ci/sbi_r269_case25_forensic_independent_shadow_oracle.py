"""R26.9 Case 2.5: independently recompute the scoped *shadow cash* ledger.

Separate from the Case 2.1/2.3 allocator; independently sums source money
and validates every proposed bank -> invoice edge, remaining source capacity,
protected rows, global totals, Case 2.4 review-only classifications, and a
per-payment deterministic forensic digest. No final settlement can result.

A SHA-256 receipt is an integrity fingerprint, NOT owner authorization or
an authenticated original XLSX/UTR, TDS, GST, credit note or Finance signature.
All evidence remains scoped to one fresh upload (owner Option B). Zero IO.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, ScopedMatrixProposal, fresh_workbook_digest,
    scoped_proposal_digest,
)
from sbi_r269_core_cash_ledger_dry_run import GlobalAdjudicationBoundary
from sbi_r269_case23_master_matrix_adjudicator import STAGE as CASE23_STAGE
from sbi_r269_case24_case23_review_handoff import STAGE as CASE24_STAGE

STAGE = "R269_CASE25_INDEPENDENT_SHADOW_CASH_FORENSICS_ONLY"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
SHA = re.compile(r"[0-9a-f]{64}\Z")
METHODS = frozenset({
    "EXACT_MXP_REVIEW", "GST_COMPONENT_REVIEW", "PARTIAL_REVIEW",
    "SBISA_REVIEW", "CROSS_SOL_REVIEW", "SAME_SOL_REVIEW",
})
SHADOW_STATUSES = frozenset({
    "OK_CANDIDATE", "SUSPENSE_CANDIDATE",
    "DUPLICATE_PAYMENT_CANDIDATE", "REVIEW_REQUIRED",
})


class ForensicRefusal(ValueError):
    """Refuse with a fixed code, never financial row text."""


def _require(condition, code):
    if not condition:
        raise ForensicRefusal(code)


def _money(value):
    _require(type(value) is str, "EXACT_SOURCE_MONEY_STRING_REQUIRED")
    try:
        val = Decimal(value.strip())
        valid = val.is_finite() and val == val.quantize(CENT) and val >= ZERO
    except (InvalidOperation, ValueError):
        valid = False
    _require(valid, "INVALID_SOURCE_OR_LEDGER_MONEY")
    return val.quantize(CENT)


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _digest(value):
    return sha256(json.dumps(
        value,sort_keys=True,ensure_ascii=True,
        separators=(",",":"),allow_nan=False,
    ).encode("utf-8")).hexdigest()


def independently_verify_shadow_forensics(
    workbook, case23, case24, *,
    expected_workbook_digest,
    expected_matrix_evidence_digest,
    financial_apply="LOCKED",
):
    """Pure separate arithmetic oracle; never a final payment status.

    Proofs are from the *unverified caller snapshot*. Every proposed edge is
    independently summed, checked against the source and rehashed, but no
    independently authenticated bank event or real Finance evidence is used.
    """
    _require(financial_apply == "LOCKED", "FINANCIAL_APPLY_LOCK_REQUIRED")
    _require(type(workbook) is FreshWorkbook, "FRESH_WORKBOOK_REQUIRED")
    _require(type(case23) is dict and type(case24) is dict,
             "INTEGRATED_CASE23_AND_CASE24_REQUIRED")
    _require(_sha(expected_workbook_digest) and _sha(expected_matrix_evidence_digest),
             "EXACT_EXPECTED_SOURCE_EVIDENCE_SHA_REQUIRED")
    _require(fresh_workbook_digest(workbook) == expected_workbook_digest,
             "ORIGINAL_SCOPED_SOURCE_DIGEST_MISMATCH")
    _require(
        case23.get("stage") == CASE23_STAGE
        and case23.get("workbook_digest") == expected_workbook_digest
        and case23.get("matrix_evidence_digest") == expected_matrix_evidence_digest
        and case23.get("source_sha256") == workbook.source_sha256
        and case23.get("master_sha256") == workbook.master_sha256
        and case23.get("upload_id") == workbook.upload_id
        and case23.get("upload_mode") == "INDEPENDENT_FRESH_WORKBOOK"
        and case23.get("bank_rows_in_this_upload") == len(workbook.banks)
        and case23.get("invoice_rows_in_this_upload") == len(workbook.invoices)
        and case23.get("financial_apply_locked") is True
        and case23.get("real_database_writes") == 0
        and case23.get("real_bank_payments_reconciled") == 0
        and case23.get("financial_status") is None
        and case23.get("final_payment_status") == "NOT_ASSIGNED"
        and case23.get("production_release_authorized") is False
        and case23.get("full_v251_v239_certified") is False
        and case23.get("previous_approved_allocations_imported") is False
        and case23.get("previous_payment_statuses_imported") is False,
        "UNVERIFIED_OR_RELEASED_CASE23_LEDGER",
    )
    _require(
        case24.get("stage") == CASE24_STAGE
        and case24.get("workbook_digest") == expected_workbook_digest
        and case24.get("upload_id") == workbook.upload_id
        and case24.get("financial_apply_locked") is True
        and case24.get("real_database_writes") == 0
        and case24.get("real_payment_allocations") == 0
        and case24.get("real_status_assignment") is False
        and case24.get("final_column_m_status") is None
        and case24.get("caller_evidence_not_independently_certified") is True
        and case24.get("production_release_authorized") is False
        and case24.get("full_v251_v239_certified") is False,
        "UNVERIFIED_OR_RELEASED_CASE24_STATUS",
    )
    invoices = {x.invoice_no:x for x in workbook.invoices}
    banks = {x.bank_key:x for x in workbook.banks}
    by_row = {x.source_row:x for x in workbook.banks}
    _require(len(invoices) == len(workbook.invoices)
             and len(banks) == len(workbook.banks)
             and len(by_row) == len(workbook.banks),
             "DUPLICATE_SOURCE_IDENTITY")
    _require(len({x.source_row for x in workbook.invoices}) == len(invoices),
             "DUPLICATE_INVOICE_SOURCE_ROW")
    for source in (*workbook.banks,*workbook.invoices):
        _require(source.upload_id == workbook.upload_id, "FOREIGN_SOURCE_UPLOAD")
    for bank in workbook.banks:
        _require(_money(bank.credit) > ZERO, "NONPOSITIVE_BANK_SOURCE_CREDIT")
    for inv in workbook.invoices:
        _require(_money(inv.gross) > ZERO, "NONPOSITIVE_INVOICE_SOURCE_GROSS")

    review = case23.get("review_edges_not_financial_allocations")
    cash = case23.get("scoped_shadow_edges")
    _require(type(review) is tuple and type(cash) is tuple
             and len(review) == len(cash),
             "MATRIX_VS_CASH_EDGE_POPULATION_MISMATCH")
    _require(len(cash) <= 100000, "FORENSIC_EDGE_SIZE_LIMIT")
    claimed_review = set()
    for edge in review:
        _require(type(edge) is tuple and len(edge) == 4
                 and edge[0] == workbook.upload_id and type(edge[1]) is int
                 and type(edge[2]) is str and type(edge[3]) is str
                 and edge[1] in by_row and edge[2] in invoices,
                 "MATRIX_REVIEW_EDGE_SOURCE_MISMATCH")
        _require(edge not in claimed_review, "DUPLICATE_MATRIX_REVIEW_EDGE")
        claimed_review.add(edge)

    bank_reserved = defaultdict(lambda: ZERO)
    invoice_reserved = defaultdict(lambda: ZERO)
    edge_lists = defaultdict(list)
    seen_pairs = set()
    source_steps = []
    for expected_index, edge in enumerate(cash, 1):
        _require(type(edge) is tuple and len(edge) == 7,
                 "INVALID_CORE_EDGE_SHAPE")
        upload, index, bank_key, invoice_no, portion, method, evidence_ref = edge
        _require(
            upload == workbook.upload_id and type(index) is int
            and index == expected_index
            and type(bank_key) is str and type(invoice_no) is str
            and bank_key in banks and invoice_no in invoices
            and type(method) is str and method in METHODS
            and type(evidence_ref) is str and evidence_ref.startswith("REVIEW-ONLY-MATRIX-"),
            "CORE_EDGE_IDENTITY_OR_METHOD_INVALID",
        )
        bank = banks[bank_key]
        inv = invoices[invoice_no]
        _require((upload,bank.source_row,invoice_no,method) in claimed_review,
                 "CORE_EDGE_NOT_IN_MATRIX_REVIEW")
        _require((bank_key,invoice_no) not in seen_pairs,
                 "DUPLICATED_BANK_INVOICE_RESERVATION")
        _require(not (bank.original_k is not None and str(bank.original_k).strip())
                 and not (inv.original_s is not None and str(inv.original_s).strip()),
                 "PROTECTED_ORIGINAL_SOURCE_RESERVATION")
        part = _money(portion)
        _require(part > ZERO, "ZERO_CASH_RESERVATION")
        seen_pairs.add((bank_key,invoice_no))
        bank_reserved[bank_key] += part
        invoice_reserved[invoice_no] += part
        _require(bank_reserved[bank_key] <= _money(bank.credit),
                 "INDEPENDENT_BANK_CAPACITY_OVERDRAW")
        _require(invoice_reserved[invoice_no] <= _money(inv.gross),
                 "INDEPENDENT_INVOICE_CAPACITY_OVERDRAW")
        source_steps.append(ScopedMatrixProposal(
            workbook.upload_id,bank_key,invoice_no,portion,method,evidence_ref))
        edge_lists[bank_key].append({
            "bank_source_row":bank.source_row,
            "invoice_no":invoice_no,
            "invoice_source_row":inv.source_row,
            "method":method,
            "cash_review_portion":str(part),
            "candidate_evidence_reference":evidence_ref,
            "forensic_edge_sha256":_digest({
                "upload":workbook.upload_id,
                "source":workbook.source_sha256,
                "master":workbook.master_sha256,
                "workbook_digest":expected_workbook_digest,
                "matrix_digest":expected_matrix_evidence_digest,
                "bank_key":bank_key,"bank_row":bank.source_row,
                "invoice":invoice_no,"invoice_row":inv.source_row,
                "cash":str(part),"method":method,"candidate_ref":evidence_ref,
            }),
            "documentary_authority":"NOT_EXTERNALLY_VERIFIED",
        })
    _require(len(seen_pairs) == len(claimed_review),
             "MATRIX_EDGE_NOT_IN_INDEPENDENT_CASH_LEDGER")
    source_steps.append(GlobalAdjudicationBoundary())
    _require(
        scoped_proposal_digest(tuple(source_steps)) == case23.get("scoped_matrix_plan_digest"),
        "SHADOW_PLAN_FINGERPRINT_MISMATCH",
    )
    blocked_rows = set()
    for tag in case23.get("matrix_payment_holds", ()):
        _require(type(tag) is tuple and len(tag) == 3
                 and tag[0] == workbook.upload_id
                 and type(tag[1]) is int and tag[1] in by_row,
                 "MALFORMED_OR_FOREIGN_PAYMENT_HOLD")
        blocked_rows.add(tag[1])
    for tag in case23.get("unreserved_dnm_candidates", ()):
        _require(type(tag) is tuple and len(tag) == 4
                 and tag[0] == workbook.upload_id
                 and type(tag[1]) is int and tag[1] in by_row,
                 "MALFORMED_OR_FOREIGN_PROVISIONAL_DNM")
        blocked_rows.add(tag[1])
    for tag in case23.get("globally_held_review_edges", ()):
        _require(type(tag) is tuple and len(tag) == 3
                 and type(tag[0]) is int and tag[0] in by_row,
                 "MALFORMED_GLOBAL_COMPETING_PAYMENT_HOLD")
        blocked_rows.add(tag[0])
    _require(all(bank_reserved[by_row[row].bank_key] == ZERO for row in blocked_rows),
             "HELD_PAYMENT_HAS_SHADOW_CASH")
    contested = case23.get("global_competing_invoice_groups_held")
    _require(type(contested) is tuple
             and all(type(x) is str and x in invoices for x in contested),
             "MALFORMED_COMPETING_INVOICE_SCOPE")
    _require(all(invoice_reserved[x] == ZERO for x in contested),
             "CONTESTED_INVOICE_HAS_RESERVED_CASH")
    quarantined = case23.get("matrix_invoice_quarantines", ())
    _require(type(quarantined) is tuple, "INVALID_INVOICE_QUARANTINE")
    invoice_rows = {inv.source_row:inv for inv in workbook.invoices}
    for q in quarantined:
        _require(type(q) is tuple and len(q) == 3
                 and q[0] == workbook.upload_id
                 and type(q[1]) is int and q[1] in invoice_rows,
                 "INVALID_INVOICE_QUARANTINE")
        _require(invoice_reserved[invoice_rows[q[1]].invoice_no] == ZERO,
                 "QUARANTINED_INVOICE_HAS_RESERVED_CASH")

    projected_banks = tuple((
        workbook.upload_id,x.bank_key,x.source_row,str(_money(x.credit)),
        str(bank_reserved[x.bank_key]),
        str(_money(x.credit)-bank_reserved[x.bank_key]),
    ) for x in sorted(workbook.banks,key=lambda x:x.source_row))
    projected_invoices = tuple((
        workbook.upload_id,x.invoice_no,x.source_row,str(_money(x.gross)),
        str(invoice_reserved[x.invoice_no]),
        str(_money(x.gross)-invoice_reserved[x.invoice_no]),
    ) for x in sorted(workbook.invoices,key=lambda x:x.source_row))
    _require(case23.get("scoped_shadow_bank_rows") == projected_banks,
             "INDEPENDENT_BANK_SOURCE_ROW_PARITY_FAILURE")
    _require(case23.get("scoped_shadow_invoice_cash_rows") == projected_invoices,
             "INDEPENDENT_INVOICE_SOURCE_ROW_PARITY_FAILURE")
    bank_total = sum((_money(x.credit) for x in workbook.banks), ZERO)
    invoice_total = sum((_money(x.gross) for x in workbook.invoices), ZERO)
    money_reserved = sum(bank_reserved.values(), ZERO)
    invoice_cash = sum(invoice_reserved.values(), ZERO)
    unreserved = bank_total - money_reserved
    gap = invoice_total - invoice_cash
    _require(money_reserved == invoice_cash
             and bank_total == unreserved + money_reserved
             and invoice_total == gap + invoice_cash,
             "INDEPENDENT_GLOBAL_SHADOW_CASH_CONSERVATION_FAILURE")
    _require(
        _money(case23.get("shadow_reserved_cash_total")) == money_reserved
        and _money(case23.get("shadow_unassigned_credit_total")) == unreserved
        and _money(case23.get("shadow_cash_coverage_gap_not_receivable")) == gap,
        "SHADOW_SUMMARY_DISAGREES_WITH_SOURCE",
    )

    status_rows = case24.get("records")
    _require(type(status_rows) is tuple and len(status_rows) == len(workbook.banks),
             "CASE24_PAYMENT_STATUS_POPULATION_MISMATCH")
    status_map = {}
    for x in status_rows:
        _require(
            type(x) is dict and x.get("upload_id") == workbook.upload_id
            and type(x.get("bank_source_row")) is int
            and x["bank_source_row"] in by_row
            and x.get("shadow_status") in SHADOW_STATUSES
            and x.get("final_column_m_status") is None
            and x.get("write_column_m") is False
            and x.get("financial_apply_locked") is True
            and x.get("real_database_writes") == 0,
            "UNAUTHORIZED_CASE24_BANK_STATUS_RESULT",
        )
        _require(x["bank_source_row"] not in status_map,
                 "DUPLICATE_CASE24_BANK_STATUS_ROW")
        status_map[x["bank_source_row"]] = x["shadow_status"]
    _require(
        case24.get("shadow_status_counts") == tuple(sorted(Counter(status_map.values()).items())),
        "CASE24_STATUS_COUNTER_MISMATCH",
    )
    forensic_rows = []
    for bank in sorted(workbook.banks,key=lambda x:x.source_row):
        available = _money(bank.credit) - bank_reserved[bank.bank_key]
        status = status_map[bank.source_row]
        _require(not (status == "OK_CANDIDATE"
                       and (bank_reserved[bank.bank_key] == ZERO
                            or bank.source_row in blocked_rows)),
                 "UNSUPPORTED_OK_CANDIDATE")
        _require(not (status in ("SUSPENSE_CANDIDATE","DUPLICATE_PAYMENT_CANDIDATE")
                       and bank_reserved[bank.bank_key] > ZERO),
                 "CONTRADICTORY_STATUS_AND_CASH_REVIEW")
        row = {
            "upload_id":workbook.upload_id,
            "bank_source_row":bank.source_row,
            "bank_key":bank.bank_key,
            "original_bank_credit":str(_money(bank.credit)),
            "candidate_cash_reserved":str(bank_reserved[bank.bank_key]),
            "unassigned_bank_credit":str(available),
            "case24_shadow_status":status,
            "case23_hold_applied":bank.source_row in blocked_rows,
            "edges":tuple(edge_lists[bank.bank_key]),
            "original_payment_A_to_L_edited":False,
            "final_payment_status_assigned":False,
            "independent_documentary_evidence_verified":False,
        }
        row["forensic_row_sha256"] = _digest({
            **{k:v for k,v in row.items() if k != "forensic_row_sha256"},
            "source_sha256":workbook.source_sha256,
            "master_sha256":workbook.master_sha256,
            "matrix_evidence_sha256":expected_matrix_evidence_digest,
        })
        forensic_rows.append(row)
    _require(fresh_workbook_digest(workbook) == expected_workbook_digest,
             "WORKBOOK_MUTATED_DURING_FORENSICS")
    manifest = _digest({
        "source":workbook.source_sha256,"master":workbook.master_sha256,
        "workbook":expected_workbook_digest,
        "matrix":expected_matrix_evidence_digest,
        "bank_row_receipts":[r["forensic_row_sha256"] for r in forensic_rows],
        "reserved":str(money_reserved),"unused":str(unreserved),
        "invoice_cash_coverage_gap":str(gap),
    })
    return {
        "stage":STAGE,"upload_id":workbook.upload_id,
        "source_sha256":workbook.source_sha256,
        "master_sha256":workbook.master_sha256,
        "scoped_workbook_digest":expected_workbook_digest,
        "matrix_evidence_digest":expected_matrix_evidence_digest,
        "forensic_manifest_sha256":manifest,
        "payment_forensics":tuple(forensic_rows),
        "payment_rows_recomputed":len(workbook.banks),
        "review_edges_recomputed":len(cash),
        "independent_cash_arithmetic_verified":True,
        "shadow_cash_reserved":str(money_reserved),
        "shadow_bank_unassigned":str(unreserved),
        "shadow_invoice_cash_gap_not_receivable":str(gap),
        "bank_and_invoice_cash_conservation":True,
        "original_source_xlsx_bytes_independently_verified":False,
        "verified_bank_utr_or_statement_event":False,
        "verified_external_tds_gst_credit_note_ledger":False,
        "cross_upload_duplicate_reconciliation_certified":False,
        "case24_status_claim_independently_certified":False,
        "real_financial_allocations":0,
        "final_paymnent_column_m_written":False,
        "real_database_writes":0,
        "financial_apply_locked":True,
        "full_master_v251_matrix_v239_certified":False,
        "production_release_authorized":False,
    }
