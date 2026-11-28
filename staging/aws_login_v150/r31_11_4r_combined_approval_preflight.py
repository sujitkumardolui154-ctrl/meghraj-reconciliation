#!/usr/bin/env python3
"""R31.11.4R: isolated QA endpoint DEPLOYMENT APPROVAL PRECHECK.

All checks are READ-ONLY. This script has no route that can deploy.
Existing R31.11.4Q→4P→4O→4N→4M→4L→4K→4J→4H checks are rerun against
the existing private QA environment. A successful *preflight* still
reports DEPLOYMENT=BLOCKED until separately verified owner approvals,
actual QA FQDN, DNS/PKI, ingress, independently reviewed rollback exist.

This is NOT a deployment script. No DNS lookup/change, CA/cert issuance,
firewall or Caddy changes, Docker run/connect, Firebase password login,
database write or financial Apply.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

import r31_11_4q_combined_ingress_preflight as q
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

MANIFEST = Path(__file__).resolve().with_name("r31_11_4r_deployment_gate.json")
SCHEMA = "DB-R31.11.4R-ISOLATED-QA-DEPLOYMENT-GATE-V1"
PRECONDITIONS = (
    "ORGANIZATION_CONTROLLED_QA_FQDN_AND_DNS",
    "RESTRICTED_QA_INGRESS_AND_FIREWALL",
    "TEST_CLIENT_CA_AND_REAL_REVOCATION",
    "VALID_QA_SERVER_TLS_CERTIFICATE",
    "DEDICATED_NONROOT_QA_HTTP_ADAPTER",
    "EXACT_ROUTES_FIREBASE_AND_RLS_SECURITY",
    "INDEPENDENT_SECURITY_CHANGE_AND_ROLLBACK_APPROVAL",
    "MONITORING_ALERTING_AND_EXTERNAL_TEST_OWNER",
)
ROOT = {
    "schema","classification","mode","deployment_authorization",
    "approved_qa_fqdn","independent_owner_and_security_approval",
    "policy_constraints","independent_prerequisites","linked_approvals",
    "reviewed_rollback","remote_acceptance","release_decision",
    "r3112","financial_apply","production_release","statement",
}
CONSTRAINTS = {
    "public_caddy_sha256":h.EXPECTED_4G_CADDY_SHA256,
    "public_caddy_change":"FORBIDDEN",
    "qa_ingress":"NOT_DEPLOYED",
    "qa_http_adapter":"NOT_DEPLOYED",
    "qa_postgres_public_port":"FORBIDDEN",
    "qa_to_production_finance":"FORBIDDEN",
    "qa_proxy_to_docker_socket":"FORBIDDEN",
    "qa_proxy_to_postgres_direct":"FORBIDDEN",
    "restricted_cidr_list":"PENDING",
    "test_client_ca":"NOT_APPROVED",
    "client_revocation":"NOT_IMPLEMENTED",
    "signed_firebase_test_session":"REQUIRED_FOR_FUTURE_TEST_ONLY",
    "finance_write_endpoint":"FORBIDDEN",
    "financial_apply":"LOCKED",
    "production_release":"BLOCKED",
}
REMOTE = {
    "planned_case_count":22,
    "executed_case_count":0,
    "external_https_mtls":"NOT_TESTED",
    "real_client_revocation":"NOT_TESTED",
    "real_firebase_expired_revoked":"NOT_TESTED",
}

class DeploymentBlocked(RuntimeError):
    """Failure of source/evidence integrity, not the expected missing approvals."""


def require(ok,code):
    if not ok:
        raise DeploymentBlocked(code)


def validate_manifest(path=MANIFEST):
    require(path.is_file() and not path.is_symlink(),"R_MANIFEST_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    require(1<=len(raw)<=32768,"R_MANIFEST_SIZE_INVALID")
    try:
        doc=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise DeploymentBlocked("R_MANIFEST_INVALID_JSON") from None
    require(type(doc) is dict and set(doc)==ROOT,"R_MANIFEST_SCHEMA_INVALID")
    require(
        doc["schema"]==SCHEMA
        and doc["classification"]=="READONLY_DEPLOYMENT_APPROVAL_PRECHECK_NO_EXECUTION"
        and doc["mode"]=="APPROVAL_PREFLIGHT_ONLY"
        and doc["deployment_authorization"]=="NOT_GRANTED"
        and doc["approved_qa_fqdn"]=="PENDING"
        and doc["independent_owner_and_security_approval"]=="NOT_VERIFIED"
        and doc["release_decision"]=="BLOCKED_NO_DEPLOYMENT_PERMISSION"
        and doc["r3112"]=="ACTIVE_QA_DESIGN_RELEASE_GATED"
        and doc["financial_apply"]=="LOCKED"
        and doc["production_release"]=="BLOCKED",
        "R_RELEASE_AUTHORIZATION_CHANGED")
    require(type(doc["policy_constraints"]) is dict
            and doc["policy_constraints"]==CONSTRAINTS,
            "R_INFRASTRUCTURE_CONSTRAINTS_CHANGED")
    require(doc["independent_prerequisites"]==[
        {"id":name,"state":"NOT_APPROVED_OR_VERIFIED"} for name in PRECONDITIONS],
        "R_PREREQUISITES_MISSING_OR_FAKE_APPROVED")
    expected_fields=tuple(q.k.APPROVAL_FIELDS)+tuple(q.k.TEXT_FIELDS)
    require(len(expected_fields)==23 and len(set(expected_fields))==23,
            "R_SOURCE_4K_APPROVAL_CONTRACT_CHANGED")
    require(doc["linked_approvals"]==[
        {"field":field,"state":"PENDING"} for field in expected_fields],
        "R_LINKED_APPROVALS_CHANGED")
    require(doc["reviewed_rollback"]==[
        {"id":item,"state":"DESIGNED_NOT_EXECUTED"} for item in q.l.EXPECTED_ROLLBACK_STEPS],
        "R_ROLLBACK_FALSIFIED_OR_CHANGED")
    require(type(doc["remote_acceptance"]) is dict
            and doc["remote_acceptance"]==REMOTE,
            "R_EXTERNAL_ACCEPTANCE_FALSIFIED")
    note=doc["statement"]
    require(type(note) is str and 80<=len(note)<=350
            and "No manifest" in note
            and "independent" in note
            and "authorization" in note,
            "R_INDEPENDENT_APPROVAL_NOTICE_CHANGED")

    print("DB_R31_11_4R_GATE_MANIFEST=PASS_NONDEPLOYABLE_SCHEMA",flush=True)
    print("DB_R31_11_4R_INDEPENDENT_PREREQUISITES=8_OF_8_UNVERIFIED",flush=True)
    print("DB_R31_11_4R_LINKED_APPROVALS=23_OF_23_PENDING",flush=True)
    print("DB_R31_11_4R_ROLLBACK_STEPS=9_DESIGNED_NOT_EXECUTED",flush=True)
    print("DB_R31_11_4R_REMOTE_ACCEPTANCE=0_OF_22_TESTED",flush=True)
    return doc


def validate_real_approval_sources(packet_path,register_path):
    # Even a source flag "true" or REVIEWED metadata cannot authorize R:
    # evidence content and human signoff are external to this design.
    q.check_approvals(packet_path,register_path)
    print("DB_R31_11_4R_REAL_OWNER_SECURITY_SIGNOFF=NOT_VERIFIED",flush=True)
    print("DB_R31_11_4R_QA_HOSTNAME_DNS_AND_CERTS=NOT_APPROVED",flush=True)
    print("DB_R31_11_4R_ROLLBACK_EXERCISE=NOT_EXECUTED",flush=True)
    print("DB_R31_11_4R_DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS",flush=True)


def full_combined(source_sha,manifest_path,packet_path,register_path):
    validate_manifest(manifest_path)
    validate_real_approval_sources(packet_path,register_path)
    q.full_combined_preflight(source_sha,q.FILE,packet_path,register_path)
    print("DB_R31_11_4R_4Q_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY",flush=True)
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "R_PUBLIC_CADDY_FINGERPRINT_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4R_AFTER_COMBINED_CADDY_AND_PG=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4R_APPROVAL_PREFLIGHT=PASS_READONLY_RELEASE_BLOCKED",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4R approval preflight ONLY")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--manifest",type=Path,default=MANIFEST)
    parser.add_argument("--packet",type=Path,default=q.k.TEMPLATE_PACKET)
    parser.add_argument("--register",type=Path,default=q.m.REGISTER)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4R CONTROLLED QA ENDPOINT DEPLOYMENT APPROVAL PREFLIGHT ===",
          flush=True)
    try:
        full_combined(args.source_sha,args.manifest,args.packet,args.register)
        return 0
    except DeploymentBlocked as exc:
        known={
            "R_MANIFEST_MISSING_OR_SYMLINK","R_MANIFEST_SIZE_INVALID",
            "R_MANIFEST_INVALID_JSON","R_MANIFEST_SCHEMA_INVALID",
            "R_RELEASE_AUTHORIZATION_CHANGED",
            "R_INFRASTRUCTURE_CONSTRAINTS_CHANGED",
            "R_PREREQUISITES_MISSING_OR_FAKE_APPROVED",
            "R_SOURCE_4K_APPROVAL_CONTRACT_CHANGED","R_LINKED_APPROVALS_CHANGED",
            "R_ROLLBACK_FALSIFIED_OR_CHANGED","R_EXTERNAL_ACCEPTANCE_FALSIFIED",
            "R_INDEPENDENT_APPROVAL_NOTICE_CHANGED",
            "R_PUBLIC_CADDY_FINGERPRINT_DRIFT",
        }
        reason=str(exc)
        print("DB_R31_11_4R_BLOCK_REASON="+(
              reason if reason in known else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4R_SOURCE_OR_INFRA_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        # Never echo raw Docker, PG, Firebase or certificate exceptions.
        print("DB_R31_11_4R_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4R_SOURCE_OR_INFRA_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4R_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4R_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4R_REAL_FIREBASE_SESSION_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4R_QA_ENDPOINT=NOT_DEPLOYED_BY_THIS_PHASE",flush=True)
        print("DB_R31_11_4R_PUBLIC_CADDY=UNCHANGED_BY_THIS_PHASE",flush=True)
        print("DB_R31_11_4R_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4R_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4R_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
