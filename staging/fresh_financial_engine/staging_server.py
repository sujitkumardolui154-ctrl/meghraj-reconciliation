"""Isolated, read-only synthetic HTTP probe for NEW engine 21 11 2026.

Never accepts finance input. No bank data, files, ledger, credentials, SQL or
external connections. This is NOT an AWS production allocation endpoint.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from sbi_engine import evaluate

NAME = "NEW engine 21 11 2026"
NO_FINANCE = dict(
    engine=NAME,
    service="sbi-new-engine-synthetic-staging",
    mode="SYNTHETIC_ONLY",
    financial_execution_enabled=False,
    financial_writes=False,
    production_approved=False,
    historical_records_accessed=False,
    database_connected=False,
    apply_enabled=False,
)


def synthetic_smoke() -> dict:
    """Fixed fabricated fixture, not derived from any request or source file."""
    invoice = dict(
        source_kind="SYNTHETIC", invoice_no="SYNTH-INV-STAGE-001",
        sol_id="1505", client_name="SYNTHETIC CLIENT", sbisa=False,
        invoice_date="2026-11-21", service_months=["2026-11"],
        taxable="100.00", cgst="9.00", sgst="9.00", gross="118.00",
        approved_tds_rate=1, original_paid_marker=None,
        source_verified=True, master_verified=True, protected_prior=False,
        credit_note=False,
    )
    payment = dict(
        source_kind="SYNTHETIC", utr="SYNTH-UTR-STAGE-001",
        sol_id="1505", client_name="SYNTHETIC CLIENT", sbisa=False,
        bank_date="2026-11-22", description="SYNTH NOVEMBER 2026",
        credit="117.00", invoice_refs=["SYNTH-INV-STAGE-001"],
        source_verified=True, bank_reference_verified=True,
    )
    report = evaluate([invoice], [payment], activation_cutoff="2026-11-21",
                      synthetic_only=True)
    if (report["proposal_count"] != 1 or report["hold_count"] != 0
        or report["financial_writes"] is not False
        or report["production_approved"] is not False
        or report["historical_records_accessed"] is not False
        or report["actual_financial_status"] != "NOT_ASSIGNED"):
        raise RuntimeError("SYNTHETIC_INVARIANT_FAILURE")
    return {
        **NO_FINANCE,
        "synthetic_probe": "PASS",
        "proposal_count": report["proposal_count"],
        "hold_count": report["hold_count"],
        "actual_financial_status": report["actual_financial_status"],
    }




def stage3_mock_smoke() -> dict:
    """Fabricated intake -> dual review -> mock ledger, never real finance."""
    from d030_future_payment_provenance import evidence_row_sha256
    from d031_synthetic_receipt_register import MockPrincipal, MockServerPolicy, UPLOADER, REVIEWER
    from stage3_mock_bridge import Stage3MockBridge

    row = {"Description": "SYNTH-STAGE3 POSTAGE NOVEMBER 2026",
           "SOL ID": "1505", "Credit Amount": "117.00"}
    meta = {"source_kind": "SYNTHETIC", "excel_row": 2,
            "bank_date": "2026-11-23", "bank_reference": "SYNTH-UTR-STAGE3",
            "source_credit_column": "PAYMNENT!I", "source_credit_I": "117.00",
            "evidence_row_sha256": evidence_row_sha256(row)}
    context = {"source_kind": "SYNTHETIC", "bank_reference": "SYNTH-UTR-STAGE3",
               "client_name": "SYNTH BRANCH",
               "invoice_refs": ["SYNTH-INV-STAGE3"], "sbisa": False,
               "source_verified": True, "bank_reference_verified": True}
    invoice = {"source_kind": "SYNTHETIC", "invoice_no": "SYNTH-INV-STAGE3",
               "sol_id": "1505", "client_name": "SYNTH BRANCH", "sbisa": False,
               "invoice_date": "2026-11-21", "service_months": ["2026-11"],
               "taxable": "100.00", "cgst": "9.00", "sgst": "9.00",
               "gross": "118.00", "approved_tds_rate": 1,
               "original_paid_marker": None, "source_verified": True,
               "master_verified": True, "protected_prior": False, "credit_note": False}
    policy = MockServerPolicy(
        activation_date="2026-11-21", submission_date="2026-11-24",
        uploader_uid="SYNTH-USER-STAGE3-UP",
        reviewer_uid="SYNTH-USER-STAGE3-REVIEW")
    uploader = MockPrincipal(uid=policy.uploader_uid, role=UPLOADER)
    reviewer = MockPrincipal(uid=policy.reviewer_uid, role=REVIEWER)
    bridge = Stage3MockBridge(server_policy=policy)
    try:
        staged = bridge.stage([row], [meta], principal=uploader)
        if staged.get("mock_receipt_created") is not True:
            raise RuntimeError("SYNTH_STAGE3_MOCK_INTAKE_DENIED")
        reviewed = bridge.review(staged["receipt_id"], principal=reviewer)
        if reviewed.get("mock_review_completed") is not True:
            raise RuntimeError("SYNTH_STAGE3_REVIEW_DENIED")
        proposed = bridge.propose(staged["receipt_id"], [invoice],
                                  [context], principal=reviewer)
        counted = bridge.counts(principal=reviewer)
        if (proposed["status"] != "SYNTHETIC_PROPOSALS_RESERVED_FOR_REVIEW"
                or proposed["proposal_count"] != 1
                or counted["mock_candidate_edges"] != 1
                or proposed["financial_writes"] is not False
                or proposed["production_approved"] is not False):
            raise RuntimeError("SYNTH_STAGE3_CANDIDATE_INVARIANT_FAILURE")
        return {**NO_FINANCE, "stage3_probe": "PASS",
                "mock_receipt_registered": True, "mock_review_completed": True,
                "mock_candidate_ledger_edges": counted["mock_candidate_edges"],
                "mock_ledger_persistent": False,
                "actual_financial_status": "NOT_ASSIGNED"}
    finally:
        bridge.close()

class SyntheticHandler(BaseHTTPRequestHandler):
    server_version = "SBI-Synthetic-Stage"
    sys_version = ""

    def log_message(self, format: str, *args) -> None:
        # Never log untrusted URL paths/headers from unexpected requests.
        return

    def _send(self, code: int, payload: dict) -> None:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            return self._send(200, {**NO_FINANCE, "status": "synthetic_alive"})
        if self.path == "/readyz":
            return self._send(200, {**NO_FINANCE, "ready_for": "synthetic_staging_only"})
        if self.path == "/api/synthetic-demo":
            try:
                result = synthetic_smoke()
            except Exception:
                return self._send(503, {**NO_FINANCE, "error": "SYNTHETIC_ENGINE_UNAVAILABLE"})
            return self._send(200, result)
        if self.path == "/api/stage3/synthetic-bridge":
            try:
                result = stage3_mock_smoke()
            except Exception:
                return self._send(503, {**NO_FINANCE, "error": "STAGE3_SYNTHETIC_BRIDGE_UNAVAILABLE"})
            return self._send(200, result)
        return self._send(404, {**NO_FINANCE, "error": "ROUTE_NOT_AVAILABLE"})

    def _deny_write(self) -> None:
        # Do not parse/read request bodies; no arbitrary financial records enter.
        self.close_connection = True
        self._send(403, {**NO_FINANCE, "error": "FINANCIAL_APPLY_LOCKED"})

    do_POST = _deny_write
    do_PUT = _deny_write
    do_PATCH = _deny_write
    do_DELETE = _deny_write


def main() -> None:
    port = int(os.getenv("SBI_SYNTHETIC_STAGE_PORT", "8080"))
    if not (1024 <= port <= 65535):
        raise SystemExit("STAGING_PORT_INVALID")
    with HTTPServer(("0.0.0.0", port), SyntheticHandler) as server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()