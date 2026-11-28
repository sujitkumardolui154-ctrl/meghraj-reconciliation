#!/usr/bin/env python3
"""R31.11.4P — PKI trust/lifecycle planning + full 4O→4H read-only QA.

Source-only policy fixtures are NOT actual Caddy client revocation support.
No DNS, CA issuance, certificates, secrets, TLS listeners, user logins,
Caddy edits, SQL writes, Docker mutation or financial Apply.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True

import r31_11_4o_combined_domain_ownership as o
import r31_11_4n_combined_dns_pki_preflight as n
import r31_11_4m_combined_evidence_preflight as m
import r31_11_4k_external_mtls_readiness as k
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

PLAN=Path(__file__).resolve().parent/"r31_11_4p_pki_trust_lifecycle_plan.json"
SCHEMA="DB-R31.11.4P-PKI-TRUST-LIFECYCLE-V1"
PKI_FIELDS=(
 "qa_client_ca_owner_approved","qa_client_cert_inventory_approved",
 "qa_client_revocation_mechanism_approved","server_certificate_lifecycle_approved",
 "server_certificate_provider","client_ca_metadata_reference",
)
LIFECYCLE=(
 "CA_TRUST_OWNER_APPROVAL",
 "CLIENT_CERT_PROFILE_REVIEW",
 "SERVER_CERT_SAN_EKU_VALIDITY_REVIEW",
 "ISSUANCE_WITH_CONTROLLED_KEY_CUSTODY",
 "VALIDITY_MONITORING_AND_RENEWAL_PLAN",
 "REVOCATION_MECHANISM_INDEPENDENT_REVIEW",
 "REVOKED_CERT_REJECTION_EXTERNAL_TEST",
 "ROTATION_ROLLBACK_AND_TERMINATION_REVIEW",
)
REQUIREMENTS={
 "separate_qa_client_ca":"REQUIRED_DESIGN_ONLY",
 "unique_client_certificate_identity":"REQUIRED_DESIGN_ONLY",
 "client_certificate_eku":"CLIENT_AUTH_DESIGN_ONLY",
 "server_certificate_san":"MATCH_APPROVED_QA_FQDN_WHEN_AVAILABLE",
 "server_certificate_eku":"SERVER_AUTH_DESIGN_ONLY",
 "minimum_tls_version":"TLS_1_2_OR_HIGHER_DESIGN_ONLY",
 "client_certificate_revocation":"MUST_DENY_REVOKED_CERTS_WITH_VERIFIED_ENFORCEMENT",
 "expired_client_and_server_certificates":"MUST_DENY",
 "unknown_client_ca":"MUST_DENY",
 "nonproduction_key_custody":"PRIVATE_KEY_MATERIAL_NEVER_IN_GIT_OR_CHAT",
 "independent_pki_reviewer":"REQUIRED_NOT_ASSIGNED",
 "production_financial_apply":"LOCKED",
}
STATUS={
 "real_ca_custody":"NOT_VERIFIED",
 "real_qa_server_certificate":"NOT_ISSUED_OR_VERIFIED",
 "real_qa_client_certificates":"NOT_ISSUED_OR_VERIFIED",
 "client_revocation":"NOT_TESTED",
 "external_mtls":"NOT_TESTED",
 "financial_apply":"LOCKED",
 "production_release":"BLOCKED",
 "r3112":"ACTIVE_QA_DESIGN_RELEASE_GATED",
}
ROOT={
 "schema","classification","environment","deployment_authorization",
 "qa_fqdn","trusted_client_ca","server_certificate_provider",
 "revocation_enforcement","reference_security_requirements",
 "evidence_requirements","lifecycle_workflow","caveat","status",
}
EVIDENCE_KEYS={
 "field","state","evidence_ticket","evidence_sha256",
 "reviewer_ticket","reviewed_at_utc",
}

class PKIBlocked(RuntimeError):
    """Emit only static, non-sensitive failure codes."""


def require(ok, code):
    if not ok:
        raise PKIBlocked(code)


def read_plan(path=PLAN):
    require(path.is_file() and not path.is_symlink(), "PKI_PLAN_MISSING_OR_SYMLINK")
    data=path.read_bytes()
    require(1 <= len(data) <= 24576, "PKI_PLAN_SIZE_INVALID")
    try:
        d=json.loads(data.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise PKIBlocked("PKI_PLAN_INVALID_JSON") from None
    require(type(d) is dict and set(d)==ROOT,"PKI_PLAN_SCHEMA_INVALID")
    require(d["schema"]==SCHEMA
       and d["classification"]=="NONSECRET_DESIGN_NOT_CERTIFICATE_ISSUANCE"
       and d["environment"]=="qa_isolated_external_mtls"
       and d["deployment_authorization"]=="NOT_GRANTED"
       and d["qa_fqdn"]=="PENDING"
       and d["trusted_client_ca"]=="NOT_SELECTED_OR_APPROVED"
       and d["server_certificate_provider"]=="NOT_SELECTED_OR_APPROVED"
       and d["revocation_enforcement"]=="NOT_SELECTED_OR_TESTED",
       "PKI_PLAN_RELEASE_BOUNDARY_CHANGED")
    require(type(d["reference_security_requirements"]) is dict
            and d["reference_security_requirements"]==REQUIREMENTS,
            "PKI_TRUST_REQUIREMENTS_CHANGED")
    require(type(d["status"]) is dict and d["status"]==STATUS,
            "PKI_EXTERNAL_TEST_OR_FINANCE_STATUS_CHANGED")
    entries=d["evidence_requirements"]
    require(type(entries) is list and len(entries)==len(PKI_FIELDS),
            "PKI_APPROVAL_COUNT_CHANGED")
    require([i.get("field") if type(i) is dict else None for i in entries]
            ==list(PKI_FIELDS),"PKI_APPROVAL_FIELDS_CHANGED")
    for item in entries:
        require(set(item)==EVIDENCE_KEYS and
                all(item[key]=="PENDING" for key in EVIDENCE_KEYS-{"field"}),
                "PKI_APPROVAL_EVIDENCE_NOT_PENDING")
    lifecycle=d["lifecycle_workflow"]
    require(type(lifecycle) is list and
            lifecycle==[{"id":code,"status":"NOT_IMPLEMENTED_OR_TESTED"}
                        for code in LIFECYCLE],
            "PKI_LIFECYCLE_NOT_PENDING")
    caveat=d["caveat"]
    require(type(caveat) is str and
            "trust chain validation alone does not demonstrate revocation" in caveat
            and "no real certificate identities or secrets" in caveat,
            "PKI_REVOCATION_CAUTION_REMOVED")
    return d


def enforce_prior_approval_consistency(packet_path,register_path,intake_path):
    packet=k.read_packet(packet_path)
    require(packet["workflow_status"]=="PENDING_APPROVAL"
            and all(packet[x] is False for x in k.APPROVAL_FIELDS)
            and all(packet[x]=="PENDING" for x in k.TEXT_FIELDS),
            "PKI_ORIGINAL_4K_PACKET_CHANGED")
    m.read_register(register_path)
    d=json.loads(register_path.read_text("utf-8"))
    by_field={item["field"]:item for item in d["entries"]}
    intake,_=n.validate_intake(intake_path)
    by_intake={item["field"]:item for item in intake["items"]}
    for field in PKI_FIELDS:
        require(by_field[field]["status"]=="PENDING"
                and by_intake[field]["state"]=="PENDING",
                "PKI_PRIOR_REGISTER_EVIDENCE_CHANGED")
    require(intake["qa_hostname"]=="PENDING" and intake["dns_zone"]=="PENDING",
            "PKI_REAL_QA_HOSTNAME_NOT_APPROVED")
    print("DB_R31_11_4P_PRIOR_K_M_N_APPROVALS=6_OF_6_PKI_PENDING",flush=True)


def simulated_decision(cert, *, trusted_ca, allowed_ids, revoked_ids, now):
    """PURE synthetic POLICY decision, NOT a TLS/cert verification API.

    This is deliberately mock metadata: no PEM, no chain parsing, no
    signature verification, no CRL/OCSP network access, no Caddy integration.
    """
    if not isinstance(cert,dict) or set(cert)!={"id","issuer","eku","not_before","not_after"}:
        return False
    if cert["issuer"]!=trusted_ca or cert["eku"]!="clientAuth":
        return False
    if cert["id"] not in allowed_ids or cert["id"] in revoked_ids:
        return False
    if not isinstance(cert["not_before"],datetime) or not isinstance(cert["not_after"],datetime):
        return False
    return cert["not_before"] <= now < cert["not_after"]


def simulation():
    from datetime import timedelta
    now=datetime(2026,11,28,tzinfo=timezone.utc)
    good={"id":"synthetic-client-a","issuer":"synthetic-qa-ca","eku":"clientAuth",
          "not_before":now-timedelta(days=1),"not_after":now+timedelta(days=1)}
    trusted="synthetic-qa-ca"
    allowed=frozenset({"synthetic-client-a"})
    require(simulated_decision(good,trusted_ca=trusted,allowed_ids=allowed,
                               revoked_ids=frozenset(),now=now),
            "PKI_SYNTHETIC_VALID_CLIENT_REJECTED")
    cases=[
        (dict(good,id="synthetic-unlisted"),frozenset()),
        (dict(good,issuer="synthetic-untrusted-ca"),frozenset()),
        (dict(good,eku="serverAuth"),frozenset()),
        (dict(good,not_after=now-timedelta(minutes=1)),frozenset()),
        (dict(good,not_before=now+timedelta(minutes=1)),frozenset()),
        (good,frozenset({"synthetic-client-a"})),
    ]
    for altered,denied in cases:
        require(not simulated_decision(altered,trusted_ca=trusted,allowed_ids=allowed,
                                       revoked_ids=denied,now=now),
                "PKI_SYNTHETIC_DENIAL_FAILED")
    print("DB_R31_11_4P_POLICY_SIMULATION=PASS_FAIL_CLOSED_METADATA_ONLY",flush=True)
    print("DB_R31_11_4P_POLICY_SIMULATION_REAL_TLS=NOT_TESTED",flush=True)


def combined(sha,plan_path,packet_path,register_path,intake_path,dossier_path):
    read_plan(plan_path)
    enforce_prior_approval_consistency(packet_path,register_path,intake_path)
    print("DB_R31_11_4P_TRUST_PROFILE=PASS_REFERENCE_DESIGN_ONLY",flush=True)
    print("DB_R31_11_4P_LIFECYCLE_STEPS=8_NOT_IMPLEMENTED",flush=True)
    print("DB_R31_11_4P_REVOCATION_ENFORCEMENT=NOT_SELECTED_OR_TESTED",flush=True)
    simulation()
    o.full_combined_preflight(sha,dossier_path,intake_path,register_path,packet_path)
    print("DB_R31_11_4P_4O_THROUGH_4H_COMBINED_QA=PASS_READONLY",flush=True)
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "PKI_CADDY_FINGERPRINT_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4P_POST_QA_CADDY_PG=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4P_COMBINED_PKI_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4P combined PKI readiness QA")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--plan",type=Path,default=PLAN)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    parser.add_argument("--register",type=Path,default=m.REGISTER)
    parser.add_argument("--intake",type=Path,default=n.INTAKE)
    parser.add_argument("--dossier",type=Path,default=o.DOSSIER)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4P COMBINED PKI TRUST LIFECYCLE REVOCATION QA ===",flush=True)
    try:
        combined(args.source_sha,args.plan,args.packet,args.register,
                 args.intake,args.dossier)
        return 0
    except PKIBlocked as exc:
        codes={
            "PKI_PLAN_MISSING_OR_SYMLINK","PKI_PLAN_SIZE_INVALID",
            "PKI_PLAN_INVALID_JSON","PKI_PLAN_SCHEMA_INVALID",
            "PKI_PLAN_RELEASE_BOUNDARY_CHANGED",
            "PKI_TRUST_REQUIREMENTS_CHANGED",
            "PKI_EXTERNAL_TEST_OR_FINANCE_STATUS_CHANGED",
            "PKI_APPROVAL_COUNT_CHANGED","PKI_APPROVAL_FIELDS_CHANGED",
            "PKI_APPROVAL_EVIDENCE_NOT_PENDING",
            "PKI_LIFECYCLE_NOT_PENDING","PKI_REVOCATION_CAUTION_REMOVED",
            "PKI_ORIGINAL_4K_PACKET_CHANGED","PKI_PRIOR_REGISTER_EVIDENCE_CHANGED",
            "PKI_REAL_QA_HOSTNAME_NOT_APPROVED",
            "PKI_SYNTHETIC_VALID_CLIENT_REJECTED",
            "PKI_SYNTHETIC_DENIAL_FAILED",
            "PKI_CADDY_FINGERPRINT_DRIFT",
        }
        code=str(exc)
        print("DB_R31_11_4P_BLOCK_REASON="+
              (code if code in codes else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4P_COMBINED_PKI_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        print("DB_R31_11_4P_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4P_COMBINED_PKI_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4P_CLIENT_CA_AND_SERVER_CERTS=NOT_ISSUED_OR_VERIFIED",flush=True)
        print("DB_R31_11_4P_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4P_REAL_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4P_22_EXTERNAL_ACCEPTANCE=NOT_TESTED",flush=True)
        print("DB_R31_11_4P_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4P_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4P_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
