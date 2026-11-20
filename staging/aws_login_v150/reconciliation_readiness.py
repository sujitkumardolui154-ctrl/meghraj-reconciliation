"""Read-only payment-to-engine preflight, not a financial reconciliation engine.

The recovery source audit establishes that no approved, complete allocation
engine, original ledger and financial writer are connected to this AWS UI.
Never turn a 3-column evidence upload into an invoice allocation or database
update by guessing SOL/narration/TDS rules. All finance writes are fail-closed.

This blueprint validates immutable, account-scoped evidence and explicitly
reports the remaining source/engine/release blockers. It does not import
Firestore, update invoice records or issue tasks to an unverified service.
"""
import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from flask import Blueprint, g, jsonify, request
from dashboard_sessions import csrf_valid
from payment_evidence_upload import RECEIPT_RE, _store, _connection, _parse

reconciliation_readiness = Blueprint("sbi_reconciliation_readiness", __name__)

BLOCKERS = (
    "FULL_AUTHORITATIVE_PAYMENT_SHEET_REQUIRED",
    "CURRENT_INVOICE_SOURCE_AND_APPROVED_ALLOCATION_LEDGER_REQUIRED",
    "APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED",
    "FINANCIAL_DATABASE_WRITER_NOT_VERIFIED",
    "INDEPENDENT_FINANCIAL_QA_AND_RELEASE_AUTHORIZATION_REQUIRED",
)


def _unlock_requirements():
    """Read-only remediation checklist; never grants finance execution.

    The original historical bank and invoice ledgers are out of scope under
    the owner's policy. Missing requirements cannot be satisfied by changing
    HTML, a feature flag, user-supplied claims, or synthetic QA success.
    """
    return [
        {
            "id": "NEW_PAYMENT_IDENTITY_AND_DATE",
            "status": "BLOCKED",
            "explanation": (
                "The three-column upload has no verified bank transaction date "
                "or UTR. Workbook duplicate hashes do not establish uniqueness."
            ),
            "required_work": (
                "Add a versioned, authenticated, server-validated NEW payment "
                "evidence contract with bank date, unique reference, original "
                "Credit-I provenance and an enforced activation cutoff."
            ),
        },
        {
            "id": "POST_ACTIVATION_INVOICE_AND_LEDGER",
            "status": "BLOCKED",
            "explanation": (
                "There is no certified, isolated post-activation invoice ledger "
                "and prior allocations must not be accessed or recomputed."
            ),
            "required_work": (
                "Define a new-only invoice source and an isolated allocation "
                "store that never mounts, reads or changes legacy financial data."
            ),
        },
        {
            "id": "CANONICAL_ALLOCATOR",
            "status": "BLOCKED",
            "explanation": (
                "Synthetic candidate/waterfall previews do not implement or "
                "certify all approved SBI reconciliation rules."
            ),
            "required_work": (
                "Implement and independently certify new-only SOL, service "
                "period, GST/TDS, full/partial waterfall, SBISA and "
                "duplicate/credit-note conflict rules with synthetic QA."
            ),
        },
        {
            "id": "TRANSACTIONAL_WRITER_AND_REVIEW",
            "status": "BLOCKED",
            "explanation": (
                "No authorized reconciliation writer, duplicate-safe new "
                "record receipt, owner review approval or rollback is connected."
            ),
            "required_work": (
                "Build isolated append-only new-ledger posting with "
                "idempotency, authenticated reviewer approval, audit and rollback."
            ),
        },
        {
            "id": "INDEPENDENT_RELEASE_EVIDENCE",
            "status": "BLOCKED",
            "explanation": (
                "An AWS-running UI and successful synthetic tests alone do "
                "not prove financial engine production readiness."
            ),
            "required_work": (
                "Complete independent synthetic integration/negative QA, "
                "source-pinned staging, permission checks, rollback rehearsal "
                "and separate owner sign-off before any finance activation."
            ),
        },
    ]


def _base_response():
    return {
        "engine": "NOT_CONNECTED",
        "state": "BLOCKED_PRODUCTION_DEPENDENCIES",
        "financial_database": "NOT_CONNECTED",
        "payment_matching_executed": False,
        "financial_writes": False,
        "reconciliation_executed": False,
        "allocation_approved": False,
        "required_source_sheets": ["PAYMNENT", "Invoice Details."],
        "required_bank_credit_column": "PAYMNENT!I",
        "required_source_protection": "PAYMNENT!A:L and invoice originals unchanged",
        "staged_three_column_evidence_is_authoritative": False,
        "blockers": list(BLOCKERS),
        "unlock_requirements": _unlock_requirements(),
        "unlock_allowed": False,
        "execution_mode": "FINANCIAL_APPLY_BLOCKED",
        "synthetic_qa_is_production_approval": False,
        "historical_financial_read_authorized": False,
        "historical_financial_write_authorized": False,
        "historical_reconciliation_authorized": False,
        "eligible_future_only_scope": "NOT_YET_CERTIFIED",
        "existing_payment_evidence_format": [
            "Description", "SOL ID", "Credit Amount",
        ],
        "note": (
            "This status inspects only fixed release contracts. It does not "
            "load invoice, PAYMNENT, credit-note or financial database records."
        ),
    }


@reconciliation_readiness.get("/api/payment-reconciliation/status")
def engine_status():
    # Authenticated even for read-only engine status; no external calls.
    return jsonify(**_base_response())


@reconciliation_readiness.post("/api/payment-reconciliation/preflight")
def reconciliation_preflight():
    """Validate ownership/integrity only. Never match or write invoices."""
    if not csrf_valid():
        return jsonify(error="Same-origin session CSRF check failed",
                       financial_writes=False), 403
    if request.content_length is None or request.content_length > 1024:
        return jsonify(error="Invalid preflight request size",
                       financial_writes=False), 413
    if not request.is_json:
        return jsonify(error="JSON receipt request required",
                       financial_writes=False), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"receipt_id"}:
        return jsonify(error="Only a payment receipt ID is accepted",
                       financial_writes=False), 422
    rid = data["receipt_id"]
    if not isinstance(rid, str) or not RECEIPT_RE.fullmatch(rid):
        return jsonify(error="Invalid payment receipt ID",
                       financial_writes=False), 422

    try:
        base = _store()
        with closing(_connection(base)) as conn:
            row = conn.execute(
                "SELECT * FROM receipts WHERE id=? AND owner_uid=?",
                (rid, str(g.dil_user.uid)),
            ).fetchone()
        if row is None:
            return jsonify(error="Payment evidence receipt not found",
                           financial_writes=False), 404
        if row["filename"] != rid + ".xlsx":
            return jsonify(error="Invalid receipt storage lineage",
                           financial_writes=False), 503
        evidence = base / row["filename"]
        if evidence.is_symlink() or not evidence.is_file():
            return jsonify(error="Staged evidence unavailable",
                           financial_writes=False), 503
        source = evidence.read_bytes()
        if hashlib.sha256(source).hexdigest() != row["sha256"]:
            return jsonify(error="Staged evidence integrity check failed",
                           financial_writes=False), 503
        parsed = _parse(source)
    except ValueError:
        return jsonify(error="Stored Excel evidence failed verification",
                       financial_writes=False), 503
    except (OSError, sqlite3.Error):
        return jsonify(error="Private evidence store is unavailable",
                       financial_writes=False), 503

    # The receipt's original summary is independently rechecked before
    # preflight; if it has changed, fail rather than updating ledger data.
    if (row["source_rows"] != parsed["source_rows"] or
        row["valid_rows"] != parsed["valid_rows"] or
        row["review_rows"] != parsed["review_rows"] or
        row["credit_total"] != parsed["valid_credit_total"]):
        return jsonify(error="Staged evidence receipt summary mismatch",
                       financial_writes=False), 503

    base_result = {
        **_base_response(),
        "receipt_id": rid,
        "evidence_sha256": row["sha256"],
        "evidence_verified": True,
        "source_rows": parsed["source_rows"],
        "review_rows": parsed["review_rows"],
        "valid_rows": parsed["valid_rows"],
        "valid_credit_total_unallocated": parsed["valid_credit_total"],
        "evidence_review_flags": parsed["review_flag_counts"],
    }
    if parsed["review_rows"]:
        return jsonify(
            **base_result,
            code="PAYMENT_EVIDENCE_REVIEW_REQUIRED",
            error="Resolve all flagged evidence rows before reconciliation.",
        ), 409
    return jsonify(
        **base_result,
        code="APPROVED_FINANCIAL_ENGINE_NOT_CONNECTED",
        error=(
            "Evidence verified, but the approved reconciliation engine, "
            "original bank/invoice source and financial writer are not connected. "
            "No reconciliation or database update was performed."
        ),
    ), 503
