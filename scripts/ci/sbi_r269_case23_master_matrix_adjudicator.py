"""R26.9 Case 2.3 — connect Matrix v2.39 review proposals to Master v2.51.

This is a real-SCHEMA-CAPABLE, READ-ONLY, fail-closed financial REVIEW
integration using ONLY the already authorized pure modules:
 * R267 independent eligibility/rule candidate planner (Matrix role)
 * Case 2.2 one-fresh-workbook scoped core ledger (Master role)

CRITICAL: a Matrix proposal, a self-declared proof, a matching TDS rate,
an MXP reference or an amount resemblance is NOT an authorized payment.
This module never writes an OK or Duplicate Payment, never performs DB/Excel
writes, never uses historical allocations and never certifies v2.51/v2.39.

Priority (for review edge ORDER only, not paid status):
 EXACT_MXP > documented GST > partial > SBISA > documented cross-SOL
 > same-SOL discovery (NOT integrated) > DNM provisional (NOT reserved)
 > Global adjudication > waterfall LAST (NOT integrated).

If a competing bank row overcommits an invoice, the WHOLE competing invoice
group is held; bank-row order is NOT a financial eligibility decision.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date
from hashlib import sha256
import json
import re

from sbi_r267_readonly_real_candidate_engine import (
    InvoiceInput, BankInput, RelationshipProof, refs, plan_review_only,
    STAGE as MATRIX_STAGE,
)
from sbi_r269_core_cash_ledger_dry_run import GlobalAdjudicationBoundary, money
from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, ScopedMatrixProposal, fresh_workbook_digest,
    scoped_proposal_digest, run_independent_fresh_workbook,
)

STAGE = "R269_CASE23_MASTER_MATRIX_REVIEW_INTEGRATION_ONLY"
SHA = re.compile(r"[0-9a-f]{64}\Z")
PRIORITY = (
    "EXACT_MXP_REVIEW",
    "GST_COMPONENT_REVIEW",
    "PARTIAL_REVIEW",
    "SBISA_REVIEW",
    "CROSS_SOL_REVIEW",
    "SAME_SOL_REVIEW",
)
METHOD_RANK = {name: i for i,name in enumerate(PRIORITY)}
MATRIX_TO_MASTER = {
    "EXACT_MXP_TDS_REVIEW": "EXACT_MXP_REVIEW",
    "GST_LATER_DOCUMENTED_CANDIDATE": "GST_COMPONENT_REVIEW",
    "EXACT_MXP_PARTIAL_REVIEW": "PARTIAL_REVIEW",
}
HOLD_STAGES = (
    "DNM01_PROVISIONAL_NO_RESERVATION",
    "WATERFALL_FULL_LEDGER_QA_REQUIRED",
    "SAME_SOL_WITHOUT_EXACT_REF_FULL_COVERAGE_PENDING",
)


class MasterMatrixRefusal(ValueError):
    """Stable failure code; never put private customer data in exceptions."""


def _json_default(x):
    if isinstance(x,date):
        return x.isoformat()
    raise TypeError("UNSUPPORTED_EVIDENCE_TYPE")


def evidence_digest(invoices, payments, master_pairs, relationships=()):
    """Bind reviewed row-level source evidence, including method proofs.

    Not a substitute for checking original XLSX bytes, proving bank origin,
    verifying owner-authenticated documentation or source-master authority.
    """
    if (type(invoices) is not tuple or type(payments) is not tuple
        or type(master_pairs) is not tuple or type(relationships) is not tuple):
        raise MasterMatrixRefusal("IMMUTABLE_REVIEW_EVIDENCE_TUPLES_REQUIRED")
    for family, permitted in (
        (invoices,InvoiceInput),
        (payments,BankInput),
        (relationships,RelationshipProof),
    ):
        if any(type(item) is not permitted for item in family):
            raise MasterMatrixRefusal("INVALID_MATRIX_EVIDENCE_SCHEMA")
    if any(type(row) is not tuple or len(row)!=2
           or any(type(v) is not str for v in row) for row in master_pairs):
        raise MasterMatrixRefusal("MASTER_OFFICIAL_PAIR_SCHEMA_REQUIRED")
    data = {
        "invoice_evidence":[asdict(i) for i in invoices],
        "payment_evidence":[asdict(p) for p in payments],
        "master_identity_pairs":[list(pair) for pair in master_pairs],
        "relationship_evidence":[asdict(p) for p in relationships],
    }
    return sha256(json.dumps(
        data,sort_keys=True,ensure_ascii=True,separators=(",",":"),
        default=_json_default,
    ).encode("utf-8")).hexdigest()


def _same_original(a,b):
    return type(a) is type(b) and a==b


def _verify_same_upload_source(workbook, invoices, payments):
    """Refuse *any* mismatch between scoped core and Matrix source rows."""
    if type(workbook) is not FreshWorkbook:
        raise MasterMatrixRefusal("FRESH_SCOPED_WORKBOOK_REQUIRED")
    iv = {item.source_row:item for item in workbook.invoices}
    bank = {item.source_row:item for item in workbook.banks}
    if (len(iv)!=len(workbook.invoices) or len(bank)!=len(workbook.banks)):
        raise MasterMatrixRefusal("DUPLICATED_SOURCE_ROW_IN_WORKBOOK")
    if len(invoices)!=len(iv) or len(payments)!=len(bank):
        raise MasterMatrixRefusal("MASTER_MATRIX_SOURCE_POPULATION_MISMATCH")
    ids=set()
    for x in invoices:
        if type(x) is not InvoiceInput or x.source_row not in iv:
            raise MasterMatrixRefusal("MATRIX_INVOICE_ROW_NOT_IN_SCOPED_WORKBOOK")
        if x.source_row in ids:
            raise MasterMatrixRefusal("MATRIX_DUPLICATE_INVOICE_SOURCE_ROW")
        ids.add(x.source_row)
        c=iv[x.source_row]
        if (c.invoice_no!=x.invoice_no
                or money(c.gross)!=money(x.gross)
                or not _same_original(c.original_s,x.original_s)):
            raise MasterMatrixRefusal("INVOICE_ID_AMOUNT_OR_PROTECTION_MISMATCH")
    ids.clear()
    for x in payments:
        if type(x) is not BankInput or x.source_row not in bank:
            raise MasterMatrixRefusal("MATRIX_BANK_ROW_NOT_IN_SCOPED_WORKBOOK")
        if x.source_row in ids:
            raise MasterMatrixRefusal("MATRIX_DUPLICATE_PAYMENT_SOURCE_ROW")
        ids.add(x.source_row)
        c=bank[x.source_row]
        if (money(c.credit)!=money(x.credit)
                or not _same_original(c.original_k,x.original_k)):
            raise MasterMatrixRefusal("BANK_CREDIT_OR_PROTECTION_MISMATCH")
    return iv,bank


def _master_review_method(inv,bank,matrix_method):
    """Qualified review method, never signed allocation eligibility."""
    if matrix_method not in MATRIX_TO_MASTER:
        raise MasterMatrixRefusal("UNSUPPORTED_MATRIX_RESERVATION_METHOD")
    if bank.sol=="1" and inv.sol=="":
        if matrix_method!="EXACT_MXP_TDS_REVIEW":
            return None
        return "SBISA_REVIEW"
    if bank.sol!=inv.sol:
        if matrix_method!="EXACT_MXP_TDS_REVIEW":
            return None
        return "CROSS_SOL_REVIEW"
    return MATRIX_TO_MASTER[matrix_method]


def connect_master_matrix_review(
    workbook, invoices, payments, master_pairs, *,
    relationship_proofs=(),
    expected_workbook_digest,
    expected_matrix_evidence_digest,
    financial_apply="LOCKED",
):
    """Integrate candidate selection and atomic scoped Master CASH reservations.

    Exact-source verification, no history, no data writes. Any source binding,
    schema or method mismatch refuses the ENTIRE call. Financial ambiguity
    holds the affected invoice group (no arbitrary first-row settlement).
    """
    if financial_apply!="LOCKED":
        raise MasterMatrixRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    for d in (expected_workbook_digest,expected_matrix_evidence_digest):
        if type(d) is not str or not SHA.fullmatch(d):
            raise MasterMatrixRefusal("TWO_EXACT_SHA256_MANIFESTS_REQUIRED")
    if fresh_workbook_digest(workbook)!=expected_workbook_digest:
        raise MasterMatrixRefusal("SCOPED_WORKBOOK_DIGEST_MISMATCH")
    if (evidence_digest(invoices,payments,master_pairs,relationship_proofs)
            !=expected_matrix_evidence_digest):
        raise MasterMatrixRefusal("MATRIX_EVIDENCE_DIGEST_MISMATCH")
    scoped_iv,scoped_bank=_verify_same_upload_source(workbook,invoices,payments)
    master_ix={x.invoice_no:x for x in invoices}
    payment_ix={x.source_row:x for x in payments}
    if len(master_ix)!=len(invoices):
        # Duplicate invoice identities must not allow an arbitrary winner.
        raise MasterMatrixRefusal("DUPLICATE_MATRIX_INVOICE_IDENTITY")
    result=plan_review_only(
        list(invoices),list(payments),list(master_pairs),
        source_sha256=workbook.source_sha256,
        master_sha256=workbook.master_sha256,
        relationship_proofs=relationship_proofs,
        financial_apply="LOCKED",
    )
    if (result.get("stage")!=MATRIX_STAGE
            or result.get("financial_apply_locked") is not True
            or result.get("real_database_writes")!=0
            or result.get("complete_master_v251_matrix_v239_certified") is not False
            or result.get("all_real_bank_statuses")!="SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL"):
        raise MasterMatrixRefusal("UNAUTHORIZED_MATRIX_RELEASE_OR_SOURCE_CHANGE")
    if result["source_invoice_count"]!=len(invoices) or result["bank_row_count"]!=len(payments):
        raise MasterMatrixRefusal("MATRIX_CANDIDATE_POPULATION_MISMATCH")

    quarantined=defaultdict(set)
    for row,codes in result["invoice_quarantines"]:
        quarantined[row].update(codes)
    holds=defaultdict(set)
    for row,codes in result["bank_review_holds"]:
        holds[row].update(codes)

    # A first-row candidate does NOT win an invoice automatically if a later
    # competing bank row was rejected for invoice capacity. Move ALL its
    # competing edges to HOLD; future proof adjudication is a separate gate.
    contested=set()
    for row,codes in holds.items():
        if "INVOICE_CASH_CAPACITY_CONFLICT" in codes:
            bank=payment_ix[row]
            contested.update(r for r in refs(bank.description) if r in master_ix)
    held_edges=[]
    stage_edges=[]
    for source_row,invoice_no,credit,matrix_method,tds_rate in result["candidate_rows"]:
        if source_row not in scoped_bank or invoice_no not in master_ix:
            raise MasterMatrixRefusal("MATRIX_PROPOSAL_OUTSIDE_VERIFIED_SOURCE")
        if invoice_no in contested:
            holds[source_row].add("GLOBAL_INVOICE_COMPETING_CASH_HOLD")
            held_edges.append((source_row,invoice_no,"GLOBAL_INVOICE_COMPETING_CASH_HOLD"))
            continue
        inv=master_ix[invoice_no]
        bank=payment_ix[source_row]
        method=_master_review_method(inv,bank,matrix_method)
        if method is None:
            holds[source_row].add("COMPOUND_EXCEPTION_NEEDS_INDEPENDENT_PROOF")
            held_edges.append((source_row,invoice_no,
                               "COMPOUND_EXCEPTION_NEEDS_INDEPENDENT_PROOF"))
            continue
        # Extra guard against planner regression or forged candidate cash.
        if money(credit)!=money(scoped_bank[source_row].credit):
            raise MasterMatrixRefusal("MATRIX_CREDIT_DIFFERS_FROM_SOURCE")
        if source_row in holds:
            raise MasterMatrixRefusal("MATRIX_CANDIDATE_HAS_SIMULTANEOUS_HOLD")
        if inv.source_row in quarantined:
            raise MasterMatrixRefusal("MATRIX_CANDIDATE_REFERENCES_QUARANTINED_INVOICE")
        bank_key=scoped_bank[source_row].bank_key
        stage_edges.append((METHOD_RANK[method],source_row,bank_key,
                            invoice_no,credit,method,matrix_method,tds_rate))
    # Never permit R267 provisional DNM to reserve as a cash edge.
    provisional=[]
    for source_row,invoice_no,credit,method,tds_rate in result["candidate_rows"]:
        if method=="DNM01_PROVISIONAL_NO_RESERVATION":
            provisional.append((workbook.upload_id,source_row,invoice_no,
                                "DNM_REVIEW_ONLY_NEVER_RESERVE"))
        elif method not in MATRIX_TO_MASTER:
            raise MasterMatrixRefusal("UNSUPPORTED_MATRIX_MATCH_METHOD")

    seen=set()
    ordered=[]
    for _,row,bank_key,invoice_no,credit,method,matrix_method,rate in sorted(
            stage_edges,key=lambda x:(x[0],x[1],x[3])):
        key=(row,invoice_no)
        if key in seen:
            raise MasterMatrixRefusal("DUPLICATE_MATRIX_PROPOSAL_IDENTITY")
        seen.add(key)
        ordered.append(ScopedMatrixProposal(
            workbook.upload_id,bank_key,invoice_no,credit,method,
            f"REVIEW-ONLY-MATRIX-{row}-{invoice_no}-{method}",
        ))
    steps=tuple(ordered)+(GlobalAdjudicationBoundary(),)
    ledger=run_independent_fresh_workbook(
        workbook,steps,
        expected_workbook_digest=expected_workbook_digest,
        expected_scoped_plan_digest=scoped_proposal_digest(steps),
        previous_allocations=(),
        previous_payment_statuses=(),
        financial_apply="LOCKED",
    )
    # Verify the Matrix and workbook are still byte-equivalent to the
    # caller-provided immutable input manifest, after the pure calculation.
    if (fresh_workbook_digest(workbook)!=expected_workbook_digest
            or evidence_digest(invoices,payments,master_pairs,relationship_proofs)
                !=expected_matrix_evidence_digest):
        raise MasterMatrixRefusal("REVIEW_EVIDENCE_CHANGED_DURING_ADJUDICATION")
    if (ledger["financial_apply_locked"] is not True
            or ledger["real_database_writes"]!=0
            or ledger["financial_status"] is not None
            or ledger["complete_master_v251_matrix_v239_certified"] is not False):
        raise MasterMatrixRefusal("UNAUTHORIZED_MASTER_FINANCIAL_RELEASE")

    return {
        **ledger,
        "stage":STAGE,
        "matrix_source_stage":MATRIX_STAGE,
        "matrix_evidence_digest":expected_matrix_evidence_digest,
        "approved_review_priority":PRIORITY,
        "master_owns_only_scoped_cash_reservations":True,
        "matrix_only_proposes_no_approval":True,
        "review_edges_not_financial_allocations":tuple(
            (workbook.upload_id,row,invoice_no,method)
            for _,row,bank_key,invoice_no,credit,method,_,_ in sorted(
                stage_edges,key=lambda x:(x[0],x[1],x[3]))
        ),
        "global_competing_invoice_groups_held":tuple(sorted(contested)),
        "globally_held_review_edges":tuple(sorted(held_edges)),
        "unreserved_dnm_candidates":tuple(sorted(provisional)),
        "matrix_payment_holds":tuple(sorted(
            (workbook.upload_id,row,tuple(sorted(v)))
            for row,v in holds.items()
        )),
        "matrix_invoice_quarantines":tuple(sorted(
            (workbook.upload_id,row,tuple(sorted(v)))
            for row,v in quarantined.items()
        )),
        "same_sol_without_exact_ref_fully_integrated":False,
        "approved_waterfall_reservation_fully_integrated":False,
        "tns_tds_gst_credit_note_settlement_certified":False,
        "pending_methods":HOLD_STAGES,
        "real_bank_payments_reconciled":0,
        "final_payment_status":"NOT_ASSIGNED",
        "case23_full_method_coverage_certified":False,
        "full_v251_v239_certified":False,
        "financial_apply_locked":True,
        "real_database_writes":0,
        "production_release_authorized":False,
    }
