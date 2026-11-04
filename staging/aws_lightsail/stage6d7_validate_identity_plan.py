#!/usr/bin/env python3
"""Stage 6D.7: fail-closed, offline certificate-identity plan validator.

No provider, IAM, key, certificate, Firebase, AWS or finance operations.
A PASS proves the proposal is conservatively bounded; it does NOT authorize apply.
"""
import argparse
import json
from pathlib import Path

PLAN = "staging/aws_lightsail/stage6d7_x509_identity_plan.json"
APPROVAL_FIELDS = (
    "owner_certificate_custody",
    "owner_iam_x509_provider",
    "independent_security_review",
    "least_privilege_permission_review",
    "firebase_admin_identity_parity",
    "cost_acceptance",
)
def review(plan):
    p = plan["planned_provider"]
    c = plan["credentials"]
    perms = plan["permissions"]
    approvals = plan["approvals"]
    costs = plan["costs"]
    checks = {
        "LIGHTSAIL_ONLY": plan["approved_destination"] == "EXISTING_LIGHTSAIL" and plan["estimated_new_aws_instances"] == 0,
        "NO_LIVE_SERVICE_MUTATION": plan["existing_cloud_run"] == "PROTECTED_UNCHANGED" and plan["existing_lightsail_services"] == "PROTECTED_UNCHANGED",
        "PROPOSAL_ONLY": plan["state"] == "PROPOSAL_ONLY_NO_EXECUTION",
        "SEPARATE_X509_PROVIDER": p["type"] == "X509" and p["state"] == "NOT_CREATED" and p["existing_aws_provider"] == "UNCHANGED_DISABLED" and p["pool"] != "sbi-aws-migration-pool",
        "EXACT_CLIENT_IDENTITY": p["principal_scope"] == "EXACT_SUBJECT_ONLY" and p["attribute_mapping"] == "google.subject=assertion.san.uri" and p["subject"].startswith("spiffe://") and p["attribute_condition"] == "assertion.san.uri == '" + p["subject"] + "'",
        "NO_UNKNOWN_CA_TRUST": p["trust_anchor"] == "NOT_SELECTED" and c["ca_private_key_location"] == "NOT_SELECTED_MUST_REMAIN_OFF_APPLICATION_HOST",
        "NO_CREDENTIAL_ISSUANCE": c["google_service_account_private_key_json"] == "PROHIBITED" and c["client_certificate"] == "NOT_CREATED" and c["client_private_key"] == "NOT_CREATED" and c["workload_credential_config"] == "NOT_CREATED",
        "ROTATION_AND_REVOCATION_PENDING": 1 <= c["client_certificate_validity_days_proposed"] <= 90 and c["certificate_rotation_plan"] == "PENDING_REVIEW" and c["revocation_and_compromise_playbook"] == "PENDING_REVIEW",
        "REAL_FIREBASE_NOT_CLAIMED": c["firebase_admin_external_account_support"] == "UNVERIFIED" and c["firebase_admin_session_minting"] == "NOT_TESTED" and c["firebase_admin_revocation"] == "NOT_TESTED" and plan["real_firebase_login"] == "NOT_TESTED",
        "NO_IAM_GRANTS": perms["iam_grants"] == "NONE_CREATED" and perms["service_account"] == "NOT_SELECTED",
        "NO_FINANCIAL_ACCESS": perms["firebase_user_mutations"] == "DISABLED" and perms["firestore_write"] == "DENIED" and perms["financial_backend_access"] == "DENIED" and plan["financial_database"] == "NOT_CONNECTED",
        "NO_PRODUCTION_CUTOVER": perms["production_traffic"] == "UNCHANGED" and plan["production_cutover"] == "BLOCKED",
        "NO_NEW_PAID_PROVIDER": costs["additional_aws_hosting"] == "NONE_PROPOSED" and costs["managed_ca"] == "NOT_APPROVED" and costs["ca_ops_and_certificate_custody"] == "COST_UNQUANTIFIED",
        "APPROVALS_ALL_PENDING": all(approvals.get(key) == "PENDING" for key in APPROVAL_FIELDS),
    }
    return checks

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    root=Path(args.repo).resolve()
    path=(root / PLAN).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        print("BATCH_QA=BLOCKED")
        print("NEXT_GATE=REVIEW_MISSING_IDENTITY_PLAN")
        return 2
    try:
        plan=json.loads(path.read_text(encoding="utf-8"))
        checks=review(plan)
    except (KeyError, TypeError, ValueError, UnicodeError, OSError):
        print("BATCH_QA=FAIL")
        print("NEXT_GATE=REVIEW_MALFORMED_IDENTITY_PLAN")
        return 1
    for name, ok in sorted(checks.items()):
        print(name + "=" + ("PASS" if ok else "FAIL"))
    result = "PASS" if all(checks.values()) else "FAIL"
    print("BATCH_QA="+result)
    print("IDENTITY_PROVIDER_CREATION=NOT_PERFORMED")
    print("IAM_CHANGE=NOT_PERFORMED")
    print("FIREBASE_REAL_LOGIN=NOT_TESTED")
    print("FINANCIAL_DATABASE=NOT_CONNECTED")
    print("PRODUCTION_DEPLOYMENT=BLOCKED")
    print("NEXT_GATE=" + ("INDEPENDENT_SECURITY_AND_OWNER_APPROVAL_REQUIRED" if result=="PASS" else "REVISE_UNSAFE_IDENTITY_PROPOSAL"))
    return 0 if result=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
