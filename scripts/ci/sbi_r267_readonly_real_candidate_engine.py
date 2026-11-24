"""R26.7 candidate: real-source-capable, pure, READ-ONLY v2.51 rules planner.

This module has NO file, API, cloud, DB, or Excel writer access. Source intake is
independent; callers provide immutable identity-checked evidence records.
Methods are *candidate classifications*, NOT authorized settlement. No status
'OK' or 'Duplicate Payment' can be produced. Every actual bank row remains
SUSPENSE until real independent QA and Finance release. No writable ledger.

Implemented review coverage: exact MXP/0-3% TDS, multimonth, same-SOL full,
partial groups, GST-later, SBISA, cross SOL, DNM01, waterfall-last. All phases
have explicit quarantine/ambiguity handling. 180-day limit for provisional
non-reference DNM/waterfall; no double reservation. Does NOT establish full
v2.51/Matrix v2.39 certified engine or lawful TDS / Credit Note settlement.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

CENT=Decimal("0.01")
ZERO=Decimal("0.00")
ONE=Decimal("1.00")
TWO=Decimal("2.00")
TEN=Decimal("10.00")
VALID_RATE=(0,1,2,3)
INV_REF=re.compile(r"(?<![A-Za-z0-9])MXP[\s./#:\-]*([0-9]{4,8})(?![A-Za-z0-9])",re.I)
SOL_RE=re.compile(r"[0-9]{1,12}\Z")
PERIOD_RE=re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")
NONCE_RE=re.compile(r"[a-f0-9]{64}\Z")
MONTHS={x:i for i,x in enumerate(("JAN","FEB","MAR","APR","MAY","JUN",
                                 "JUL","AUG","SEP","OCT","NOV","DEC"),1)}
STAGE="R267_REAL_SOURCE_CAPABLE_REVIEW_PLANNER_NOT_CERTIFIED"


class FinancialReviewRefusal(ValueError):
    """Constant QA code only; never disclose sensitive input in exceptions."""


def cash(value):
    if isinstance(value,bool) or isinstance(value,float) or value is None:
        raise FinancialReviewRefusal("MONEY_MUST_BE_EXACT_DECIMAL_OR_STRING")
    try:
        n=Decimal(str(value).replace(",","").strip())
    except (ValueError,InvalidOperation):
        raise FinancialReviewRefusal("INVALID_EXACT_MONEY")
    if not n.is_finite():
        raise FinancialReviewRefusal("NONFINITE_MONEY")
    return n.quantize(CENT,rounding=ROUND_HALF_UP)


def normalized(value):
    if not isinstance(value,str):return ""
    return " ".join(re.findall("[A-Z0-9]+",
        unicodedata.normalize("NFKC",value).upper()))


def refs(value):
    if not isinstance(value,str):return ()
    return tuple(dict.fromkeys("MXP"+k for k in INV_REF.findall(value)))


def blank(value):
    return value is None or isinstance(value,str) and not value.strip()


@dataclass(frozen=True)
class InvoiceInput:
    source_row:int
    invoice_no:str
    sol:str
    client:str
    issue_date:date
    service_periods:tuple[str,...]
    taxable:str
    cgst:str
    sgst:str
    gross:str
    original_s:object=None


@dataclass(frozen=True)
class BankInput:
    source_row:int
    sol:str
    client:str
    bank_date:date
    service_periods:tuple[str,...]
    description:str
    credit:str
    original_k:object=None


@dataclass(frozen=True)
class RelationshipProof:
    """Review-only pair-specific documentation; NOT authorizing production."""
    payment_row:int
    invoice_no:str
    category:str
    evidence_id:str
    confirmed:bool=False


def _valid_inv(x):
    if type(x) is not InvoiceInput or type(x.source_row) is not int or x.source_row<2:
        raise FinancialReviewRefusal("INVALID_INVOICE_SOURCE_ROW")
    if not isinstance(x.invoice_no,str):
        raise FinancialReviewRefusal("INVALID_INVOICE_ID_TYPE")
    if not isinstance(x.sol,str) or (x.sol and not SOL_RE.fullmatch(x.sol)):
        raise FinancialReviewRefusal("INVOICE_SOL_NOT_EXACT_TEXT")
    if not isinstance(x.client,str) or type(x.issue_date) is not date:
        raise FinancialReviewRefusal("INVOICE_CLIENT_OR_DATE_UNVERIFIED")
    if type(x.service_periods) is not tuple or any(
       not isinstance(p,str) or not PERIOD_RE.fullmatch(p)
       for p in x.service_periods):
        raise FinancialReviewRefusal("INVOICE_SERVICE_PERIOD_INVALID")
    for money in (x.taxable,x.cgst,x.sgst,x.gross):cash(money)


def _valid_bank(x):
    if type(x) is not BankInput or type(x.source_row) is not int or x.source_row<2:
        raise FinancialReviewRefusal("INVALID_BANK_SOURCE_ROW")
    if not isinstance(x.sol,str) or not SOL_RE.fullmatch(x.sol):
        raise FinancialReviewRefusal("BANK_SOL_NOT_EXACT_TEXT")
    if type(x.bank_date) is not date or not isinstance(x.client,str):
        raise FinancialReviewRefusal("BANK_CLIENT_OR_DATE_UNVERIFIED")
    if type(x.service_periods) is not tuple or any(
       not isinstance(p,str) or not PERIOD_RE.fullmatch(p)
       for p in x.service_periods):
        raise FinancialReviewRefusal("BANK_SERVICE_PERIOD_INVALID")
    if not isinstance(x.description,str):
        raise FinancialReviewRefusal("BANK_NARRATION_NOT_TEXT")
    cash(x.credit)


def _identity(inv,bank,verified_master,proofs):
    if not normalized(inv.client) or not normalized(bank.client):
        return "EMPTY_CLIENT_IDENTITY"
    if bank.sol==inv.sol and inv.sol:
        if ((inv.sol,normalized(inv.client)) in verified_master
             and (bank.sol,normalized(bank.client)) in verified_master):
            if normalized(inv.client)==normalized(bank.client):
                return ""
            return "CLIENT_NAME_CONFLICT"
        return "SOL_CLIENT_NOT_IN_SELECTED_MASTER"
    if bank.sol=="1" and not inv.sol:
        return ("SBISA_DOCUMENTARY_PROOF_REQUIRED"
                if ("SBISA",bank.source_row,inv.invoice_no) not in proofs
                else "")
    if bank.sol and inv.sol and bank.sol!=inv.sol:
        return ("CROSS_SOL_DOCUMENTARY_PROOF_REQUIRED"
                if ("CROSS_SOL",bank.source_row,inv.invoice_no) not in proofs
                else "")
    return "SOL_OR_RELATIONSHIP_NOT_VERIFIED"


def _common(inv,bank,verified_master,proofs):
    if not blank(inv.original_s):
        return "PROTECTED_INVOICE_S_NONBLANK"
    if not blank(bank.original_k):
        return "PROTECTED_BANK_K_NONBLANK"
    if inv.issue_date>bank.bank_date:
        return "INVOICE_AFTER_BANK_POSTING"
    if not inv.service_periods or not bank.service_periods:
        return "SERVICE_PERIOD_EVIDENCE_MISSING"
    if not set(inv.service_periods).issubset(bank.service_periods):
        return "SERVICE_PERIOD_CONFLICT"
    if cash(inv.taxable)<ZERO or cash(inv.cgst)<ZERO or cash(inv.sgst)<ZERO:
        return "NEGATIVE_TAX_COMPONENT"
    if cash(inv.gross)<=ZERO:
        return "NEGATIVE_GROSS_OR_CREDIT_NOTE_REVIEW"
    if abs(cash(inv.gross)-cash(inv.taxable)-cash(inv.cgst)-cash(inv.sgst))>CENT:
        return "INVOICE_GROSS_TAX_COMPONENT_CONFLICT"
    if cash(bank.credit)<=ZERO:
        return "NONPOSITIVE_BANK_CREDIT"
    return _identity(inv,bank,verified_master,proofs)


def _tds_hypotheses(inv,bank):
    rates=[]
    for rate in VALID_RATE:
        hypothetical=(cash(inv.taxable)*Decimal(rate)/Decimal(100)).quantize(
           CENT,rounding=ROUND_HALF_UP)
        expected=cash(inv.gross)-hypothetical
        delta=abs(cash(bank.credit)-expected)
        rates.append((delta,rate))
    return sorted(rates)


def _proof_catalog(proofs):
    out=set()
    for p in proofs:
        if type(p) is not RelationshipProof or p.category not in (
            "SBISA","CROSS_SOL","GST","PARTIAL","WATERFALL"):
            raise FinancialReviewRefusal("INVALID_RELATIONSHIP_PROOF_TYPE")
        if type(p.confirmed) is not bool:
            raise FinancialReviewRefusal("DOCUMENTARY_CONFIRMATION_INVALID")
        if type(p.payment_row) is not int or p.payment_row<2:
            raise FinancialReviewRefusal("INVALID_DOCUMENTARY_BANK_ROW")
        if not isinstance(p.evidence_id,str) or not p.evidence_id:
            raise FinancialReviewRefusal("EVIDENCE_REFERENCE_REQUIRED")
        # Real proofs still require owner signed approval; confirmed=False
        # holds every case. This object's confirmed field is never sufficient
        # to change financial statuses or authorize Apply.
        if p.confirmed:
            out.add((p.category,p.payment_row,p.invoice_no))
    return out


def plan_review_only(
    invoices,bank_rows,master_pairs,*,source_sha256,master_sha256,
    relationship_proofs=(),financial_apply="LOCKED",
):
    if financial_apply!="LOCKED":
        raise FinancialReviewRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if any(not isinstance(k,str) or not NONCE_RE.fullmatch(k)
           for k in (source_sha256,master_sha256)):
        raise FinancialReviewRefusal("EXACT_SOURCE_AND_MASTER_SHA256_REQUIRED")
    if type(invoices) not in (list,tuple) or type(bank_rows) not in (list,tuple):
        raise FinancialReviewRefusal("SOURCE_RECORD_LISTS_REQUIRED")
    if type(master_pairs) not in (list,tuple) or len(master_pairs)>30000:
        raise FinancialReviewRefusal("MASTER_IDENTITY_LIST_LIMIT")
    if len(invoices)>50000 or len(bank_rows)>50000:
        raise FinancialReviewRefusal("READONLY_SOURCE_ROW_LIMIT")
    for i in invoices:_valid_inv(i)
    for p in bank_rows:_valid_bank(p)
    master=set()
    for item in master_pairs:
        if type(item) not in (tuple,list) or len(item)!=2:
            raise FinancialReviewRefusal("MASTER_PAIR_SCHEMA_REQUIRED")
        sol,name=item
        if not isinstance(sol,str) or not SOL_RE.fullmatch(sol):
            # Reject malformed master rows; private importer should hold them.
            continue
        if not isinstance(name,str) or not normalized(name):
            continue
        master.add((sol,normalized(name)))
    documented=_proof_catalog(relationship_proofs)
    id_counts=Counter(i.invoice_no for i in invoices if i.invoice_no)
    inv_source_counts=Counter(i.source_row for i in invoices)
    bank_source_counts=Counter(p.source_row for p in bank_rows)
    valid_inv={}
    invoice_holds=defaultdict(set)
    by_sol=defaultdict(list)
    for inv in invoices:
        key=inv.invoice_no
        if not key or not re.fullmatch(r"MXP[0-9]{4,8}",key):
            invoice_holds[inv.source_row].add("INVALID_MXP_INVOICE_REFERENCE")
            continue
        if id_counts[key]!=1 or inv_source_counts[inv.source_row]!=1:
            invoice_holds[inv.source_row].add("DUPLICATE_INVOICE_ID_OR_ROW")
            continue
        if not blank(inv.original_s):
            invoice_holds[inv.source_row].add("PROTECTED_INVOICE_S_NONBLANK")
            continue
        if cash(inv.gross)<=ZERO:
            invoice_holds[inv.source_row].add("NEGATIVE_GROSS_CREDIT_NOTE_REVIEW")
            continue
        if abs(cash(inv.gross)-cash(inv.taxable)-cash(inv.cgst)-cash(inv.sgst))>CENT:
            invoice_holds[inv.source_row].add("INVOICE_GROSS_COMPONENTS_MISMATCH")
            continue
        valid_inv[key]=inv
        by_sol[inv.sol].append(inv)
    # Reserve only in local memory; conservation verified again globally.
    reserved_cash=defaultdict(lambda:ZERO)
    reserved_invoice=defaultdict(lambda:ZERO)
    proposals=[]
    holds=defaultdict(set)
    examined=Counter()
    pool=set()

    # Stage 1: unique exact MXP references + exact TDS.
    for p in sorted(bank_rows,key=lambda x:x.source_row):
        if bank_source_counts[p.source_row]>1:
            holds[p.source_row].add("DUPLICATE_BANK_SOURCE_ROW")
            continue
        if cash(p.credit)<=ZERO:
            holds[p.source_row].add("NONPOSITIVE_BANK_CREDIT")
            continue
        if not blank(p.original_k):
            holds[p.source_row].add("PROTECTED_BANK_K_NONBLANK")
            continue
        linked=refs(p.description)
        if len(linked)>1:
            holds[p.source_row].add("CONTRADICTORY_MULTIPLE_MXP_REFERENCES")
            continue
        if len(linked)!=1:
            pool.add(p.source_row)
            continue
        inv=valid_inv.get(linked[0])
        if inv is None:
            holds[p.source_row].add("NAMED_MXP_UNAVAILABLE_OR_QUARANTINED")
            continue
        reason=_common(inv,p,master,documented)
        if reason:
            holds[p.source_row].add(reason)
            continue
        if re.search(r"\b(?:GST|SGST|CGST|IGST)\b",p.description,re.I):
            if ("GST",p.source_row,inv.invoice_no) not in documented:
                holds[p.source_row].add("GST_LATER_APPROVAL_MISSING")
                continue
            if abs(cash(p.credit)-cash(inv.cgst)-cash(inv.sgst))>CENT:
                holds[p.source_row].add("GST_COMPONENT_NOT_EQUAL_SOURCE_TAX")
                continue
            method="GST_LATER_DOCUMENTED_CANDIDATE";rate=None
        else:
            hypotheses=_tds_hypotheses(inv,p)
            if hypotheses[0][0]<=CENT and (
                len(hypotheses)==1 or hypotheses[1][0]>hypotheses[0][0]):
                method="EXACT_MXP_TDS_REVIEW";rate=hypotheses[0][1]
            elif ("PARTIAL",p.source_row,inv.invoice_no) in documented:
                method="EXACT_MXP_PARTIAL_REVIEW";rate=None
            else:
                holds[p.source_row].add("EXACT_MXP_AMOUNT_OR_PARTIAL_PROOF_MISSING")
                continue
        if reserved_cash[p.source_row]+cash(p.credit)>cash(p.credit):
            holds[p.source_row].add("BANK_CREDIT_ALREADY_RESERVED")
            continue
        # A 0-3% TDS difference is NOT automatically a paid invoice balance;
        # cash-only reservation is conservative and never a financial write.
        if reserved_invoice[inv.invoice_no]+cash(p.credit)>cash(inv.gross)+CENT:
            holds[p.source_row].add("INVOICE_CASH_CAPACITY_CONFLICT")
            continue
        reserved_cash[p.source_row]+=cash(p.credit)
        reserved_invoice[inv.invoice_no]+=cash(p.credit)
        proposals.append((p.source_row,inv.invoice_no,str(cash(p.credit)),method,rate))
        examined[method]+=1

    # Stage 2: DNM01 provisional, no cash reservation. Any explicit MXP
    # reference was processed above and is NOT eligible for a fallback.
    for p in sorted(bank_rows,key=lambda x:x.source_row):
        if p.source_row not in pool or p.source_row in holds:
            continue
        if re.search(r"\b(?:GST|SGST|CGST|IGST)\b",p.description,re.I):
            holds[p.source_row].add("GST_NARRATION_REQUIRES_EXACT_EVIDENCE")
            continue
        if reserved_cash[p.source_row]>ZERO:
            holds[p.source_row].add("PAYMENT_ALREADY_RESERVED")
            continue
        viable=[]
        for inv in by_sol.get(p.sol,()):
            age=(p.bank_date-inv.issue_date).days
            if age<0 or age>180:continue
            if _common(inv,p,master,documented):continue
            if reserved_invoice[inv.invoice_no]>ZERO:continue
            delta,rate=_tds_hypotheses(inv,p)[0]
            if delta<=TEN:
                viable.append((delta,inv.invoice_no,rate))
        viable.sort()
        if not viable:
            holds[p.source_row].add("DNM_NO_ELIGIBLE_CANDIDATE")
        elif viable[0][0]>ONE:
            holds[p.source_row].add("DNM_NEAREST_OVER_ONE_RUPEE")
        elif len(viable)>1 and viable[1][0]-viable[0][0]<TWO:
            holds[p.source_row].add("DNM_AMBIGUOUS_RUNNER_UP")
        else:
            proposals.append((p.source_row,viable[0][1],str(cash(p.credit)),
                              "DNM01_PROVISIONAL_NO_RESERVATION",viable[0][2]))
            examined["DNM01_PROVISIONAL"]+=1
    # Stage 3: WATERFALL LAST. Without signed evidence we HOLD. This is
    # a discovery pass that lists evidence requirements but no cash writes.
    for p in bank_rows:
        if p.source_row in pool and (
             ("WATERFALL",p.source_row,"*") in documented):
            holds[p.source_row].add("WATERFALL_FULL_LEDGER_QA_REQUIRED")
    # Re-check global conservation for stage-1 exact candidates.
    by_payment={p.source_row:p for p in bank_rows}
    if any(reserved_cash[row]>cash(by_payment[row].credit)+CENT
           for row in reserved_cash):
        raise FinancialReviewRefusal("GLOBAL_BANK_CREDIT_NONCONSERVATION")
    if any(reserved_invoice[key]>cash(valid_inv[key].gross)+CENT
           for key in reserved_invoice):
        raise FinancialReviewRefusal("GLOBAL_INVOICE_CASH_OVERRESERVATION")
    return {
        "stage":STAGE,
        "source_sha256":source_sha256,"master_sha256":master_sha256,
        "source_invoice_count":len(invoices),
        "bank_row_count":len(bank_rows),
        "candidate_rows":tuple(proposals),
        "invoice_quarantines":tuple(sorted(
            (row,tuple(sorted(rs))) for row,rs in invoice_holds.items())),
        "bank_review_holds":tuple(sorted(
            (row,tuple(sorted(rs))) for row,rs in holds.items())),
        "review_method_counts":dict(sorted(examined.items())),
        "global_cash_reserved_hypothesis_only":str(sum(reserved_cash.values(),ZERO)),
        "dnm_does_not_reserve_money":True,
        "waterfall_only_after_global":True,
        "protected_original_source_mutated":False,
        "all_real_bank_statuses":"SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL",
        "financial_apply_locked":True,
        "real_database_writes":0,
        "production_release_authorized":False,
        "complete_master_v251_matrix_v239_certified":False,
        "real_v218_financial_writer_certified":False,
    }
