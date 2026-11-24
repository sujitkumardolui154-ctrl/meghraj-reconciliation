"""Case 2.6: SAME-UPLOAD, SYNTHETIC-ONLY method-coverage rehearsal.

Never a production v2.51/v2.39 settlement runner. Tests the main *method
contracts* against separate source-schema financial details and a pure Case 2.2
cash ledger, re-checking arithmetic independently. All method proof IDs are
synthetic fixtures, not verified bank events or approved settlement authority.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from hashlib import sha256
import json
import re

from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, ScopedMatrixProposal, fresh_workbook_digest,
    scoped_proposal_digest, run_independent_fresh_workbook,
)
from sbi_r269_core_cash_ledger_dry_run import GlobalAdjudicationBoundary

STAGE = "R269_CASE26_SYNTHETIC_METHOD_REHEARSAL_NOT_SETTLEMENT"
CENT=Decimal("0.01")
ZERO=Decimal("0.00")
SHA=re.compile(r"[a-f0-9]{64}\Z")
PERIOD=re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")
MXP=re.compile(r"MXP[0-9]+")
NONWATERFALL=(
    "EXACT_MXP_REVIEW", "GST_COMPONENT_REVIEW", "PARTIAL_REVIEW",
    "SBISA_REVIEW", "CROSS_SOL_REVIEW", "SAME_SOL_REVIEW",
)
WATERFALL="WATERFALL_REVIEW"
DNM="DNM01_PROVISIONAL_NO_RESERVATION"
PRIORITY={k:i for i,k in enumerate(NONWATERFALL+(DNM,WATERFALL))}


class Case26Refusal(ValueError):
    """Use fixed refusal reason codes, never private row data."""


def demand(condition, code):
    if not condition:
        raise Case26Refusal(code)


def money(value):
    demand(type(value) is str, "DECIMAL_STRING_REQUIRED")
    try:
        v=Decimal(value)
        demand(v.is_finite() and v == v.quantize(CENT) and v >= ZERO,
               "INVALID_OR_SUBPAISE_AMOUNT")
    except (InvalidOperation, ValueError):
        raise Case26Refusal("INVALID_OR_SUBPAISE_AMOUNT")
    return v.quantize(CENT)


def normalized(s):
    return " ".join(s.upper().split())


@dataclass(frozen=True)
class InvoiceDetail:
    source_row:int
    invoice_no:str
    sol:str
    client:str
    issue_date:date
    periods:tuple[str,...]
    taxable:str
    cgst:str
    sgst:str
    gross:str


@dataclass(frozen=True)
class BankDetail:
    source_row:int
    bank_key:str
    sol:str
    client:str
    bank_date:date
    periods:tuple[str,...]
    credit:str
    narration:str


@dataclass(frozen=True)
class MethodStep:
    bank_key:str
    invoice_no:str
    portion:str
    method:str
    proof_tag:str
    tds_rate:int|None=None


def evidence_digest(invoices,banks,steps,master_pairs,relationships):
    demand(all(type(x) is tuple for x in
               (invoices,banks,steps,master_pairs,relationships)),
           "IMMUTABLE_EVIDENCE_TUPLES_REQUIRED")
    for family,cls in ((invoices,InvoiceDetail),(banks,BankDetail),(steps,MethodStep)):
        demand(all(type(x) is cls for x in family),
               "INVALID_METHOD_EVIDENCE_TYPES")
    payload={
        "invoices":[asdict(i) for i in invoices],
        "banks":[asdict(p) for p in banks],
        "steps":[asdict(s) for s in steps],
        "selected_master_pairs":master_pairs,
        "documented_relationship_pairs":relationships,
    }
    return sha256(json.dumps(payload,sort_keys=True,default=lambda x:x.isoformat()
        if type(x) is date else None,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()


def _identity_and_source(workbook,invoices,banks):
    demand(type(workbook) is FreshWorkbook
           and type(invoices) is tuple and type(banks) is tuple,
           "EXACT_FRESH_WORKBOOK_REQUIRED")
    source_inv={i.invoice_no:i for i in workbook.invoices}
    source_bank={b.bank_key:b for b in workbook.banks}
    iv={i.invoice_no:i for i in invoices}
    pay={b.bank_key:b for b in banks}
    demand(len(source_inv)==len(workbook.invoices) and
           len(source_bank)==len(workbook.banks) and
           len(iv)==len(invoices)==len(source_inv) and
           len(pay)==len(banks)==len(source_bank),
           "SOURCE_POPULATION_OR_DUPLICATE_MISMATCH")
    demand(len({i.source_row for i in invoices})==len(invoices) and
           len({p.source_row for p in banks})==len(banks),
           "DUPLICATE_SOURCE_ROW")
    for ident,item in iv.items():
        demand(type(item) is InvoiceDetail and ident in source_inv,
               "INVOICE_NOT_IN_SOURCE")
        raw=source_inv[ident]
        demand(item.source_row==raw.source_row and
               money(item.gross)==money(raw.gross) and
               (raw.original_s is None or str(raw.original_s).strip()==""),
               "INVOICE_SOURCE_OR_PROTECTION_CONFLICT")
        demand(type(item.issue_date) is date and item.invoice_no.startswith("MXP") and
               type(item.sol) is str and type(item.client) is str and
               type(item.periods) is tuple and bool(item.periods) and
               all(type(v) is str and PERIOD.fullmatch(v) for v in item.periods),
               "INVOICE_METADATA_NOT_VERIFIED")
        demand(money(item.taxable)+money(item.cgst)+money(item.sgst)==money(item.gross),
               "INVOICE_GST_COMPONENT_TOTAL_MISMATCH")
    for ident,item in pay.items():
        demand(type(item) is BankDetail and ident in source_bank,
               "BANK_NOT_IN_SOURCE")
        raw=source_bank[ident]
        demand(item.source_row==raw.source_row and
               money(item.credit)==money(raw.credit) and
               (raw.original_k is None or str(raw.original_k).strip()==""),
               "BANK_SOURCE_OR_PROTECTION_CONFLICT")
        demand(type(item.bank_date) is date and
               type(item.sol) is str and type(item.client) is str and
               type(item.narration) is str and
               type(item.periods) is tuple and bool(item.periods) and
               all(type(v) is str and PERIOD.fullmatch(v) for v in item.periods),
               "BANK_METADATA_NOT_VERIFIED")
        demand(money(item.credit)>ZERO, "NONPOSITIVE_BANK_CREDIT")
    return iv,pay


def rehearse_methods(
    workbook,invoices,banks,steps,master_pairs,relationships, *,
    expected_workbook_digest,expected_evidence_digest,
    financial_apply="LOCKED",
):
    demand(financial_apply=="LOCKED", "FINANCIAL_APPLY_LOCK_REQUIRED")
    demand(type(steps) is tuple and type(master_pairs) is tuple and
           type(relationships) is tuple,
           "IMMUTABLE_METHOD_AND_IDENTITY_INPUT_REQUIRED")
    demand(type(expected_workbook_digest) is str and SHA.fullmatch(expected_workbook_digest)
           and type(expected_evidence_digest) is str and SHA.fullmatch(expected_evidence_digest),
           "TWO_EXACT_SHA256_PROOFS_REQUIRED")
    demand(fresh_workbook_digest(workbook)==expected_workbook_digest,
           "SCOPED_WORKBOOK_SOURCE_SHA_MISMATCH")
    demand(evidence_digest(invoices,banks,steps,master_pairs,relationships)==expected_evidence_digest,
           "SOURCE_METHOD_EVIDENCE_SHA_MISMATCH")
    inv,pay=_identity_and_source(workbook,invoices,banks)
    demand(all(type(p) is tuple and len(p)==2 and
               all(type(v) is str for v in p) for p in master_pairs),
           "OFFICIAL_MASTER_PAIR_SCHEMA_INVALID")
    demand(all(type(p) is tuple and len(p)==2 and
               all(type(v) is str for v in p) for p in relationships),
           "RELATIONSHIP_PAIR_SCHEMA_INVALID")
    official={(sol,normalized(name)) for sol,name in master_pairs}
    cross_pairs=set(relationships)
    dnm_banks={s.bank_key for s in steps if type(s) is MethodStep and s.method==DNM}
    demand(not any(type(s) is MethodStep and s.method!=DNM and s.bank_key in dnm_banks
                   for s in steps), "DNM_PROVISIONAL_AND_RESERVED_SAME_BANK")
    ordered=[]
    pending_dnm=[]
    seen=set()
    waterfall_groups=defaultdict(list)
    for step in steps:
        demand(type(step) is MethodStep and step.method in PRIORITY,
               "UNSUPPORTED_OR_UNSCOPED_METHOD")
        demand(step.bank_key in pay and step.invoice_no in inv,
               "UNKNOWN_BANK_OR_INVOICE_METHOD")
        key=(step.bank_key,step.invoice_no)
        demand(key not in seen, "DUPLICATE_METHOD_ALLOCATION_EDGE")
        seen.add(key)
        bank=pay[step.bank_key];invoice=inv[step.invoice_no]
        demand(type(step.proof_tag) is str and
               step.proof_tag.startswith("SYN-") and len(step.proof_tag)>5,
               "SYNTHETIC_DOCUMENTARY_PROOF_REQUIRED")
        demand(type(step.portion) is str, "METHOD_AMOUNT_STRING_REQUIRED")
        amount=money(step.portion)
        refs=set(MXP.findall(bank.narration.upper()))
        age=(bank.bank_date-invoice.issue_date).days
        demand(0<=age<=180, "BANK_INVOICE_180_DAY_OR_DATE_CONFLICT")
        demand(set(invoice.periods).issubset(bank.periods),
               "SERVICE_PERIOD_MULTI_MONTH_COVERAGE_CONFLICT")
        if step.method==DNM:
            demand(amount==ZERO and not refs and step.tds_rate is None,
                   "PROVISIONAL_DNM_MUST_NEVER_RESERVE")
            pending_dnm.append((bank.source_row,invoice.invoice_no,"DNM_REVIEW_ONLY"))
            continue
        demand(amount>ZERO, "NONPOSITIVE_METHOD_RESERVATION")
        if step.method in ("EXACT_MXP_REVIEW","PARTIAL_REVIEW","GST_COMPONENT_REVIEW"):
            demand(refs=={invoice.invoice_no}, "EXPLICIT_MXP_NARRATION_MISMATCH")
            demand(bank.sol==invoice.sol and normalized(bank.client)==normalized(invoice.client),
                   "EXACT_METHOD_SOL_CLIENT_CONFLICT")
        elif step.method==WATERFALL:
            demand(not refs and bank.sol==invoice.sol and
                   normalized(bank.client)==normalized(invoice.client),
                   "WATERFALL_NO_EXPLICIT_REF_AND_SAME_SOL_REQUIRED")
            waterfall_groups[bank.bank_key].append(invoice)
        elif step.method==DNM:
            pass
        elif step.method=="SAME_SOL_REVIEW":
            demand(not refs and bank.sol and bank.sol==invoice.sol and
                   normalized(bank.client)==normalized(invoice.client),
                   "SAME_SOL_IDENTITY_OR_NARRATION_CONFLICT")
            possible=[x for x in invoices if x.sol==bank.sol and
                     normalized(x.client)==normalized(bank.client) and
                     set(x.periods).issubset(bank.periods) and
                     0 <= (bank.bank_date-x.issue_date).days <= 180]
            demand(len(possible)==1, "AMBIGUOUS_SAME_SOL_WITHOUT_MXP")
        elif step.method=="SBISA_REVIEW":
            demand(bank.sol=="1" and invoice.sol=="" and not refs and
                   "SBISA" in bank.narration.upper() and
                   normalized(bank.client)==normalized(invoice.client),
                   "SBISA_EXCEPTION_IDENTITY_OR_NARRATION_REQUIRED")
        elif step.method=="CROSS_SOL_REVIEW":
            demand(bank.sol!=invoice.sol and bank.sol!="" and invoice.sol!="" and
                   refs=={invoice.invoice_no} and
                   (bank.sol,invoice.sol) in cross_pairs and
                   (bank.sol,normalized(bank.client)) in official and
                   (invoice.sol,normalized(invoice.client)) in official,
                   "CROSS_SOL_OFFICIAL_TWO_SIDED_PROOF_REQUIRED")
        if step.method=="EXACT_MXP_REVIEW":
            demand(type(step.tds_rate) is int and step.tds_rate in (0,1,2,3),
                   "EXACT_MATCH_TDS_RATE_0_TO_3_REQUIRED")
            tax=(money(invoice.taxable)*Decimal(step.tds_rate)/100).quantize(
                 CENT,rounding=ROUND_HALF_UP)
            demand(amount==money(invoice.gross)-tax and
                   amount==money(bank.credit),
                   "NET_TDS_CREDIT_MATH_MISMATCH")
        else:
            demand(step.tds_rate is None, "NONEXACT_METHOD_CANNOT_ASSERT_TDS")
        if step.method=="GST_COMPONENT_REVIEW":
            demand("GST" in bank.narration.upper() and
                   amount==money(invoice.cgst)+money(invoice.sgst),
                   "GST_LATER_COMPONENT_DOCUMENTARY_CASH_MISMATCH")
        if step.method=="PARTIAL_REVIEW":
            demand(amount<money(invoice.gross),
                   "PARTIAL_MUST_BE_LESS_THAN_INVOICE_GROSS")
        ordered.append(step)
    for key,group in waterfall_groups.items():
        demand(len(group)>=2,"MULTI_INVOICE_WATERFALL_REQUIRED")
        demand([x.invoice_no for x in group]==[
            x.invoice_no for x in sorted(group,key=lambda x:(x.issue_date,x.invoice_no))],
            "WATERFALL_OLDEST_INVOICE_FIRST_REQUIRED")
    ordered_ranks=[PRIORITY[s.method] for s in ordered]
    demand(ordered_ranks==sorted(ordered_ranks),
           "METHOD_PRIORITY_OR_WATERFALL_LAST_VIOLATION")
    # Never let the same bank credit be both DNM-provisional and reserved.
    paying={s.bank_key for s in ordered}
    demand(not any(pay[b].source_row==row for row,_,_ in pending_dnm for b in paying),
           "DNM_PROVISIONAL_AND_RESERVED_SAME_BANK")
    before=tuple(ScopedMatrixProposal(workbook.upload_id,s.bank_key,s.invoice_no,
        s.portion,s.method,s.proof_tag) for s in ordered if s.method!=WATERFALL)
    after=tuple(ScopedMatrixProposal(workbook.upload_id,s.bank_key,s.invoice_no,
        s.portion,s.method,s.proof_tag) for s in ordered if s.method==WATERFALL)
    scoped=before+(GlobalAdjudicationBoundary(),)+after
    shadow=run_independent_fresh_workbook(
        workbook,scoped,
        expected_workbook_digest=expected_workbook_digest,
        expected_scoped_plan_digest=scoped_proposal_digest(scoped),
        previous_allocations=(),previous_payment_statuses=(),
        financial_apply="LOCKED",
    )
    # Independent, duplicate arithmetic tally; the ledger is not the oracle.
    bank_cash=defaultdict(lambda:ZERO)
    inv_cash=defaultdict(lambda:ZERO)
    for s in ordered:
        a=money(s.portion)
        bank_cash[s.bank_key]+=a
        inv_cash[s.invoice_no]+=a
        demand(bank_cash[s.bank_key]<=money(pay[s.bank_key].credit) and
               inv_cash[s.invoice_no]<=money(inv[s.invoice_no].gross),
               "INDEPENDENT_METHOD_CAPACITY_EXCEEDED")
    reserved=sum(bank_cash.values(),ZERO)
    invoice_reserved=sum(inv_cash.values(),ZERO)
    bank_total=sum((money(x.credit) for x in banks),ZERO)
    invoice_total=sum((money(x.gross) for x in invoices),ZERO)
    demand(reserved==invoice_reserved and
           bank_total==reserved+(bank_total-reserved) and
           invoice_total==invoice_reserved+(invoice_total-invoice_reserved),
           "METHOD_INDEPENDENT_CASH_CONSERVATION")
    demand(money(shadow["shadow_reserved_cash_total"])==reserved and
           money(shadow["shadow_unassigned_credit_total"])==bank_total-reserved and
           money(shadow["shadow_cash_coverage_gap_not_receivable"])==invoice_total-invoice_reserved,
           "MASTER_VS_INDEPENDENT_METHOD_ACCOUNTING_MISMATCH")
    demand(shadow["financial_status"] is None and
           shadow["financial_apply_locked"] is True and
           shadow["real_database_writes"]==0 and
           shadow["complete_master_v251_matrix_v239_certified"] is False,
           "UNAUTHORIZED_FINANCIAL_RELEASE")
    demand(fresh_workbook_digest(workbook)==expected_workbook_digest and
           evidence_digest(invoices,banks,steps,master_pairs,relationships)==expected_evidence_digest,
           "MUTATED_SOURCE_OR_EVIDENCE_DURING_REHEARSAL")
    return {
        "stage":STAGE,
        "upload_id":workbook.upload_id,
        "workbook_digest":expected_workbook_digest,
        "method_evidence_digest":expected_evidence_digest,
        "methods_rehearsed":tuple(sorted({s.method for s in ordered})),
        "dnm_provisional_unreserved":tuple(sorted(pending_dnm)),
        "shadow_edges":shadow["scoped_shadow_edges"],
        "cash_reserved":str(reserved),
        "cash_unassigned":str(bank_total-reserved),
        "invoice_cash_coverage_gap_not_receivable":str(invoice_total-invoice_reserved),
        "method_oracle_cash_conserved":True,
        "one_upload_option_b":True,
        "full_matching_method_coverage_certified":False,
        "real_tds_gst_cn_documents_verified":False,
        "official_bank_utr_verified":False,
        "final_payment_status":None,
        "real_bank_allocations":0,
        "real_database_writes":0,
        "financial_apply_locked":True,
        "production_release_authorized":False,
        "full_v251_v239_certified":False,
    }
