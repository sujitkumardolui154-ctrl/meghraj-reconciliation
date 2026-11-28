#!/usr/bin/env python3
"""DB-R31.11.4Q — read-only QA ingress and proxy isolation acceptance PREP.

Combines R31.11.4P→4O→4N→4M→4L→4K→4J→4H, then validates a
nondeployable proxy isolation policy, 13 related unchanged pending approval
fields and simulated method/path/auth decisions. Verifies existing Caddy
is not joined to the QA PG network, and rechecks original Caddy fingerprint.

No real HTTP listener, Caddy change, Docker build/run, DNS, certificate,
firewall opening, database mutation, Firebase sign-in or financial Apply.
CI uses mocks for every AWS/database call; AWS operator run is read-only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True

import r31_11_4p_combined_pki_preflight as p
import r31_11_4l_combined_design_gate as l
import r31_11_4k_external_mtls_readiness as k
import r31_11_4m_combined_evidence_preflight as m
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

FILE=Path(__file__).resolve().with_name("r31_11_4q_ingress_isolation_policy.json")
SCHEMA="DB-R31.11.4Q-QA-INGRESS-ISOLATION-V1"
GATES=(
 "RESTRICTED_SOURCE_CIDRS",
 "SEPARATE_QA_PROXY_WITH_NO_PUBLIC_CADDY_CHANGE",
 "QA_HOSTNAME_DNS_AND_CLIENT_CA_APPROVED",
 "MTLS_REQUIRE_AND_VERIFY_AT_QA_EDGE",
 "SNI_HOST_MATCH_ENFORCED",
 "REJECT_UNTRUSTED_CLIENT_IP_FORWARDED_HEADERS",
 "DROP_FORGED_UID_ROLE_AND_CERT_IDENTITY_HEADERS",
 "EXACT_METHOD_AND_PATH_ALLOWLIST",
 "FIREBASE_SIGNED_SESSION_IN_QA_ADAPTER",
 "SESSION_ORIGIN_AND_CSRF_GUARDS",
 "PRODUCTION_FINANCIAL_ROUTES_DENIED",
 "NO_PROXY_DIRECT_PG_OR_PRODUCTION_FINANCIAL_NETWORK",
 "RATE_LIMITS_AND_SAFE_AUDIT_LOGS",
 "APPROVED_ROLLBACK_AND_INDEPENDENT_REVIEW",
)
AUTH_GATES=(
 "MTLS_ONLY","MTLS_ONLY","MTLS_ORIGIN_CSRF_REQUIRED",
 "MTLS_FIREBASE_SESSION_REQUIRED","MTLS_FIREBASE_SESSION_REQUIRED"
)
ROUTES=tuple(
 {"method":record.split(" ",1)[0],
  "path":record.split(" ",1)[1],
  "auth_gate":guard,
  "status":"PROPOSED_NOT_EXPOSED"}
 for record,guard in zip(l.EXPECTED_ROUTES,AUTH_GATES)
)
APPROVAL_FIELDS=(
 "qa_only_public_endpoint_scope_approved",
 "firewall_cidr_scope_approved",
 "qa_proxy_isolation_peer_reviewed",
 "qa_proxy_config_peer_reviewed",
 "firebase_test_origin_approved",
 "finance_routes_excluded_verified",
 "rollback_owner_and_test_approved",
 "monitoring_and_alerts_approved",
 "external_negative_test_plan_approved",
 "independent_security_reviewer_approved",
 "approved_source_cidrs",
 "rollback_ticket",
 "external_test_owner",
)
TOPOLOGY={
 "public_caddy":"UNCHANGED_SHA256_"+h.EXPECTED_4G_CADDY_SHA256,
 "dedicated_qa_proxy":"NOT_DEPLOYED",
 "dedicated_qa_http_adapter":"NOT_DEPLOYED",
 "qa_hostname":"PENDING",
 "approved_source_cidrs":"PENDING",
 "client_ca":"NOT_APPROVED",
 "tls_listener":"NOT_DEPLOYED",
 "qa_postgres":"PRIVATE_INTERNAL_NO_PUBLISHED_PORTS",
 "qa_proxy_docker_socket":"FORBIDDEN",
 "qa_proxy_direct_postgres":"FORBIDDEN",
 "qa_proxy_production_financial_network":"FORBIDDEN",
 "financial_apply":"LOCKED",
}
LOG_POLICY={
 "permitted_fields":[
  "timestamp_utc","event_code","correlation_id","method","route_template","decision"
 ],
 "prohibited_fields":[
  "Authorization","Cookie","Set-Cookie","X-Firebase-UID","X-DB-Role",
  "X-Forwarded-For","client_certificate_PEM","client_private_key",
  "firebase_id_token","email","raw_ip"
 ],
 "status":"NOT_IMPLEMENTED_OR_TESTED",
}
ACCEPTANCE={
 "external_case_count":22,
 "external_cases":"NOT_TESTED",
 "actual_remote_mtls":"NOT_TESTED",
 "actual_rate_limit_and_logging":"NOT_TESTED",
 "real_firebase_session_expiry_revocation":"NOT_TESTED",
 "client_certificate_revocation":"NOT_TESTED",
 "qa_ingress_firewall":"NOT_DEPLOYED",
}
ROOT={
 "schema","classification","deployment_authorization","topology",
 "controls","routes","forbidden_prefixes","logging_policy",
 "rollback","linked_approval_requirements","acceptance",
 "r3112","financial_apply","production_release","notice"
}

class IngressBlocked(RuntimeError):
    """Safe status only: never expose AWS metadata, tokens or Caddy contents."""


def require(ok,code):
    if not ok:
        raise IngressBlocked(code)


def validate_design(path=FILE):
    require(path.is_file() and not path.is_symlink(),"Q_POLICY_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    require(1<=len(raw)<=32768,"Q_POLICY_SIZE_INVALID")
    try:
        d=json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError):
        raise IngressBlocked("Q_POLICY_INVALID_JSON") from None
    require(type(d) is dict and set(d)==ROOT,"Q_POLICY_FIELDS_CHANGED")
    require(d["schema"]==SCHEMA
            and d["classification"]=="NONDEPLOYABLE_SECURITY_DESIGN_ONLY"
            and d["deployment_authorization"]=="NOT_GRANTED"
            and d["r3112"]=="ACTIVE_QA_DESIGN_RELEASE_GATED"
            and d["financial_apply"]=="LOCKED"
            and d["production_release"]=="BLOCKED",
            "Q_POLICY_RELEASE_BOUNDARY_CHANGED")
    require(type(d["topology"]) is dict and d["topology"]==TOPOLOGY,
            "Q_POLICY_TOPOLOGY_CHANGED")
    require(d["controls"]==[
        {"id":name,"status":"DESIGN_REQUIRED_NOT_ACCEPTED"} for name in GATES],
        "Q_POLICY_SECURITY_CONTROLS_CHANGED")
    require(d["routes"]==list(ROUTES),"Q_POLICY_ROUTE_ALLOWLIST_CHANGED")
    require(d["forbidden_prefixes"]==list(l.EXPECTED_FORBIDDEN),
            "Q_POLICY_FINANCIAL_ROUTE_DENYLIST_CHANGED")
    require(d["logging_policy"]==LOG_POLICY,
            "Q_POLICY_LOG_SAFETY_CHANGED")
    require(d["rollback"]==[
        {"id":name,"status":"NOT_EXECUTED"} for name in l.EXPECTED_ROLLBACK_STEPS],
        "Q_POLICY_ROLLBACK_STATUS_CHANGED")
    require(d["linked_approval_requirements"]==[
        {"field":name,"status":"PENDING"} for name in APPROVAL_FIELDS],
        "Q_POLICY_APPROVALS_NOT_PENDING")
    require(type(d["acceptance"]) is dict and d["acceptance"]==ACCEPTANCE,
            "Q_POLICY_EXTERNAL_TEST_STATUS_CHANGED")
    require(type(d["notice"]) is str
            and "offline design" in d["notice"]
            and "not a Caddy configuration" in d["notice"]
            and len(d["notice"])<=300,
            "Q_POLICY_DISCLAIMER_REMOVED")
    print("DB_R31_11_4Q_INGRESS_POLICY=PASS_NONDEPLOYABLE_14_GATES",flush=True)
    print("DB_R31_11_4Q_ROUTE_POLICY=PASS_EXACT_FIVE_METHOD_PATH_PAIRS",flush=True)
    print("DB_R31_11_4Q_AUDIT_LOG_POLICY=PASS_NO_SECRET_FIELDS_DESIGN_ONLY",flush=True)
    print("DB_R31_11_4Q_ROLLBACK=9_STEPS_REVIEW_ONLY_NOT_EXECUTED",flush=True)
    return d


def check_approvals(packet_path=k.TEMPLATE_PACKET,register_path=m.REGISTER):
    original=k.read_packet(packet_path)
    register=m.read_register(register_path)
    require(original["workflow_status"]=="PENDING_APPROVAL"
            and all(original[key] is False for key in k.APPROVAL_FIELDS)
            and all(original[key]=="PENDING" for key in k.TEXT_FIELDS),
            "Q_ORIGINAL_4K_PACKET_WAS_CHANGED")
    require(register=={m.PENDING:23,m.SUBMITTED:0,m.REVIEWED:0},
            "Q_ORIGINAL_4M_REGISTER_WAS_CHANGED")
    print("DB_R31_11_4Q_INGRESS_RELATED_APPROVALS=13_OF_13_PENDING_WITHIN_23",flush=True)
    print("DB_R31_11_4Q_ALL_EXTERNAL_APPROVALS=23_OF_23_PENDING",flush=True)


# Pure offline policy decision only. No live Caddy/HTTP route is configured.
REQUIRED_REQUEST_KEYS={
 "method","path","client_cert_verified","peer_ip_in_approved_range",
 "sni_host_match","identity_headers_absent",
 "firebase_session_valid","origin_and_csrf_valid"
}


def allow_synthetic_request(req):
    """Fail-closed policy simulation, NOT live authentication/TLS acceptance.

    A synthetic client_cert_verified=True is a test fixture, not a
    certificate. A synthetic firebase_session_valid=True is not verified
    Firebase JWT, session cookie or real authentication. Caller-supplied
    headers are never trusted by the real adapter; no real adapter exists.
    """
    if type(req) is not dict or set(req)!=REQUIRED_REQUEST_KEYS:
        return False
    if type(req["method"]) is not str or type(req["path"]) is not str:
        return False
    for key in (
        "client_cert_verified","peer_ip_in_approved_range",
        "sni_host_match","identity_headers_absent",
        "firebase_session_valid","origin_and_csrf_valid"
    ):
        if type(req[key]) is not bool:
            return False
    if not all(req[k] is True for k in (
            "client_cert_verified","peer_ip_in_approved_range",
            "sni_host_match","identity_headers_absent")):
        return False
    match=next((route for route in ROUTES
                if route["method"]==req["method"]
                and route["path"]==req["path"]),None)
    if match is None:
        return False
    gate=match["auth_gate"]
    if gate=="MTLS_ORIGIN_CSRF_REQUIRED" and not req["origin_and_csrf_valid"]:
        return False
    if gate=="MTLS_FIREBASE_SESSION_REQUIRED" and not req["firebase_session_valid"]:
        return False
    return True


def simulate():
    clean={
      "method":"GET","path":"/healthz",
      "client_cert_verified":True,"peer_ip_in_approved_range":True,
      "sni_host_match":True,"identity_headers_absent":True,
      "firebase_session_valid":False,"origin_and_csrf_valid":False,
    }
    for route in ROUTES:
        trial=dict(clean,method=route["method"],path=route["path"])
        if route["auth_gate"]=="MTLS_FIREBASE_SESSION_REQUIRED":
            trial["firebase_session_valid"]=True
        if route["auth_gate"]=="MTLS_ORIGIN_CSRF_REQUIRED":
            trial["origin_and_csrf_valid"]=True
        require(allow_synthetic_request(trial),"Q_SIMULATION_EXPECTED_ROUTE_DENIED")
    negatives=[
      dict(clean,client_cert_verified=False),
      dict(clean,peer_ip_in_approved_range=False),
      dict(clean,sni_host_match=False),
      dict(clean,identity_headers_absent=False),
      dict(clean,method="POST",path="/healthz"),
      dict(clean,method="HEAD"),
      dict(clean,path="/admin"),
      dict(clean,path="/api/gst"),
      dict(clean,path="/api/payment-evidence"),
      dict(clean,path="/auth//csrf"),
      dict(clean,path="/auth/%63srf"),
      dict(clean,path="/auth/csrf/"),
      dict(clean,path="/api/r31-private-qa/tenant-rls-source-r3114",
           firebase_session_valid=False),
      dict(clean,method="POST",path="/auth/session",origin_and_csrf_valid=False),
      dict(clean,method="GET",path="/auth/me",firebase_session_valid=False),
    ]
    for request in negatives:
        require(not allow_synthetic_request(request),"Q_SIMULATION_UNSAFE_ROUTE_ALLOWED")
    print("DB_R31_11_4Q_SIMULATED_ROUTES=PASS_FIVE_ALLOW_FIFTEEN_DENY",flush=True)
    print("DB_R31_11_4Q_REAL_HTTP_PROXY=NOT_DEPLOYED",flush=True)


def inspect_running_proxy_metadata():
    # Existing public Caddy is NOT the 4Q test proxy.
    existing=g.inspect_one("container",g.CADDY)
    host=existing.get("HostConfig") or {}
    networks=(existing.get("NetworkSettings") or {}).get("Networks") or {}
    mounts=existing.get("Mounts") or []
    require(existing.get("State",{}).get("Running") is True
            and host.get("Privileged") is False,
            "Q_EXISTING_CADDY_RUNTIME_CHANGED")
    require(type(networks) is dict and g.QA_NETWORK not in networks,
            "Q_EXISTING_CADDY_JOINED_QA_POSTGRES_NETWORK")
    require(type(mounts) is list,"Q_EXISTING_CADDY_MOUNTS_INVALID")
    for entry in mounts:
        require(type(entry) is dict,"Q_EXISTING_CADDY_MOUNTS_INVALID")
        for value in (entry.get("Source"),entry.get("Destination")):
            if type(value) is str:
                require(value not in (
                  "/var/run/docker.sock","/run/docker.sock"
                ),"Q_CADDY_DOCKER_SOCKET_MOUNTED")
    print("DB_R31_11_4Q_EXISTING_CADDY_PROXY_ISOLATION=PASS_READONLY_METADATA",flush=True)
    print("DB_R31_11_4Q_NEW_QA_PROXY=NOT_DEPLOYED_BY_4Q",flush=True)


def full_combined_preflight(source_sha,policy_path,packet_path,register_path):
    validate_design(policy_path)
    check_approvals(packet_path,register_path)
    simulate()
    p.combined(source_sha,p.PLAN,packet_path,register_path,
               p.n.INTAKE,p.o.DOSSIER)
    print("DB_R31_11_4Q_4P_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY",flush=True)
    inspect_running_proxy_metadata()
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "Q_PUBLIC_CADDY_HASH_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4Q_AFTER_QA_DB_AND_CADDY=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4Q_COMBINED_INGRESS_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4Q read-only ingress QA")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--policy",type=Path,default=FILE)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    parser.add_argument("--register",type=Path,default=m.REGISTER)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4Q COMBINED RESTRICTED INGRESS SECURITY QA ===",flush=True)
    try:
        full_combined_preflight(args.source_sha,args.policy,args.packet,args.register)
        return 0
    except IngressBlocked as exc:
        allowed={
          "Q_POLICY_MISSING_OR_SYMLINK","Q_POLICY_SIZE_INVALID",
          "Q_POLICY_INVALID_JSON","Q_POLICY_FIELDS_CHANGED",
          "Q_POLICY_RELEASE_BOUNDARY_CHANGED",
          "Q_POLICY_TOPOLOGY_CHANGED","Q_POLICY_SECURITY_CONTROLS_CHANGED",
          "Q_POLICY_ROUTE_ALLOWLIST_CHANGED",
          "Q_POLICY_FINANCIAL_ROUTE_DENYLIST_CHANGED",
          "Q_POLICY_LOG_SAFETY_CHANGED","Q_POLICY_ROLLBACK_STATUS_CHANGED",
          "Q_POLICY_APPROVALS_NOT_PENDING","Q_POLICY_EXTERNAL_TEST_STATUS_CHANGED",
          "Q_POLICY_DISCLAIMER_REMOVED","Q_ORIGINAL_4K_PACKET_WAS_CHANGED",
          "Q_ORIGINAL_4M_REGISTER_WAS_CHANGED",
          "Q_SIMULATION_EXPECTED_ROUTE_DENIED","Q_SIMULATION_UNSAFE_ROUTE_ALLOWED",
          "Q_EXISTING_CADDY_RUNTIME_CHANGED",
          "Q_EXISTING_CADDY_JOINED_QA_POSTGRES_NETWORK",
          "Q_EXISTING_CADDY_MOUNTS_INVALID",
          "Q_CADDY_DOCKER_SOCKET_MOUNTED","Q_PUBLIC_CADDY_HASH_DRIFT",
        }
        code=str(exc)
        print("DB_R31_11_4Q_BLOCK_REASON="+(
              code if code in allowed else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4Q_COMBINED_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        # Sensitive cloud/SQL/Docker configuration is never printed.
        print("DB_R31_11_4Q_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4Q_COMBINED_SECURITY_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4Q_INGRESS_CIDR_AND_FIREWALL=NOT_APPROVED_OR_DEPLOYED",flush=True)
        print("DB_R31_11_4Q_REAL_QA_MTLS_ENDPOINT=NOT_DEPLOYED",flush=True)
        print("DB_R31_11_4Q_EXTERNAL_ACCEPTANCE=22_NOT_TESTED",flush=True)
        print("DB_R31_11_4Q_REAL_CLIENT_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4Q_REAL_FIREBASE_SESSION_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4Q_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4Q_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4Q_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
