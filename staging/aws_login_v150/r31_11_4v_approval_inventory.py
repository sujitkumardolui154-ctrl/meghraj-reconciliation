#!/usr/bin/env python3
"""R31.11.4V: static, read-only QA infrastructure approval inventory.

Does not test live DNS, certificate validity, ingress, ownership, or external TLS.
Does not invoke predecessor QA, install, configure, write data, or authorize deploy.
"""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCES={
    "DOMAIN":"r31_11_4o_domain_ownership_dossier.json",
    "PKI":"r31_11_4p_pki_trust_lifecycle_plan.json",
    "INGRESS":"r31_11_4q_ingress_isolation_policy.json",
    "APPROVAL":"r31_11_4r_deployment_gate.json",
    "EXTERNAL":"r31_11_4s_external_acceptance_matrix.json",
}
EXPECTED_SCHEMAS={
    "DOMAIN":"DB-R31.11.4O-DOMAIN-OWNERSHIP-EVIDENCE-V1",
    "PKI":"DB-R31.11.4P-PKI-TRUST-LIFECYCLE-V1",
    "INGRESS":"DB-R31.11.4Q-QA-INGRESS-ISOLATION-V1",
    "APPROVAL":"DB-R31.11.4R-ISOLATED-QA-DEPLOYMENT-GATE-V1",
    "EXTERNAL":"DB-R31.11.4S-REAL-EXTERNAL-MTLS-ACCEPTANCE-V1",
}

def check():
    data={}
    for name, filename in SOURCES.items():
        p=HERE/filename
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 131072:
            raise ValueError("SOURCE_MISSING_OR_UNSAFE_"+name)
        obj=json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj,dict) or obj.get("schema") != EXPECTED_SCHEMAS[name]:
            raise ValueError("SOURCE_SCHEMA_MISMATCH_"+name)
        data[name]=obj
    d,p,q,r,s=(data[x] for x in ("DOMAIN","PKI","INGRESS","APPROVAL","EXTERNAL"))
    if (d.get("deployment_authorization")!="NOT_GRANTED"
        or p.get("deployment_authorization")!="NOT_GRANTED"
        or q.get("deployment_authorization")!="NOT_GRANTED"
        or r.get("deployment_authorization")!="NOT_GRANTED"
        or r.get("release_decision")!="BLOCKED_NO_DEPLOYMENT_PERMISSION"
        or s.get("authorization")!="NOT_GRANTED"
        or s.get("financial_apply")!="LOCKED"
        or s.get("production_release")!="BLOCKED"):
        raise ValueError("UNEXPECTED_AUTHORIZATION_OR_LOCK_STATUS")
    cases=s.get("external_cases")
    if not isinstance(cases,list) or len(cases)!=22 or any(
        not isinstance(x,dict) or x.get("status")!="NOT_TESTED_EXTERNAL"
        for x in cases
    ):
        raise ValueError("EXTERNAL_MATRIX_UNEXPECTED")
    approval_ids={x.get("id"):x.get("state") for x in r.get("independent_prerequisites",[]) if isinstance(x,dict)}
    expected=[
        "ORGANIZATION_CONTROLLED_QA_FQDN_AND_DNS",
        "RESTRICTED_QA_INGRESS_AND_FIREWALL",
        "TEST_CLIENT_CA_AND_REAL_REVOCATION",
        "VALID_QA_SERVER_TLS_CERTIFICATE",
    ]
    if any(approval_ids.get(x)!="NOT_APPROVED_OR_VERIFIED" for x in expected):
        raise ValueError("PREREQUISITE_STATE_CHANGED_REVIEW_REQUIRED")
    print("DB_R31_11_4V_EXISTING_EVIDENCE_SOURCES=PASS_FIVE_SCHEMAS")
    print("DB_R31_11_4V_QA_DNS_OWNER=NOT_APPROVED_OR_VERIFIED")
    print("DB_R31_11_4V_QA_INGRESS_FIREWALL=NOT_APPROVED_OR_VERIFIED")
    print("DB_R31_11_4V_CLIENT_CA_REVOCATION=NOT_APPROVED_OR_VERIFIED")
    print("DB_R31_11_4V_SERVER_TLS_CERT=NOT_APPROVED_OR_VERIFIED")
    print("DB_R31_11_4V_ROLLBACK=DESIGN_ONLY_NOT_APPROVED")
    print("DB_R31_11_4V_EXTERNAL_CASES=0_OF_22_EXECUTED")
    print("DB_R31_11_4V_AUDIT=PASS_SOURCE_INVENTORY_ONLY")
    return 0

if __name__=="__main__":
    try:
        code=check()
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
        print("STOP=DB_R31_11_4V_SOURCE_OR_APPROVAL_REVIEW_REQUIRED")
        code=2
    finally:
        print("DB_R31_11_4V_EXTERNAL_HTTPS_MTLS=NOT_TESTED")
        print("DB_R31_11_4V_FINANCIAL_APPLY=LOCKED")
        print("DB_R31_11_4V_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(code)
