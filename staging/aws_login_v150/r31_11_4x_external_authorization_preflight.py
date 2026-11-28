#!/usr/bin/env python3
"""R31.11.4X read-only authorization preflight for external QA.

Reads existing approved-source records, never edits or grants approvals.
Does not contact AWS/DNS/HTTPS, read certificates, or run older QA suites.
"""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
FILES={
    "K":"r31_11_4k_external_mtls_approval_packet.json",
    "N":"r31_11_4n_dns_pki_evidence_intake.json",
    "O":"r31_11_4o_domain_ownership_dossier.json",
    "P":"r31_11_4p_pki_trust_lifecycle_plan.json",
    "Q":"r31_11_4q_ingress_isolation_policy.json",
    "R":"r31_11_4r_deployment_gate.json",
    "S":"r31_11_4s_external_acceptance_matrix.json",
}
SCHEMAS={
    "K":"DB-R31.11.4K-EXTERNAL-MTLS-APPROVAL-PACKET-V1",
    "N":"DB-R31.11.4N-DNS-PKI-EVIDENCE-INTAKE-V1",
    "O":"DB-R31.11.4O-DOMAIN-OWNERSHIP-EVIDENCE-V1",
    "P":"DB-R31.11.4P-PKI-TRUST-LIFECYCLE-V1",
    "Q":"DB-R31.11.4Q-QA-INGRESS-ISOLATION-V1",
    "R":"DB-R31.11.4R-ISOLATED-QA-DEPLOYMENT-GATE-V1",
    "S":"DB-R31.11.4S-REAL-EXTERNAL-MTLS-ACCEPTANCE-V1",
}

def require(ok):
    if not ok:
        raise ValueError("REVIEW_REQUIRED")

def main():
    docs={}
    for key,name in FILES.items():
        path=HERE/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=131072)
        doc=json.loads(path.read_text(encoding="utf-8"))
        require(type(doc) is dict and doc.get("schema")==SCHEMAS[key])
        docs[key]=doc
    k,n,o,p,q,r,s=(docs[x] for x in FILES)
    # The original packet is a template, not evidence of approval.
    approvals=(
        "fqdn_owner_approved","dns_control_verified",
        "qa_only_public_endpoint_scope_approved","firewall_cidr_scope_approved",
        "qa_client_ca_owner_approved","qa_client_cert_inventory_approved",
        "qa_client_revocation_mechanism_approved","server_certificate_lifecycle_approved",
        "qa_proxy_isolation_peer_reviewed","qa_proxy_config_peer_reviewed",
        "firebase_test_origin_approved","finance_routes_excluded_verified",
        "rollback_owner_and_test_approved","monitoring_and_alerts_approved",
        "external_negative_test_plan_approved","independent_security_reviewer_approved",
    )
    require(all(k.get(field) is False for field in approvals))
    require(k.get("workflow_status")=="PENDING_APPROVAL")
    require(n.get("qa_hostname")=="PENDING" and n.get("dns_zone")=="PENDING")
    require(o.get("deployment_authorization")=="NOT_GRANTED"
            and o.get("qa_fqdn")=="PENDING")
    require(p.get("deployment_authorization")=="NOT_GRANTED"
            and p.get("trusted_client_ca")=="NOT_SELECTED_OR_APPROVED"
            and p.get("server_certificate_provider")=="NOT_SELECTED_OR_APPROVED")
    require(q.get("deployment_authorization")=="NOT_GRANTED")
    require(r.get("deployment_authorization")=="NOT_GRANTED"
            and r.get("release_decision")=="BLOCKED_NO_DEPLOYMENT_PERMISSION")
    items=r.get("independent_prerequisites")
    require(type(items) is list and len(items)==8
            and all(type(x) is dict and x.get("state")=="NOT_APPROVED_OR_VERIFIED" for x in items))
    require(s.get("authorization")=="NOT_GRANTED"
            and s.get("external_https_endpoint")=="NOT_DEPLOYED"
            and s.get("financial_apply")=="LOCKED"
            and s.get("production_release")=="BLOCKED")
    cases=s.get("external_cases")
    require(type(cases) is list and len(cases)==22
            and all(type(x) is dict and x.get("status")=="NOT_TESTED_EXTERNAL" for x in cases))
    print("DB_R31_11_4X_SOURCE_RECORDS=PASS_SEVEN_SCHEMAS")
    print("DB_R31_11_4X_4K_APPROVAL_FIELDS=16_OF_16_PENDING")
    print("DB_R31_11_4X_INDEPENDENT_PREREQUISITES=8_OF_8_PENDING")
    print("DB_R31_11_4X_QA_DOMAIN_DNS=NOT_APPROVED")
    print("DB_R31_11_4X_SERVER_CERT=NOT_APPROVED")
    print("DB_R31_11_4X_CLIENT_CA_REVOCATION=NOT_APPROVED")
    print("DB_R31_11_4X_INGRESS_FIREWALL=NOT_APPROVED")
    print("DB_R31_11_4X_CHANGE_ROLLBACK=NOT_APPROVED")
    print("DB_R31_11_4X_EXTERNAL_ACCEPTANCE=0_OF_22_EXECUTED")
    print("DB_R31_11_4X_PREFLIGHT=PASS_METADATA_ONLY_NOT_AUTHORIZATION")
    return 0

if __name__=="__main__":
    try:
        rc=main()
    except (OSError,ValueError,UnicodeError,TypeError):
        print("STOP=DB_R31_11_4X_SOURCE_OR_AUTHORIZATION_REVIEW_REQUIRED")
        rc=2
    finally:
        print("DB_R31_11_4X_LIVE_HTTPS_MTLS=NOT_TESTED")
        print("DB_R31_11_4X_FINANCIAL_APPLY=LOCKED")
        print("DB_R31_11_4X_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(rc)
