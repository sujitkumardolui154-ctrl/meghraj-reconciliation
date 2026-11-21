"""Stage 3 mock intake-to-proposal bridge for NEW engine 21 11 2026.

Only SYNTHETIC fixture evidence. Reuses existing D-030 source/sidecar checks,
D-031 role-separated in-memory receipt register and the fresh v2.51 proposal
engine. The second SQLite :memory: register below tracks *mock candidate*
reservations, NOT financial postings, paid markers or a persistent ledger.

No IO paths, bank APIs, database DSNs, external identities, historical files,
HTTP financial routes or live finance writer are available in this module.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import sqlite3
import threading

from d030_future_payment_provenance import evidence_row_sha256
from d031_synthetic_receipt_register import (
    MockPrincipal, MockServerPolicy, REVIEWER, SyntheticOnlyReceiptRegister,
)
from sbi_engine import evaluate


class Stage3MockBlocked(ValueError):
    """A mock rule or source boundary failed; no proposal is committed."""


def _deny(code: str) -> None:
    raise Stage3MockBlocked(code)


# This context is FAKE test-harness evidence outside the existing three-column
# upload format; no production bank or SBI source trust can be inferred from it.
CONTEXT_KEYS = frozenset({
    "source_kind", "bank_reference", "client_name", "invoice_refs",
    "sbisa", "source_verified", "bank_reference_verified",
})


class Stage3MockBridge:
    def __init__(self, *, server_policy: MockServerPolicy):
        if not isinstance(server_policy, MockServerPolicy) or server_policy.synthetic_mode is not True:
            _deny("SYNTHETIC_MOCK_SERVER_POLICY_REQUIRED")
        self._policy = server_policy
        self._register = SyntheticOnlyReceiptRegister(server_policy=server_policy)
        self._lock = threading.RLock()
        self._batches: dict[str, tuple[list[dict], list[dict]]] = {}
        self._reviewed: set[str] = set()
        # Isolated volatile candidate ledger. This does NOT meet production
        # durability, bank authority, authentication or rollback requirements.
        self._db = sqlite3.connect(":memory:", isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("CREATE TABLE mock_applied_batches (receipt_id TEXT PRIMARY KEY)")
        self._db.execute("CREATE TABLE mock_invoice_capacity ("
                         "invoice_no TEXT PRIMARY KEY, capacity TEXT NOT NULL, "
                         "reserved TEXT NOT NULL)")
        self._db.execute("CREATE TABLE mock_candidates ("
                         "receipt_id TEXT NOT NULL, payment_id TEXT NOT NULL, "
                         "invoice_no TEXT NOT NULL, amount TEXT NOT NULL, "
                         "PRIMARY KEY(receipt_id,payment_id,invoice_no))")

    def close(self) -> None:
        with self._lock:
            self._register.close()
            self._db.close()

    def stage(self, rows: list[dict], sidecar: list[dict], *,
              principal: MockPrincipal) -> dict:
        """Copy mock source after D-031 atomic batch/UTR attestation."""
        with self._lock:
            receipt = self._register.stage_mock_evidence(rows, sidecar, principal=principal)
            if receipt.get("mock_receipt_created") is True:
                receipt_id = receipt["receipt_id"]
                self._batches[receipt_id] = (deepcopy(rows), deepcopy(sidecar))
            return receipt

    def review(self, receipt_id: str, *, principal: MockPrincipal) -> dict:
        with self._lock:
            result = self._register.review_mock_receipt(receipt_id, principal=principal)
            if result.get("mock_review_completed") is True and receipt_id in self._batches:
                self._reviewed.add(receipt_id)
            return result

    def _mock_payments(self, rows: list[dict], sidecar: list[dict],
                       context: list[dict]) -> list[dict]:
        if type(context) is not list or len(context) != len(rows):
            _deny("ONE_INDEPENDENT_MOCK_CONTEXT_PER_ROW_REQUIRED")
        mapped = []
        for row, meta, extra in zip(rows, sidecar, context):
            if type(extra) is not dict or set(extra) != CONTEXT_KEYS:
                _deny("MOCK_PAYMENT_CONTEXT_SCHEMA_INVALID")
            if extra["source_kind"] != "SYNTHETIC":
                _deny("REAL_CLIENT_OR_BANK_CONTEXT_FORBIDDEN")
            if extra["bank_reference"] != meta["bank_reference"]:
                _deny("UTR_SIDECAR_CONTEXT_CONFLICT")
            if not (type(extra["client_name"]) is str
                    and extra["client_name"].startswith("SYNTH ")):
                _deny("NONFABRICATED_CLIENT_CONTEXT_FORBIDDEN")
            if (type(extra["sbisa"]) is not bool
                or type(extra["source_verified"]) is not bool
                or type(extra["bank_reference_verified"]) is not bool
                or type(extra["invoice_refs"]) is not list):
                _deny("MOCK_CONTEXT_TYPES_INVALID")
            # Rehash pinned copies before converting row data, so an external
            # object changing after stage cannot replace source evidence.
            if evidence_row_sha256(row) != meta["evidence_row_sha256"]:
                _deny("PINNED_SOURCE_DIGEST_MISMATCH")
            mapped.append({
                "source_kind": "SYNTHETIC",
                "utr": meta["bank_reference"],
                "sol_id": row["SOL ID"],
                "client_name": extra["client_name"],
                "bank_date": meta["bank_date"],
                "description": row["Description"],
                "credit": row["Credit Amount"],
                "invoice_refs": deepcopy(extra["invoice_refs"]),
                "sbisa": extra["sbisa"],
                "source_verified": extra["source_verified"],
                "bank_reference_verified": extra["bank_reference_verified"],
            })
        return mapped

    def propose(self, receipt_id: str, invoices: list[dict],
                payment_context: list[dict], *, principal: MockPrincipal) -> dict:
        """Reserve ONLY synthetic proposals in a volatile transaction.

        A second reviewed batch can never reserve beyond the same synthetic
        invoice capacity. All held payments block the entire mock batch.
        The caller cannot provide a replacement bank date, UTR or credit here.
        """
        if not isinstance(principal, MockPrincipal) or (principal.uid != self._policy.reviewer_uid
                or principal.role != REVIEWER):
            _deny("MOCK_REVIEWER_REQUIRED")
        with self._lock:
            if receipt_id not in self._reviewed or receipt_id not in self._batches:
                _deny("MOCK_RECEIPT_NOT_REVIEWED")
            if type(invoices) is not list or any(
                    type(i) is not dict or i.get("source_kind") != "SYNTHETIC"
                    or type(i.get("client_name")) is not str
                    or not i["client_name"].startswith("SYNTH ") for i in invoices):
                _deny("ONLY_FABRICATED_INVOICES_ALLOWED")
            rows, sidecar = self._batches[receipt_id]
            payments = self._mock_payments(rows, sidecar, payment_context)
            report = evaluate(deepcopy(invoices), payments,
                              activation_cutoff=self._policy.activation_date,
                              synthetic_only=True)
            if report["holds"] or not report["proposals"]:
                return self._result("MOCK_BATCH_HELD_NO_CANDIDATE_LEDGER_UPDATE", report)

            # Reconcile mock proposed edges with the exact three-column credit.
            # A legitimate split is allowed; no over-credit or amount creation.
            credit = {p["utr"]: Decimal(p["credit"]) for p in payments}
            edges_by_pay = defaultdict(lambda: Decimal("0.00"))
            edges_by_invoice = defaultdict(lambda: Decimal("0.00"))
            for e in report["proposals"]:
                val = Decimal(e["candidate_credit"])
                if val <= 0:
                    _deny("MOCK_NONPOSITIVE_CANDIDATE")
                edges_by_pay[e["payment_id"]] += val
                edges_by_invoice[e["invoice_no"]] += val
            if any(edges_by_pay.get(k, Decimal("0")) != v for k, v in credit.items()):
                _deny("MOCK_PAYMENT_CREDIT_NOT_CONSERVED")
            capacity = {invoice_id: Decimal(rem) + edges_by_invoice[invoice_id]
                        for invoice_id, rem in report["remaining_net"].items()}
            try:
                self._db.execute("BEGIN IMMEDIATE")
                existing = self._db.execute(
                    "SELECT 1 FROM mock_applied_batches WHERE receipt_id=?", (receipt_id,)
                ).fetchone()
                if existing:
                    self._db.execute("ROLLBACK")
                    return self._result("MOCK_PROPOSAL_BATCH_ALREADY_RESERVED", report)
                for invoice_no, requested in edges_by_invoice.items():
                    prior = self._db.execute(
                        "SELECT capacity,reserved FROM mock_invoice_capacity WHERE invoice_no=?",
                        (invoice_no,)
                    ).fetchone()
                    limit = capacity[invoice_no]
                    if prior is not None:
                        if Decimal(prior[0]) != limit:
                            self._db.execute("ROLLBACK")
                            return self._result("MOCK_INVOICE_SOURCE_CONFLICT_HELD", report)
                        if Decimal(prior[1]) + requested > limit:
                            self._db.execute("ROLLBACK")
                            return self._result("MOCK_GLOBAL_OVERALLOCATION_HELD", report)
                    else:
                        if requested > limit:
                            self._db.execute("ROLLBACK")
                            return self._result("MOCK_GLOBAL_OVERALLOCATION_HELD", report)
                for invoice_no, requested in edges_by_invoice.items():
                    prior = self._db.execute(
                        "SELECT reserved FROM mock_invoice_capacity WHERE invoice_no=?",
                        (invoice_no,)
                    ).fetchone()
                    if prior is None:
                        self._db.execute("INSERT INTO mock_invoice_capacity VALUES (?,?,?)",
                                         (invoice_no, str(capacity[invoice_no]), str(requested)))
                    else:
                        new_total = Decimal(prior[0]) + requested
                        self._db.execute("UPDATE mock_invoice_capacity SET reserved=? "
                                         "WHERE invoice_no=?", (str(new_total), invoice_no))
                self._db.execute("INSERT INTO mock_applied_batches VALUES (?)", (receipt_id,))
                self._db.executemany(
                    "INSERT INTO mock_candidates VALUES (?,?,?,?)",
                    [(receipt_id, e["payment_id"], e["invoice_no"], e["candidate_credit"])
                     for e in report["proposals"]]
                )
                self._db.execute("COMMIT")
            except (sqlite3.DatabaseError, ValueError) as exc:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise Stage3MockBlocked("MOCK_TRANSACTION_ROLLED_BACK") from exc
            return self._result("SYNTHETIC_PROPOSALS_RESERVED_FOR_REVIEW", report)

    def counts(self, *, principal: MockPrincipal) -> dict:
        if not isinstance(principal, MockPrincipal) or (principal.uid != self._policy.reviewer_uid
                or principal.role != REVIEWER):
            _deny("MOCK_REVIEWER_REQUIRED")
        with self._lock:
            return {
                "mock_receipts_with_proposals": self._db.execute(
                    "SELECT COUNT(*) FROM mock_applied_batches").fetchone()[0],
                "mock_candidate_edges": self._db.execute(
                    "SELECT COUNT(*) FROM mock_candidates").fetchone()[0],
                "financial_writes": False,
                "persistent_ledger": False,
                "historical_records_accessed": False,
                "production_approved": False,
            }

    @staticmethod
    def _result(status: str, report: dict) -> dict:
        return {
            "status": status,
            "proposal_count": report["proposal_count"],
            "hold_count": report["hold_count"],
            "holds": report["holds"],
            "proposals": report["proposals"],
            "mode": "SYNTHETIC_ONLY_NO_FINANCIAL_SETTLEMENT",
            "mock_ledger_only": True,
            "persistent_ledger": False,
            "real_bank_provenance_verified": False,
            "financial_writes": False,
            "database_connected": False,
            "historical_records_accessed": False,
            "production_approved": False,
            "actual_financial_status": "NOT_ASSIGNED",
        }