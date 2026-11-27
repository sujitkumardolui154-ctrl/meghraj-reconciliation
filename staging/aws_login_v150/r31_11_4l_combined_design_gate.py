#!/usr/bin/env python3
"""R31.11.4L: read-only 4K security + isolated external mTLS design gate.

One combined command, no deployment. Reads existing private QA metadata
and checks strict no-secrets design plus the 4K 23-field pending approval
packet. Does not create/delete networks, containers, certificates, user
sessions, Caddy routes or SQL rows. NEVER authorizes live TLS or finance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True

import r31_11_4k_external_mtls_readiness as k
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

HERE = Path(__file__).resolve().parent
DESIGN=HERE/"r31_11_4l_isolated_mtls_design.json"
SCHEMA="DB-R31.11.4L-ISOLATED-MTLS-DESIGN-V1"
EXPECTED_ROUTES=(
    "GET /healthz",
    "GET /auth/csrf",
    "POST /auth/session",
    "GET /auth/me",
    "GET /api/r31-private-qa/tenant-rls-source-r3114",
)
EXPECTED_FORBIDDEN=(
    "/admin", "/api/payment-evidence", "/api/reconciliation",
    "/api/invoice", "/api/gst", "/api/credit", "/api/financial",
    "/api/finance", "/api/bulk",
)
EXPECTED_ACCEPTANCE_CASES=(
    "REAL_TLS_VALID_CERT_AUTH_FIREBASE_A_PG_A_READONLY",
    "REAL_TLS_VALID_CERT_AUTH_FIREBASE_B_PG_B_READONLY",
    "TLS_MISSING_CLIENT_CERT_DENIED",
    "TLS_UNTRUSTED_CLIENT_CA_DENIED",
    "TLS_EXPIRED_CLIENT_CERT_DENIED",
    "TLS_REVOKED_CLIENT_CERT_DENIED",
    "TLS_WRONG_SERVER_HOSTNAME_DENIED",
    "TLS_WRONG_SERVER_TRUST_CA_DENIED",
    "TLS_SNI_HOST_MISMATCH_DENIED",
    "TLS_BELOW_1_2_DENIED",
    "FIREBASE_ANONYMOUS_DENIED",
    "FIREBASE_TAMPERED_COOKIE_DENIED",
    "FIREBASE_REAL_EXPIRED_COOKIE_DENIED",
    "FIREBASE_REAL_REVOKED_COOKIE_DENIED",
    "TENANT_A_TO_B_DATA_DENIED",
    "TENANT_B_TO_A_DATA_DENIED",
    "FORGED_OWNER_UID_OR_PG_ROLE_DENIED",
    "FINANCIAL_WRITE_UPLOAD_GST_AND_INVOICE_ROUTES_DENIED",
    "TLS_RATE_LIMITS_AND_AUDIT_EVENTS_VERIFIED",
    "CADDY_PRODUCTION_BASELINE_UNCHANGED",
    "QA_DATABASE_ROWS_ZERO_MAPS_TWO",
    "APPROVED_ROLLBACK_EXECUTION_VERIFIED",
)
EXPECTED_ROLLBACK_STEPS=(
    "VERIFY_APPROVED_CHANGE_TICKET_AND_ROLLBACK_OWNER",
    "CAPTURE_PUBLIC_CADDY_SHA256_AND_PRIVATE_PG_QA_ROW_COUNTS",
    "STOP_ONLY_LABELED_ISOLATED_QA_INGRESS_AFTER_APPROVAL",
    "REVOKE_ONLY_APPROVED_QA_CLIENT_CERT_ACCESS",
    "RESTORE_RESTRICTED_INGRESS_AND_DNS_VIA_SEPARATE_CHANGE",
    "VERIFY_ORIGINAL_PUBLIC_CADDY_ROUTE_AND_SHA256_UNCHANGED",
    "VERIFY_QA_PG_RLS_ROWS_ZERO_AND_TWO_OWNER_MAPS",
    "VERIFY_NO_EPHEMERAL_ADC_OR_UNAPPROVED_LISTENER",
    "RECORD_ROLLBACK_REVIEW_SIGNOFF",
)
ISOLATION={
    "public_caddy":"UNCHANGED_FINGERPRINT_"+h.EXPECTED_4G_CADDY_SHA256,
    "external_qa_reverse_proxy":"NOT_CREATED",
    "qa_app_http_listener":"NOT_DEPLOYED",
    "approved_hostname":"PENDING",
    "server_tls_certificate":"PENDING",
    "client_ca_and_revocation":"PENDING",
    "restricted_ingress_cidrs":"PENDING",
    "qa_origin":"PENDING",
    "qa_proxy_docker_socket":"FORBIDDEN",
    "qa_proxy_direct_database_access":"FORBIDDEN",
    "qa_proxy_production_financial_network":"FORBIDDEN",
    "public_postgres_ports":"NONE",
    "qa_database":g.QA_DB,
    "qa_database_financial_write_access":"DENIED",
    "financial_apply":"LOCKED",
}


class Blocked(RuntimeError):
    """Static safe reason codes; do not emit raw packet or AWS errors."""


def require(ok, code):
    if not ok:
        raise Blocked(code)


def inspect_design(path=DESIGN):
    require(path.is_file() and not path.is_symlink(), "DESIGN_FILE_MISSING_OR_SYMLINK")
    data=path.read_bytes()
    require(1 <= len(data) <= 32768, "DESIGN_FILE_SIZE_INVALID")
    try:
        doc=json.loads(data.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise Blocked("DESIGN_FILE_INVALID_JSON") from None
    require(type(doc) is dict and set(doc)=={
        "schema","classification","deployment_authorization","isolation",
        "exact_candidate_routes","forbidden_route_prefixes",
        "external_acceptance_cases","rollback_review_steps","readiness_notes"
    }, "DESIGN_FIELDS_NOT_EXACT")
    require(doc["schema"]==SCHEMA
        and doc["classification"]=="REFERENCE_DESIGN_ONLY_NOT_DEPLOYABLE"
        and doc["deployment_authorization"]=="NOT_GRANTED",
        "DESIGN_RELEASE_BOUNDARY_CHANGED")
    require(type(doc["isolation"]) is dict and doc["isolation"]==ISOLATION,
            "DESIGN_ISOLATION_CHANGED")
    require(doc["exact_candidate_routes"]==list(EXPECTED_ROUTES),
            "DESIGN_ROUTE_ALLOWLIST_CHANGED")
    require(doc["forbidden_route_prefixes"]==list(EXPECTED_FORBIDDEN),
            "DESIGN_FINANCIAL_DENYLIST_CHANGED")
    require(doc["rollback_review_steps"]==list(EXPECTED_ROLLBACK_STEPS),
            "DESIGN_ROLLBACK_SEQUENCE_CHANGED")
    cases=doc["external_acceptance_cases"]
    require(type(cases) is list and
            cases==[{"id":item,"status":"NOT_TESTED_EXTERNAL"}
                    for item in EXPECTED_ACCEPTANCE_CASES],
            "DESIGN_EXTERNAL_E2E_STATUS_NOT_PENDING")
    notes=doc["readiness_notes"]
    require(type(notes) is list and len(notes)==6
            and all(type(note) is str and 15<=len(note)<=500
                    for note in notes),
            "DESIGN_NOTES_INVALID")
    print("DB_R31_11_4L_ISOLATION_GRAPH=PASS_DESIGN_ONLY_NO_DEPLOYMENT",flush=True)
    print("DB_R31_11_4L_METHOD_PATH_ALLOWLIST=PASS_EXACT_FIVE_ROUTES",flush=True)
    print("DB_R31_11_4L_FINANCIAL_ENDPOINTS=BLOCKED_IN_REFERENCE_DESIGN",flush=True)
    print("DB_R31_11_4L_EXTERNAL_ACCEPTANCE_CASES="+str(len(cases))+"_NOT_TESTED",flush=True)
    print("DB_R31_11_4L_ROLLBACK_REVIEW_SEQUENCE=PASS_NINE_STEPS_NOT_EXECUTED",flush=True)
    return doc


def packet_review(path):
    packet=k.read_packet(path)
    missing=k.review_packet(packet)
    # This is a declaration/completeness check, NOT verification of
    # DNS ownership, cert lifecycle, approvals or external access.
    print("DB_R31_11_4L_DEPLOYMENT_APPROVALS="+str(len(missing))+
          "_OF_23_STILL_PENDING",flush=True)
    print("DB_R31_11_4L_APPROVAL_STATUS=DECLARATIONS_ONLY_NOT_AUTHORIZED",flush=True)
    return missing


def combined_audit(sha, packet_path):
    # The 4K baseline invokes the actual pinned 4H + 4I+4J source/QA
    # checks, Firebase Admin readonly records, RLS, secret metadata,
    # PG network, existing Caddy hash and temporary-resource absence.
    k.audit_live_readonly(sha)
    inspect_design()
    packet_review(packet_path)
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "CADDY_FINGERPRINT_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4L_AFTER_COMBINED_CADDY_AND_PG=PASS_READONLY_UNCHANGED",flush=True)
    print("DB_R31_11_4L_DESIGN_REVIEW=PASS_PREPARATION_ONLY",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="4L QA-only external mTLS design review")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4L ISOLATED EXTERNAL MTLS COMBINED DESIGN REVIEW ===",
          flush=True)
    try:
        combined_audit(args.source_sha,args.packet)
        return 0
    except Blocked as exc:
        # Only static code labels emitted; no raw private data.
        allowed={
            "DESIGN_FILE_MISSING_OR_SYMLINK","DESIGN_FILE_SIZE_INVALID",
            "DESIGN_FILE_INVALID_JSON","DESIGN_FIELDS_NOT_EXACT",
            "DESIGN_RELEASE_BOUNDARY_CHANGED","DESIGN_ISOLATION_CHANGED",
            "DESIGN_ROUTE_ALLOWLIST_CHANGED","DESIGN_FINANCIAL_DENYLIST_CHANGED",
            "DESIGN_ROLLBACK_SEQUENCE_CHANGED",
            "DESIGN_EXTERNAL_E2E_STATUS_NOT_PENDING","DESIGN_NOTES_INVALID",
            "CADDY_FINGERPRINT_DRIFT"
        }
        code=str(exc)
        print("DB_R31_11_4L_BLOCK_REASON="+
              (code if code in allowed else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4L_COMBINED_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        print("DB_R31_11_4L_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4L_COMBINED_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4L_PUBLIC_CADDY=UNCHANGED_BY_THIS_PHASE",flush=True)
        print("DB_R31_11_4L_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4L_CERTIFICATE_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4L_EXPIRED_REVOKED_FIREBASE_SESSION=NOT_TESTED",flush=True)
        print("DB_R31_11_4L_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4L_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4L_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
