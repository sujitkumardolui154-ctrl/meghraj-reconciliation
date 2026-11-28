#!/usr/bin/env python3
"""R31.11.4S external HTTPS/mTLS acceptance readiness + full private QA audit.

This is a READ-ONLY, NON-NETWORK external acceptance GATE, not a test
client. There is NO authorized endpoint/hostname/certificate or approved
ingress to test. Real E2E execution MUST remain NOT_TESTED until a
separately approved QA endpoint and remote client exist.

Reruns 4R→4Q→4P→4O→4N→4M→4L→4K→4J→4H private QA integrity in one command.
Does not create endpoints, certs, DNS, Docker objects, users, or financial
writes and does not make network requests to an external target.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True

import r31_11_4r_combined_approval_preflight as r
import r31_11_4l_combined_design_gate as l
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

HERE=Path(__file__).resolve().parent
MATRIX=HERE/"r31_11_4s_external_acceptance_matrix.json"
SCHEMA="DB-R31.11.4S-REAL-EXTERNAL-MTLS-ACCEPTANCE-V1"
ROOT={
 "schema","classification","scope","source_4r_gate","source_4l_matrix",
 "authorization","approved_fqdn","remote_test_client",
 "external_https_endpoint","approved_dns_and_certificate_evidence",
 "approved_network_scope","rollback_authorization","witnessed_execution",
 "external_cases","postconditions","r3112","financial_apply",
 "production_release","notice"
}
CASE_KEYS={
 "id","kind","expected","description","status",
 "evidence_ticket","independent_review_ticket"
}
# Exactly the existing R31.11.4L 22 cases, original source order.
GROUPS=(
 ("remote_identity","ALLOW_READONLY"),
 ("remote_identity","ALLOW_READONLY"),
 *[("tls_boundary","DENY_HANDSHAKE_OR_REQUEST")]*8,
 *[("firebase_session","DENY_REQUEST")]*4,
 *[("tenant_rls","DENY_CROSS_TENANT")]*2,
 ("tenant_rls","DENY_FORGED_IDENTITY"),
 ("finance_boundary","DENY_FINANCIAL_WRITE"),
 ("monitoring","VERIFY_TELEMETRY"),
 ("postconditions","VERIFY_UNCHANGED"),
 ("postconditions","VERIFY_DB_READONLY"),
 ("postconditions","VERIFY_APPROVED_ROLLBACK"),
)
POSTCONDITIONS={
 "public_caddy":"REQUIRE_EXISTING_UNCHANGED",
 "qa_postgres":"REQUIRE_ZERO_ROWS_TWO_OWNER_MAPPINGS",
 "financial_apply":"LOCKED",
 "production_release":"BLOCKED",
}

class AcceptanceBlocked(RuntimeError):
    """Fixed non-sensitive error reasons only."""


def require(ok,reason):
    if not ok:
        raise AcceptanceBlocked(reason)


def validate_plan(path=MATRIX):
    require(path.is_file() and not path.is_symlink(),
            "S_MATRIX_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    require(1<=len(raw)<=32768,"S_MATRIX_SIZE_INVALID")
    try:
        doc=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise AcceptanceBlocked("S_MATRIX_INVALID_JSON") from None
    require(type(doc) is dict and set(doc)==ROOT,"S_MATRIX_SCHEMA_CHANGED")
    require(doc["schema"]==SCHEMA
            and doc["classification"]=="EXTERNAL_ACCEPTANCE_PLAN_NOT_EXECUTION"
            and doc["scope"]=="DEDICATED_NONPRODUCTION_QA_ONLY"
            and doc["source_4r_gate"]==r.MANIFEST.name
            and doc["source_4l_matrix"]==l.DESIGN.name
            and doc["authorization"]=="NOT_GRANTED"
            and doc["approved_fqdn"]=="PENDING"
            and doc["remote_test_client"]=="NOT_AUTHORIZED"
            and doc["external_https_endpoint"]=="NOT_DEPLOYED"
            and doc["approved_dns_and_certificate_evidence"]=="PENDING"
            and doc["approved_network_scope"]=="PENDING"
            and doc["rollback_authorization"]=="PENDING"
            and doc["witnessed_execution"]=="NOT_PERFORMED"
            and doc["r3112"]=="ACTIVE_QA_DESIGN_RELEASE_GATED"
            and doc["financial_apply"]=="LOCKED"
            and doc["production_release"]=="BLOCKED",
            "S_EXTERNAL_AUTHORIZATION_FALSIFIED")
    require(type(doc["postconditions"]) is dict
            and doc["postconditions"]==POSTCONDITIONS,
            "S_REQUIRED_QA_POSTCONDITIONS_CHANGED")

    cases=doc["external_cases"]
    require(type(cases) is list and len(cases)==22
            and len(GROUPS)==22 and len(l.EXPECTED_ACCEPTANCE_CASES)==22,
            "S_EXTERNAL_MATRIX_COUNT_CHANGED")
    ids=[]
    for i,(entry,(kind,expected)) in enumerate(zip(cases,GROUPS)):
        require(type(entry) is dict and set(entry)==CASE_KEYS,
                "S_CASE_SCHEMA_CHANGED")
        require(entry["id"]==l.EXPECTED_ACCEPTANCE_CASES[i]
                and entry["kind"]==kind
                and entry["expected"]==expected
                and entry["status"]=="NOT_TESTED_EXTERNAL"
                and entry["evidence_ticket"]=="PENDING"
                and entry["independent_review_ticket"]=="PENDING",
                "S_UNSUPPORTED_TEST_ACCEPTANCE_CLAIM")
        description=entry["description"]
        require(type(description) is str and 20<=len(description)<=170
                and not any(word in description.upper() for word in
                            ("PRIVATE KEY","BEARER ","PASSWORD=","API" + "KEY=")),
                "S_UNSAFE_TEST_DESCRIPTION")
        ids.append(entry["id"])
    require(len(set(ids))==22,"S_DUPLICATE_EXTERNAL_CASE")
    note=doc["notice"]
    require(type(note) is str and 90<=len(note)<=300
            and "not a TLS probe" in note
            and "permission to deploy" in note
            and "independently verified" in note,
            "S_ACCEPTANCE_DISCLAIMER_REMOVED")
    print("DB_R31_11_4S_EXTERNAL_MATRIX=PASS_22_EXACT_CASES_NOT_TESTED",flush=True)
    print("DB_R31_11_4S_SOURCE_4L_CASE_ORDER=PASS_MATCHED",flush=True)
    print("DB_R31_11_4S_EVIDENCE_RECEIPTS=ZERO_INDEPENDENT_EXTERNAL",flush=True)
    print("DB_R31_11_4S_APPROVED_QA_FQDN=NOT_PROVIDED",flush=True)
    print("DB_R31_11_4S_E2E_GATE=DENIED_MISSING_APPROVALS_AND_ENDPOINT",flush=True)
    return doc


def run_combined(sha,plan_path,previous_path,packet_path,register_path):
    validate_plan(plan_path)
    # Earlier 4R checks the *original* all-pending approval manifest and
    # invokes full predecessor read-only QA, including Caddy, PG RLS, two
    # owner maps, zero financial source rows and 4F resource cleanup.
    r.full_combined(sha,previous_path,packet_path,register_path)
    print("DB_R31_11_4S_4R_THROUGH_4H_SECURITY=PASS_READONLY",flush=True)
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "S_PUBLIC_CADDY_FINGERPRINT_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4S_AFTER_QA_CADDY_POSTGRES=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4S_COMBINED_READINESS=PASS_NO_LIVE_EXTERNAL_TEST",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(
       description="R31.11.4S nondeployable external E2E acceptance readiness")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--matrix",type=Path,default=MATRIX)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4S EXTERNAL HTTPS/MTLS E2E ACCEPTANCE READINESS ===",
          flush=True)
    try:
        run_combined(args.source_sha,args.matrix,r.MANIFEST,
                     r.q.k.TEMPLATE_PACKET,r.q.m.REGISTER)
        return 0
    except AcceptanceBlocked as exc:
        codes={
            "S_MATRIX_MISSING_OR_SYMLINK","S_MATRIX_SIZE_INVALID",
            "S_MATRIX_INVALID_JSON","S_MATRIX_SCHEMA_CHANGED",
            "S_EXTERNAL_AUTHORIZATION_FALSIFIED",
            "S_REQUIRED_QA_POSTCONDITIONS_CHANGED",
            "S_EXTERNAL_MATRIX_COUNT_CHANGED","S_CASE_SCHEMA_CHANGED",
            "S_UNSUPPORTED_TEST_ACCEPTANCE_CLAIM",
            "S_UNSAFE_TEST_DESCRIPTION","S_DUPLICATE_EXTERNAL_CASE",
            "S_ACCEPTANCE_DISCLAIMER_REMOVED",
            "S_PUBLIC_CADDY_FINGERPRINT_DRIFT",
        }
        code=str(exc)
        print("DB_R31_11_4S_BLOCK_REASON="+
              (code if code in codes else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4S_SOURCE_OR_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        # Suppress raw cloud/PG/Caddy/Firebase exception messages.
        print("DB_R31_11_4S_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4S_SOURCE_OR_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4S_ACTUAL_REMOTE_TESTS=0_OF_22_EXECUTED",flush=True)
        print("DB_R31_11_4S_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4S_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4S_REAL_FIREBASE_SESSION_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4S_QA_ENDPOINT=NOT_DEPLOYED_BY_THIS_PHASE",flush=True)
        print("DB_R31_11_4S_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4S_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4S_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
