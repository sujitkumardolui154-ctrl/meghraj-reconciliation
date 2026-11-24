"""R26.7 actual v2.18-format, FINANCE-LOCKED REVIEW writer using artifact_tool.

This is a *candidate review* serializer, not a certified financial writer or
paid-status authority. It only sets PAYMNENT M:W and Invoice Details. AI:AM.
No source financial value, original paid marker, ledger balance or original
financial formula may be modified. All bank M statuses stay SUSPENSE.

The artifact_tool import/export is intentionally separate from the pure
read-only financial engine, so a failed/expensive workbook import cannot
silently substitute a partial or old reconciled file. No cloud/DB access.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re

from sbi_r267_readonly_real_candidate_engine import normalized

PAYMENT_HEADERS=(
    "Model Reconciliation Status",
    "Model Reconciliation Remarks",
    "Model Invoice No (Candidate if SUSPENSE)",
    "Model Invoice Source Row",
    "Model Match Method",
    "Model TDS Rate % (Inferred)",
    "Model Expected Credit (Hypothesis)",
    "Model Signed Residual",
    "Model Service / Evidence",
    "Model SOL ID",
    "Model Proper Client Name",
)
INVOICE_HEADERS=(
    "Model SOL ID","Model Proper Client Name",
    "Model Linked Bank Row (Working)","Model Linked Bank Credit",
    "Model Match Evidence",
)
STAGE="R267_V218_CANDIDATE_REVIEW_WRITER_NOT_FINANCE_CERTIFIED"


class R267WriterRefusal(ValueError):
    """Constant release/format refusal code."""


def _check_plan(snapshot,review):
    if review.get("stage")!="R267_REAL_SOURCE_CAPABLE_REVIEW_PLANNER_NOT_CERTIFIED":
        raise R267WriterRefusal("EXPECTED_R267_READONLY_PLAN_REQUIRED")
    if (snapshot.source_sha256!=review.get("source_sha256")
            or snapshot.master_sha256!=review.get("master_sha256")):
        raise R267WriterRefusal("SOURCE_OR_MASTER_SHA_MISMATCH")
    if (review.get("financial_apply_locked") is not True
            or review.get("real_database_writes")!=0
            or review.get("complete_master_v251_matrix_v239_certified") is not False
            or review.get("all_real_bank_statuses")!="SUSPENSE_UNTIL_INDEPENDENT_FINANCE_APPROVAL"):
        raise R267WriterRefusal("UNAUTHORIZED_LEDGER_APPLY_OR_RELEASE")
    if review.get("source_invoice_count")!=len(snapshot.invoices):
        raise R267WriterRefusal("REVIEW_INVOICE_COUNT_MISMATCH")
    if review.get("bank_row_count")!=len(snapshot.payments):
        raise R267WriterRefusal("REVIEW_BANK_COUNT_MISMATCH")


def build_preview_cells(snapshot,review):
    """Pure model columns without changing source; suitable for unit tests."""
    _check_plan(snapshot,review)
    pre=snapshot.source_preflight
    paycount=pre["payment_data_rows"]
    invcount=pre["invoice_data_rows"]
    # A complete original source row map must be accounted for in the
    # normalized-source view or hold register, including non-Credit lines.
    valid_pay={p.source_row:p for p in snapshot.payments}
    valid_inv={i.source_row:i for i in snapshot.invoices}
    held_pay=defaultdict(set);held_inv=defaultdict(set)
    for group,row,code in snapshot.review_only_hold_codes:
        if group=="PAYMENT":held_pay[row].add(code)
        if group=="INVOICE":held_inv[row].add(code)
    for row,codes in review["bank_review_holds"]:
        held_pay[row].update(codes)
    for row,codes in review["invoice_quarantines"]:
        held_inv[row].update(codes)
    if len(valid_pay)+len(held_pay.keys()-valid_pay.keys())!=paycount:
        raise R267WriterRefusal("PAYMENT_ROW_MAPPING_INCOMPLETE")
    if len(valid_inv)+len(held_inv.keys()-valid_inv.keys())!=invcount:
        raise R267WriterRefusal("INVOICE_ROW_MAPPING_INCOMPLETE")
    if any(r<2 or r>paycount+1 for r in valid_pay|held_pay):
        raise R267WriterRefusal("PAYMENT_SOURCE_ROW_OUT_OF_BOUNDS")
    if any(r<2 or r>invcount+1 for r in valid_inv|held_inv):
        raise R267WriterRefusal("INVOICE_SOURCE_ROW_OUT_OF_BOUNDS")

    official={(code,normalized(name)):(code,name)
              for code,name in snapshot.master_pairs}
    inv_by_num={i.invoice_no:i for i in snapshot.invoices}
    proposed=defaultdict(list)
    inv_proposed=defaultdict(list)
    for payrow,invoice_no,bank_credit,method,rate in review["candidate_rows"]:
        if not isinstance(bank_credit,str):
            raise R267WriterRefusal("CANDIDATE_MONEY_MUST_BE_TEXT")
        if payrow not in valid_pay or invoice_no not in inv_by_num:
            raise R267WriterRefusal("CANDIDATE_NOT_IN_VERIFIED_SNAPSHOT")
        proposed[payrow].append((invoice_no,bank_credit,method,rate))
        inv_proposed[invoice_no].append((payrow,bank_credit,method,rate))
    payment_rows=[]
    for row in range(2,paycount+2):
        record=valid_pay.get(row)
        holds=held_pay.get(row,set())
        proposals=proposed.get(row,())
        if proposals and holds:
            raise R267WriterRefusal("CANDIDATE_AND_HOLD_CONFLICT")
        if len(proposals)>1:
            raise R267WriterRefusal("AMBIGUOUS_MULTI_INVOICE_PAYMENT")
        # Every actual bank source row has category-only SUSPENSE in M.
        cells=["SUSPENSE",None,None,None,None,None,None,None,None,None,None]
        if record is None:
            cells[1]="; ".join(sorted(holds)) or "SOURCE_CREDIT_NOT_ELIGIBLE"
        else:
            cells[9]=record.sol
            accepted=official.get((record.sol,normalized(record.client)))
            cells[10]=accepted[1] if accepted else None
            if holds:
                cells[1]="; ".join(sorted(holds))
            elif proposals:
                invoice_no,credit,method,rate=proposals[0]
                inv=inv_by_num[invoice_no]
                cells[1]="CANDIDATE ONLY; NO BANK/FINANCE CERTIFICATION"
                cells[2]=invoice_no
                cells[3]=inv.source_row
                cells[4]=method
                cells[5]=rate
                cells[6]=float(Decimal(credit))
                cells[7]=None   # No asserted signed residual without full oracle
                cells[8]="SOURCE/HASH VERIFIED; FINANCE APPLY LOCKED"
            else:
                cells[1]="NO VERIFIED MATCH; REVIEW"
        payment_rows.append(cells)
    invoice_rows=[]
    for row in range(2,invcount+2):
        record=valid_inv.get(row)
        holds=held_inv.get(row,set())
        if record is None:
            invoice_rows.append([None,None,None,None,
                                 "; ".join(sorted(holds)) or "SOURCE_INELIGIBLE"])
            continue
        accepted=official.get((record.sol,normalized(record.client)))
        links=inv_proposed.get(record.invoice_no,())
        entry=[
            accepted[0] if accepted else None,
            accepted[1] if accepted else None,
            None,None,
            "; ".join(sorted(holds)) if holds else "NOT LINKED; REVIEW ONLY",
        ]
        if links and not holds:
            entry[4]="CANDIDATE CASH ONLY; NOT SETTLED"
            if len(links)==1:
                payrow,credit,method,rate=links[0]
                entry[2]=payrow
                entry[3]=float(Decimal(credit))
            else:
                entry[4]="MULTIPLE PARTIAL CANDIDATES; NO PAID STATUS"
        invoice_rows.append(entry)
    return payment_rows,invoice_rows


def apply_locked_model_columns(workbook,snapshot,review):
    """Modify only model columns of an already IMPORTED artifact_tool workbook.

    Caller owns the workbook lifecycle and final independent source-value
    preservation test. No monetary settlement or file read/write inside here.
    """
    payments,invoices=build_preview_cells(snapshot,review)
    p=workbook.worksheets.get_item("PAYMNENT")
    i=workbook.worksheets.get_item("Invoice Details.")
    p.get_range("M1:W1").values=[list(PAYMENT_HEADERS)]
    i.get_range("AI1:AM1").values=[list(INVOICE_HEADERS)]
    if payments:p.get_range(f"M2:W{len(payments)+1}").values=payments
    if invoices:i.get_range(f"AI2:AM{len(invoices)+1}").values=invoices
    return {
        "stage":STAGE,
        "payment_model_rows":len(payments),
        "invoice_model_rows":len(invoices),
        "all_bank_statuses":"SUSPENSE",
        "protected_invoice_original_columns":"A:AH",
        "protected_payment_original_columns":"A:L",
        "financial_apply_locked":True,
        "real_bank_allocations":0,
        "financial_statuses_certified":False,
        "v218_real_monetary_parity_certified":False,
        "production_release_authorized":False,
    }


def export_locked_preview_from_private_file(
    source_path,output_path,snapshot,review,*,financial_apply="LOCKED",
):
    """Private development-only XLSX export; never modifies source file.

    On a large Excel workbook artifact_tool may refuse resource allocation.
    Failure is a HARD BLOCK; do not silently create a structurally degraded ZIP.
    """
    if financial_apply!="LOCKED":
        raise R267WriterRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    _check_plan(snapshot,review)
    source_path=Path(source_path)
    output_path=Path(output_path)
    if source_path.resolve()==output_path.resolve():
        raise R267WriterRefusal("OUTPUT_MAY_NOT_OVERWRITE_ORIGINAL_SOURCE")
    if sha256(source_path.read_bytes()).hexdigest()!=snapshot.source_sha256:
        raise R267WriterRefusal("INPUT_SOURCE_FILE_SHA_MISMATCH")
    from artifact_tool import Blob,SpreadsheetFile
    book=SpreadsheetFile.import_xlsx(Blob.load(str(source_path)))
    receipt=apply_locked_model_columns(book,snapshot,review)
    # Caller must inspect downstream R18 exact protected source/formula parity.
    # Serialize only after the in-memory review model is fully constructed.
    SpreadsheetFile.export_xlsx(book).save(str(output_path))
    receipt["output_sha256"]=sha256(output_path.read_bytes()).hexdigest()
    receipt["source_sha256"]=snapshot.source_sha256
    return receipt
