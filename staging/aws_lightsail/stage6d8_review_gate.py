#!/usr/bin/env python3
"""Stage 6D.8 consolidated offline independent-review intake and approval gate.

Never performs credential creation, network access, Google IAM, AWS or Firebase calls.
PASS means the proposal was validated, NOT that a provider or login is approved.
"""
import argparse
import json
from pathlib import Path

PLAN = "staging/aws_lightsail/stage6d7_x509_identity_plan.json"
REQUIRED_PENDING = (
    "owner_certificate_custody",
    "owner_iam_x509_provider",
    "independent_security_review",
    "least_privilege_permission_review",
    "firebase_admin_identity_parity",
    "cost_acceptance",
)
def assess(plan):
    p = plan["planned_provider"]
    identity = plan["credentials"]
    iam = plan["permissions"]
    costs = plan["costs"]
    approvals = plan["approvals"]
    checks = {
        "EXISTING_LIGHTSAIL_ONLY": plan["approved_destination"] == "EXISTING_LIGHTSAIL" and plan["estimated_new_aws_instances"] == 0,
        "PROPOSAL_STILL_INERT": plan["state"] == "PROPOSAL_ONLY_NO_EXECUTION" and p["state"] == "NOT_CREATED",
        "EXACT_SPIFFE_SUBJECT": p["attribute_mapping"] == "google.subject=assertion.san.uri" and p["attribute_condition"] == "assertion.san.uri == '" + p["subject"] + "'" and p["principal_scope"] == "EXACT_SUBJECT_ONLY",
        "NO_UNTRUSTED_CA": p["trust_anchor"] == "NOT_SELECTED" and identity["ca_private_key_location"] == "NOT_SELECTED_MUST_REMAIN_OFF_APPLICATION_HOST",
        "NO_PRIVATE_KEYS_GENERATED": identity["client_private_key"] == "NOT_CREATED" and identity["google_service_account_private_key_json"] == "PROHIBITED",
        "NO_EXISTING_WIF_CHANGES": p["existing_aws_provider"] == "UNCHANGED_DISABLED",
        "NO_IAM_GRANTS": iam["iam_grants"] == "NONE_CREATED" and iam["service_account"] == "NOT_SELECTED",
        "NO_FINANCE_OR_USER_WRITES": iam["firestore_write"] == "DENIED" and iam["financial_backend_access"] == "DENIED" and iam["firebase_user_mutations"] == "DISABLED" and plan["financial_database"] == "NOT_CONNECTED",
        "UNKNOWN_CA_COST_NOT_ASSUMED_FREE": costs["managed_ca"] == "NOT_APPROVED" and costs["ca_ops_and_certificate_custody"] == "COST_UNQUANTIFIED",
        "APPROVALS_NOT_PRETENDED": all(approvals.get(k) == "PENDING" for k in REQUIRED_PENDING),
        "REAL_LOGIN_NOT_CLAIMED": plan["real_firebase_login"] == "NOT_TESTED",
        "PRODUCTION_NOT_AUTHORIZED": plan["production_cutover"] == "BLOCKED",
    }
    blockers = [
        "CA_CUSTODY_AND_ROOT_KEY_OFF_HOST_UNDECIDED",
        "LEAF_KEY_AT_REST_ROTATION_REVOCATION_UNREVIEWED",
        "CERT_ISSUANCE_SCOPE_SAN_AND_CA_TRUST_UNAPPROVED",
        "GOOGLE_IAM_SERVICE_ACCOUNT_LEAST_PRIVILEGE_UNDEFINED",
        "FIREBASE_ADMIN_READ_SESSION_AND_REVOKE_PARITY_UNVERIFIED",
        "COSTS_AND_OWNER_CHANGE_APPROVAL_PENDING",
        "INDEPENDENT_SECURITY_SIGNOFF_MISSING",
    ]
    return checks, blockers

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    path = (root / PLAN).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        print("BATCH_QA=BLOCKED")
        print("NEXT_GATE=REVIEW_MISSING_APPROVAL_PLAN")
        return 2
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
        checks, blockers = assess(plan)
    except (KeyError, TypeError, ValueError, OSError, UnicodeError):
        print("BATCH_QA=FAIL")
        print("NEXT_GATE=REPAIR_MALFORMED_APPROVAL_PLAN")
        return 1
    for name, ok in sorted(checks.items()):
        print(f"{name}={'PASS' if ok else 'FAIL'}")
    validated = all(checks.values())
    print("BATCH_QA=" + ("PASS" if validated else "FAIL"))
    print("CURRENT_STAGE=6D.8_OFFLINE_APPROVAL_READINESS")
    for blocker in blockers:
        print("PENDING_REVIEW=" + blocker)
    print("IDENTITY_PROVISIONING=NOT_PERFORMED")
    print("REAL_FIREBASE_LOGIN=NOT_TESTED")
    print("FINANCIAL_DATABASE=NOT_CONNECTED")
    print("PRODUCTION_CUTOVER=BLOCKED")
    print("NEXT_GATE=" + ("INDEPENDENT_SECURITY_REVIEW_AND_SPECIFIC_OWNER_APPROVAL" if validated else "FIX_UNSAFE_APPROVAL_PLAN"))
    return 0 if validated else 1

if __name__ == "__main__":
    raise SystemExit(main())
