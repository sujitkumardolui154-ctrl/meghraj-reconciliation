#!/usr/bin/env python3
"""Read-only private employee-access acceptance gate; NO DEPLOYMENT.

Supersedes a *proposed topology*, not existing R31.11.4S requirements.
No arbitrary N/A permissions, financial Apply, database changes or network calls.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GATE_FILE = HERE / "private_access_gate.json"
PUBLIC_EXTERNAL_MATRIX = (
    REPO / "staging/aws_login_v150/r31_11_4s_external_acceptance_matrix.json"
)
REQUIRED_GATES = [
    "P1_APPROVE_PRIVATE_ARCHITECTURE_AND_ROLLBACK",
    "P2_IDENTITY_MFA_DEVICES_AND_DENY_BY_DEFAULT",
    "P3_PRIVATE_HTTPS_SERVE_WITH_NO_FUNNEL",
    "P4_FIREBASE_ORIGIN_TWO_USER_AUTHZ_CSRF",
    "P5_RLS_REPORTS_BACKUPS_AND_FINANCE_PARITY",
    "P6_TWO_SITE_PRIVATE_E2E_AND_REVOCATION",
    "P7_PUBLIC_IPV4_IPV6_CUTOVER_ROLLBACK_RELEASE",
]


def load_json(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("PRIVATE_GATE_SOURCE_MISSING_OR_UNSAFE")
    return json.loads(path.read_text("utf-8"))


def verify(gate, old_matrix):
    if not isinstance(gate, dict) or (
        gate.get("schema") != "SBI-PRIVATE-MULTISITE-ACCESS-GATE-V1"
        or gate.get("classification") != "SOURCE_ONLY_NOT_DEPLOYED_OR_APPROVED"
        or gate.get("architecture") != "TAILSCALE_TAILNET_STAFF_ONLY_WITH_PRIVATE_HTTPS"
        or gate.get("domain_purchase_required") is not False
        or gate.get("https_transport") != "TAILSCALE_SERVE_PRIVATE_HTTPS_NO_FUNNEL"
        or gate.get("financial_apply") != "LOCKED"
        or gate.get("production_release") != "BLOCKED"
        or gate.get("actual_tailnet_deployed") is not False
        or gate.get("actual_employee_access_tests_completed") != 0
        or gate.get("public_ingress_closed_verified") is not False
        or gate.get("legacy_external_design_change_approved") is not False
    ):
        raise ValueError("PRIVATE_GATE_LOCK_OR_TOPOLOGY_CHANGED")
    gates = gate.get("gates")
    if (
        not isinstance(gates, list)
        or len(gates) != len(REQUIRED_GATES)
        or [x.get("id") for x in gates if type(x) is dict] != REQUIRED_GATES
        or any(x.get("status") != "PENDING" for x in gates)
        or any(not isinstance(x.get("evidence"), str) or not x["evidence"] for x in gates)
    ):
        raise ValueError("PRIVATE_GATES_WRONGLY_APPROVED_OR_MISSING")
    prior = gate.get("original_public_external_mtls") or {}
    cases = old_matrix.get("external_cases")
    if (
        prior.get("acceptance_tests_planned") != 22
        or prior.get("acceptance_tests_executed") != 0
        or prior.get("scope") != "STILL_NOT_TESTED_NO_AUTOMATIC_WAIVER"
        or not isinstance(cases, list)
        or len(cases) != 22
        or any(x.get("status") != "NOT_TESTED_EXTERNAL" for x in cases)
        or old_matrix.get("production_release") != "BLOCKED"
        or old_matrix.get("financial_apply") != "LOCKED"
    ):
        raise ValueError("PRIOR_22_EXTERNAL_CASES_FALSIFIED_OR_REMOVED")
    previous = gate.get("reused_evidence")
    if (
        not isinstance(previous, list)
        or len(previous) != 5
        or any(not isinstance(x, dict) or len(x.get("sha", "")) != 40
               or not x.get("scope") for x in previous)
    ):
        raise ValueError("QA_EVIDENCE_REGISTER_INVALID")
    return len(gates)


def main():
    count = verify(load_json(GATE_FILE), load_json(PUBLIC_EXTERNAL_MATRIX))
    print("SBI_PRIVATE_MULTISITE_SOURCE_POLICY=PASS")
    print("SBI_PRIVATE_DOMAIN_PURCHASE=NOT_REQUIRED")
    print("SBI_PRIVATE_PROPOSED_RELEASE_GATES=" + str(count))
    print("SBI_PRIVATE_APPROVED_GATES=0")
    print("SBI_PRIVATE_TAILNET=NOT_PROVISIONED")
    print("SBI_PRIVATE_HTTPS_AND_FIREBASE=NOT_LIVE_TESTED")
    print("SBI_PRIVATE_PUBLIC_IPV4_IPV6_SHUTDOWN=NOT_VERIFIED")
    print("SBI_PREVIOUS_EXTERNAL_MTLS=0_OF_22_EXECUTED_NOT_WAIVED")
    print("SBI_PRIVATE_ARCHITECTURE_CHANGE=REQUIRES_INDEPENDENT_APPROVAL")
    print("SBI_FINANCIAL_APPLY=LOCKED")
    print("SBI_PRODUCTION_RELEASE=BLOCKED")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            json.JSONDecodeError):
        print("STOP=SBI_PRIVATE_POLICY_OR_EVIDENCE_REVIEW_REQUIRED")
        print("SBI_FINANCIAL_APPLY=LOCKED")
        print("SBI_PRODUCTION_RELEASE=BLOCKED")
        raise SystemExit(2)
