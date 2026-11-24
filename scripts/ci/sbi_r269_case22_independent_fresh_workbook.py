"""R26.9 Case 2.2 — owner-approved Option B: independent fresh-upload ledger.

Every uploaded workbook is an isolated reconciliation scope. No previous
workbook allocations, historical statuses, invoice balances, or imported bank
rows are consulted, applied, inherited, or copied. Repeated invoice numbers
and source row numbers in OTHER workbooks are allowed; duplicates WITHIN one
workbook still fail closed.

This is a pure dry-run wrapper around the R26.9 Case 2.1 core cash ledger.
Matrix proposals are only hypothetical cash reservations, not a final
financial verdict, TDS/GST/CN settlement, or independent bank-event proof.
Original source SHA is a caller-provided, upstream-verified reference; the
additional batch digest binds normalized rows and their provenance to this
one upload, not a substitute for verifying original XLSX bytes.

No database read, DB write, Excel write, API, financial status, historical
carry forward, automatic approval, or production Apply code is present.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from sbi_r269_core_cash_ledger_dry_run import (
    BankCapacity, GlobalAdjudicationBoundary, InvoiceCapacity, LedgerRefusal,
    MatrixProposal, dry_run_cash_ledger, plan_digest,
)

STAGE = "R269_CASE22_INDEPENDENT_FRESH_WORKBOOK_LEDGER_DRY_RUN_ONLY"
MODE = "INDEPENDENT_FRESH_WORKBOOK"
UPLOAD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,95}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")


class FreshBatchRefusal(ValueError):
    """Constant refusal code; never disclose private bank or invoice data."""


@dataclass(frozen=True)
class ScopedInvoice:
    upload_id: str
    invoice_no: str
    source_row: int
    gross: str
    original_s: str | int | None = None


@dataclass(frozen=True)
class ScopedBank:
    upload_id: str
    bank_key: str
    source_row: int
    credit: str
    original_k: str | int | None = None


@dataclass(frozen=True)
class ScopedMatrixProposal:
    upload_id: str
    bank_key: str
    invoice_no: str
    portion: str
    method: str
    evidence_ref: str


@dataclass(frozen=True)
class FreshWorkbook:
    upload_id: str
    source_sha256: str
    master_sha256: str
    invoices: tuple[ScopedInvoice, ...]
    banks: tuple[ScopedBank, ...]
    mode: str = MODE


def _digest_payload(obj):
    return sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def fresh_workbook_digest(workbook):
    """Bind one upload's exact normalized source rows and declared source hash.

    A changed amount, row, upload ID, master/source hash, or original status
    must change the batch digest. This is not an external financial signature.
    """
    if type(workbook) is not FreshWorkbook:
        raise FreshBatchRefusal("FRESH_WORKBOOK_SNAPSHOT_REQUIRED")
    if type(workbook.upload_id) is not str or not UPLOAD_ID.fullmatch(workbook.upload_id):
        raise FreshBatchRefusal("EXPLICIT_VALID_FRESH_UPLOAD_ID_REQUIRED")
    if workbook.mode != MODE:
        raise FreshBatchRefusal("INDEPENDENT_FRESH_WORKBOOK_MODE_REQUIRED")
    if (type(workbook.source_sha256) is not str
            or type(workbook.master_sha256) is not str
            or not SHA.fullmatch(workbook.source_sha256)
            or not SHA.fullmatch(workbook.master_sha256)):
        raise FreshBatchRefusal("EXPLICIT_SOURCE_AND_MASTER_SHA256_REQUIRED")
    if (type(workbook.invoices) is not tuple or type(workbook.banks) is not tuple
            or len(workbook.invoices) > 50000 or len(workbook.banks) > 50000):
        raise FreshBatchRefusal("FRESH_RECORD_TUPLE_REQUIRED")
    for entry in workbook.invoices:
        if type(entry) is not ScopedInvoice:
            raise FreshBatchRefusal("SCOPED_INVOICE_REQUIRED")
        if entry.upload_id != workbook.upload_id:
            raise FreshBatchRefusal("FOREIGN_INVOICE_UPLOAD_SCOPE")
        if type(entry.original_s) not in (str,int,type(None)):
            raise FreshBatchRefusal("INVALID_PROTECTED_INVOICE_MARKER")
    for entry in workbook.banks:
        if type(entry) is not ScopedBank:
            raise FreshBatchRefusal("SCOPED_BANK_REQUIRED")
        if entry.upload_id != workbook.upload_id:
            raise FreshBatchRefusal("FOREIGN_PAYMENT_UPLOAD_SCOPE")
        if type(entry.original_k) not in (str,int,type(None)):
            raise FreshBatchRefusal("INVALID_PROTECTED_PAYMENT_MARKER")
    return _digest_payload({
        "upload_id":workbook.upload_id,
        "source_sha256":workbook.source_sha256,
        "master_sha256":workbook.master_sha256,
        "mode":workbook.mode,
        "invoice_rows":[asdict(item) for item in workbook.invoices],
        "payment_rows":[asdict(item) for item in workbook.banks],
    })


def scoped_proposal_digest(steps):
    """Bind the Matrix plan to the same scoped upload, preserving order."""
    if type(steps) is not tuple or len(steps)>100000:
        raise FreshBatchRefusal("SCOPED_MATRIX_PLAN_TUPLE_REQUIRED")
    items=[]
    for step in steps:
        if type(step) is ScopedMatrixProposal:
            items.append({"kind":"ScopedMatrixProposal",**asdict(step)})
        elif type(step) is GlobalAdjudicationBoundary:
            items.append({"kind":"GlobalAdjudicationBoundary",**asdict(step)})
        else:
            raise FreshBatchRefusal("FOREIGN_OR_UNKNOWN_MATRIX_STEP")
    return _digest_payload(items)


def run_independent_fresh_workbook(
    workbook, steps, *,
    expected_workbook_digest,
    expected_scoped_plan_digest,
    previous_allocations=(),
    previous_payment_statuses=(),
    financial_apply="LOCKED",
):
    """Execute ONE workbook, no DB queries or cross-upload allocation imports.

    The previous_* arguments exist ONLY as fail-closed sentinels. If another
    caller tries to inject history, reject rather than silently ignore it.
    No global mutable state: two fresh uploads may each use MXP10001 or row 2.
    """
    if financial_apply != "LOCKED":
        raise FreshBatchRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if previous_allocations not in ((), None):
        raise FreshBatchRefusal("PREVIOUS_WORKBOOK_ALLOCATIONS_NOT_PERMITTED")
    if previous_payment_statuses not in ((), None):
        raise FreshBatchRefusal("HISTORICAL_PAYMENT_STATUSES_NOT_PERMITTED")
    for marker in (expected_workbook_digest, expected_scoped_plan_digest):
        if type(marker) is not str or not SHA.fullmatch(marker):
            raise FreshBatchRefusal("TWO_BATCH_BOUND_SHA256_MANIFESTS_REQUIRED")
    if fresh_workbook_digest(workbook) != expected_workbook_digest:
        raise FreshBatchRefusal("FRESH_WORKBOOK_SNAPSHOT_DIGEST_MISMATCH")
    if scoped_proposal_digest(steps) != expected_scoped_plan_digest:
        raise FreshBatchRefusal("FRESH_MATRIX_PLAN_DIGEST_MISMATCH")

    actual=[]
    for step in steps:
        if type(step) is GlobalAdjudicationBoundary:
            actual.append(step)
        elif type(step) is ScopedMatrixProposal:
            if step.upload_id != workbook.upload_id:
                raise FreshBatchRefusal("FOREIGN_MATRIX_PROPOSAL_UPLOAD_SCOPE")
            actual.append(MatrixProposal(
                step.bank_key, step.invoice_no, step.portion,
                step.method, step.evidence_ref,
            ))
        else:
            raise FreshBatchRefusal("UNRECOGNIZED_SCOPED_PLAN_STEP")
    source_invoices=tuple(
        InvoiceCapacity(x.invoice_no,x.source_row,x.gross,x.original_s)
        for x in workbook.invoices
    )
    source_banks=tuple(
        BankCapacity(x.bank_key,x.source_row,x.credit,x.original_k)
        for x in workbook.banks
    )
    bound_steps=tuple(actual)
    # Core performs strict duplicate checks and atomically refuses any
    # overdraw / protected original markers / bad waterfall order.
    ledger=dry_run_cash_ledger(
        source_invoices, source_banks, bound_steps,
        source_sha256=workbook.source_sha256,
        master_sha256=workbook.master_sha256,
        expected_plan_sha256=plan_digest(bound_steps),
        financial_apply="LOCKED",
    )
    # Verify immutable input binding again after execution.
    if (fresh_workbook_digest(workbook)!=expected_workbook_digest
            or scoped_proposal_digest(steps)!=expected_scoped_plan_digest):
        raise FreshBatchRefusal("FRESH_WORKBOOK_CHANGED_DURING_CALCULATION")
    return {
        **ledger,
        "stage": STAGE,
        "upload_id": workbook.upload_id,
        "upload_mode": MODE,
        "workbook_digest": expected_workbook_digest,
        "scoped_matrix_plan_digest": expected_scoped_plan_digest,
        "bank_rows_in_this_upload":len(workbook.banks),
        "invoice_rows_in_this_upload":len(workbook.invoices),
        # Every row exported to later review stages keeps its upload scope.
        # Unscoped core output is retained only for backwards test parity.
        "scoped_shadow_edges":tuple(
            (workbook.upload_id,)+tuple(edge) for edge in ledger["shadow_edges"]
        ),
        "scoped_shadow_bank_rows":tuple(
            (workbook.upload_id,)+tuple(row) for row in ledger["shadow_bank_rows"]
        ),
        "scoped_shadow_invoice_cash_rows":tuple(
            (workbook.upload_id,)+tuple(row)
            for row in ledger["shadow_invoice_cash_rows"]
        ),
        "historical_workbooks_read":False,
        "previous_approved_allocations_imported":False,
        "previous_payment_statuses_imported":False,
        "cross_workbook_allocation_performed":False,
        "same_invoice_number_in_another_upload_is_not_an_intrabatch_duplicate":True,
        "cross_upload_transaction_duplicate_detection_completed":False,
        "finance_approved_balance_or_utr_confirmed":False,
        "source_xlsx_sha_validated_at_this_layer":False,
        "financial_status":None,
        "financial_apply_locked":True,
        "real_database_writes":0,
        "production_release_authorized":False,
        "complete_master_v251_matrix_v239_certified":False,
    }
