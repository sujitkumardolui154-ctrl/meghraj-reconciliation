"""D-031 synthetic-only server-policy boundary and atomic mock receipt register.

No Flask route, real Firebase identity, bank integration, filesystem, AWS service,
financial ledger, historical read or production writer. This module uses only an
ephemeral SQLite ':memory:' register containing MOCK digests/receipt metadata.
It is a regression model, NOT durable storage or bank-verified provenance.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3
import threading

from d030_future_payment_provenance import (
    FutureEvidenceBlocked, _date, preview_future_evidence,
)

_UID = re.compile(r"SYNTH-USER-[A-Z0-9_-]{1,60}\Z")
_RECEIPT = re.compile(r"SYNTH-RCPT-[A-F0-9]{24}\Z")
UPLOADER = "SYNTHETIC_EVIDENCE_UPLOADER"
REVIEWER = "SYNTHETIC_EVIDENCE_REVIEWER"


class SyntheticRegistryBlocked(ValueError):
    pass


@dataclass(frozen=True)
class MockServerPolicy:
    """Provided by an isolated test harness, never trusted from an HTTP form."""
    activation_date: str
    submission_date: str
    uploader_uid: str
    reviewer_uid: str
    synthetic_mode: bool = True


@dataclass(frozen=True)
class MockPrincipal:
    uid: str
    role: str


def _deny(reason):
    raise SyntheticRegistryBlocked(reason)


def _guard_principal(principal, uid, role):
    if not isinstance(principal, MockPrincipal):
        _deny("MOCK_PRINCIPAL_REQUIRED")
    if principal.uid != uid or principal.role != role:
        _deny("MOCK_ROLE_OR_ACTOR_DENIED")


def _blocked_preview(source_rows, reasons):
    return {
        "status": "HELD_NO_MOCK_RECEIPT",
        "source_rows": source_rows,
        "holds": reasons,
        "mock_receipt_created": False,
        "mock_reference_registered": False,
        "mock_review_completed": False,
        "financial_writes": False,
        "financial_reconciliation_executed": False,
        "historical_financial_records_accessed": False,
        "real_bank_authority_verified": False,
        "live_financial_unlock_allowed": False,
    }


class SyntheticOnlyReceiptRegister:
    """Single-process fake receipt register with transactional unique mock UTR.

    The cutoff and mock actor constraints are captured in server-owned TEST
    state, not accepted from each pretend upload. That does not create actual
    authorization or a trusted banking cutover.
    """

    def __init__(self, *, server_policy):
        if not isinstance(server_policy, MockServerPolicy):
            _deny("MOCK_SERVER_POLICY_REQUIRED")
        if server_policy.synthetic_mode is not True:
            _deny("SYNTHETIC_MODE_REQUIRED")
        if not (_UID.fullmatch(server_policy.uploader_uid or "")
                and _UID.fullmatch(server_policy.reviewer_uid or "")):
            _deny("ONLY_FAKE_ACTOR_IDS_ALLOWED")
        if server_policy.uploader_uid == server_policy.reviewer_uid:
            _deny("DUAL_CONTROL_DISTINCT_USERS_REQUIRED")
        activation = _date(server_policy.activation_date)
        submission = _date(server_policy.submission_date)
        if submission < activation:
            _deny("MOCK_SUBMISSION_BEFORE_ACTIVATION")
        self.__policy = server_policy
        self.__lock = threading.RLock()
        # Never accept caller path/DSN: no persistent data, mounted volumes,
        # financial connection strings, or preexisting allocations.
        self.__db = sqlite3.connect(":memory:", isolation_level=None,
                                    check_same_thread=False)
        self.__db.execute("PRAGMA foreign_keys=ON")
        self.__db.execute(
            "CREATE TABLE mock_receipts("
            "receipt_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL UNIQUE,"
            "uploader_uid TEXT NOT NULL, status TEXT NOT NULL,"
            "row_count INTEGER NOT NULL, reviewer_uid TEXT)"
        )
        self.__db.execute(
            "CREATE TABLE mock_references("
            "reference_sha256 TEXT PRIMARY KEY, receipt_id TEXT NOT NULL,"
            "FOREIGN KEY(receipt_id) REFERENCES mock_receipts(receipt_id))"
        )

    def close(self):
        with self.__lock:
            self.__db.close()

    @staticmethod
    def _receipt_response(receipt_id, status, row_count, *,
                          created, duplicate=False, reviewed=False):
        return {
            "receipt_id": receipt_id,
            "status": status,
            "source_rows": row_count,
            "mock_receipt_created": bool(created),
            "mock_reference_registered": bool(created),
            "mock_review_completed": bool(reviewed),
            "idempotent_replay": bool(duplicate),
            "mode": "SYNTHETIC_IN_MEMORY_ONLY",
            "bank_date_verified_against_original_statement": False,
            "mock_cutoff_is_production_cutoff": False,
            "real_bank_authority_verified": False,
            "actual_user_authenticated": False,
            "persistent_receipt_written": False,
            "financial_reconciliation_executed": False,
            "historical_financial_records_accessed": False,
            "invoice_or_payment_database_accessed": False,
            "financial_writes": False,
            "live_financial_unlock_allowed": False,
        }

    def stage_mock_evidence(self, rows, sidecar, *, principal):
        _guard_principal(principal, self.__policy.uploader_uid, UPLOADER)
        if not isinstance(rows, list) or not isinstance(sidecar, list):
            _deny("MOCK_SOURCE_AND_SIDECAR_REQUIRED")
        # D-030 validates the exact existing 3-column contract, mock bank
        # dates and fake UTRs. No HTTP fields override mock server policy.
        preview = preview_future_evidence(
            rows, sidecar, synthetic_mode=True,
            mock_activation_date=self.__policy.activation_date,
            mock_submission_date=self.__policy.submission_date,
        )
        if preview["held_row_count"]:
            return _blocked_preview(len(rows), preview["holds"])
        canonical = json.dumps(
            {"rows": rows, "sidecar": sidecar, "schema": "D031_MOCK_V1"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()
        batch_sha = hashlib.sha256(canonical).hexdigest()
        receipt_id = "SYNTH-RCPT-" + batch_sha[:24].upper()
        references = [item["bank_reference_sha256"] for item in preview["preview"]]
        with self.__lock:
            try:
                self.__db.execute("BEGIN IMMEDIATE")
                old = self.__db.execute(
                    "SELECT receipt_id, status, row_count FROM mock_receipts "
                    "WHERE batch_sha256=?", (batch_sha,),
                ).fetchone()
                if old:
                    self.__db.execute("ROLLBACK")
                    return self._receipt_response(
                        old[0], "DUPLICATE_MOCK_BATCH_ALREADY_REGISTERED",
                        old[2], created=False, duplicate=True,
                        reviewed=old[1] == "SYNTHETIC_REVIEWED",
                    )
                for ref in references:
                    existing = self.__db.execute(
                        "SELECT 1 FROM mock_references "
                        "WHERE reference_sha256=?", (ref,),
                    ).fetchone()
                    if existing:
                        self.__db.execute("ROLLBACK")
                        return _blocked_preview(len(rows), [{
                            "reason": "MOCK_UTR_ALREADY_REGISTERED"
                        }])
                self.__db.execute(
                    "INSERT INTO mock_receipts "
                    "(receipt_id,batch_sha256,uploader_uid,status,row_count,"
                    "reviewer_uid) VALUES (?,?,?,?,?,NULL)",
                    (receipt_id, batch_sha, principal.uid,
                     "SYNTHETIC_PENDING_REVIEW", len(rows)),
                )
                self.__db.executemany(
                    "INSERT INTO mock_references "
                    "(reference_sha256,receipt_id) VALUES (?,?)",
                    [(ref, receipt_id) for ref in references],
                )
                self.__db.execute("COMMIT")
            except (sqlite3.DatabaseError, sqlite3.IntegrityError):
                if self.__db.in_transaction:
                    self.__db.execute("ROLLBACK")
                _deny("MOCK_TRANSACTION_REJECTED")
        return self._receipt_response(
            receipt_id, "SYNTHETIC_PENDING_REVIEW", len(rows), created=True,
        )

    def review_mock_receipt(self, receipt_id, *, principal):
        _guard_principal(principal, self.__policy.reviewer_uid, REVIEWER)
        if not isinstance(receipt_id, str) or not _RECEIPT.fullmatch(receipt_id):
            _deny("MOCK_RECEIPT_ID_INVALID")
        with self.__lock:
            try:
                self.__db.execute("BEGIN IMMEDIATE")
                row = self.__db.execute(
                    "SELECT status, row_count, uploader_uid FROM mock_receipts "
                    "WHERE receipt_id=?", (receipt_id,),
                ).fetchone()
                if row is None:
                    self.__db.execute("ROLLBACK")
                    _deny("MOCK_RECEIPT_NOT_FOUND")
                if row[2] == principal.uid:
                    self.__db.execute("ROLLBACK")
                    _deny("SELF_REVIEW_FORBIDDEN")
                if row[0] != "SYNTHETIC_PENDING_REVIEW":
                    self.__db.execute("ROLLBACK")
                    _deny("MOCK_REVIEW_STATE_INVALID")
                self.__db.execute(
                    "UPDATE mock_receipts SET status='SYNTHETIC_REVIEWED',"
                    " reviewer_uid=? WHERE receipt_id=? "
                    "AND status='SYNTHETIC_PENDING_REVIEW'",
                    (principal.uid, receipt_id),
                )
                self.__db.execute("COMMIT")
            except sqlite3.DatabaseError:
                if self.__db.in_transaction:
                    self.__db.execute("ROLLBACK")
                _deny("MOCK_REVIEW_TRANSACTION_REJECTED")
        # This is a review exercise, NOT a financial allocation approval.
        return self._receipt_response(
            receipt_id, "SYNTHETIC_REVIEWED_NO_ALLOCATION", row[1],
            created=False, reviewed=True,
        )

    def mock_counts(self, *, principal):
        _guard_principal(principal, self.__policy.reviewer_uid, REVIEWER)
        with self.__lock:
            receipts = self.__db.execute(
                "SELECT COUNT(*) FROM mock_receipts").fetchone()[0]
            refs = self.__db.execute(
                "SELECT COUNT(*) FROM mock_references").fetchone()[0]
        return {
            "mock_receipts": receipts, "mock_reference_hashes": refs,
            "persistent_receipts": False, "real_bank_data_accessed": False,
            "historical_records_accessed": False,
            "financial_writes": False, "production_unlock_allowed": False,
        }
