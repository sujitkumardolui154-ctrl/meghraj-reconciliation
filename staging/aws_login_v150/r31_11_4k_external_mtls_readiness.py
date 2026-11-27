#!/usr/bin/env python3
"""R31.11.4K — external mTLS release-packet readiness, NEVER deployment.

Combines accepted R31.11.4J read-only host/PG/Caddy/Firebase metadata and
local 4I auth receipt with strict approval-packet review. No DNS, certificate,
Caddy, network, Docker, IAM, Firebase or PostgreSQL mutations.

Even a fully reviewed packet may only report REVIEW_READY_NOT_AUTHORIZED:
live deployment and external acceptance require separate explicit approval.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True

import r31_11_4j_combined_mtls_gate as j
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

DIRECTORY = Path(__file__).resolve().parent
TEMPLATE_PACKET = DIRECTORY / "r31_11_4k_external_mtls_approval_packet.json"
TEMPLATE_CADDY = DIRECTORY / "Caddyfile.r31_11_4k_NOT_FOR_DEPLOYMENT.template"

APPROVAL_FIELDS = (
    "fqdn_owner_approved",
    "dns_control_verified",
    "qa_only_public_endpoint_scope_approved",
    "firewall_cidr_scope_approved",
    "qa_client_ca_owner_approved",
    "qa_client_cert_inventory_approved",
    "qa_client_revocation_mechanism_approved",
    "server_certificate_lifecycle_approved",
    "qa_proxy_isolation_peer_reviewed",
    "qa_proxy_config_peer_reviewed",
    "firebase_test_origin_approved",
    "finance_routes_excluded_verified",
    "rollback_owner_and_test_approved",
    "monitoring_and_alerts_approved",
    "external_negative_test_plan_approved",
    "independent_security_reviewer_approved",
)
TEXT_FIELDS = (
    "change_ticket",
    "qa_fqdn",
    "approved_source_cidrs",
    "server_certificate_provider",
    "client_ca_metadata_reference",
    "rollback_ticket",
    "external_test_owner",
)
SCHEMA = "DB-R31.11.4K-EXTERNAL-MTLS-APPROVAL-PACKET-V1"
REQUIRED = {"schema","environment","workflow_status",*APPROVAL_FIELDS,*TEXT_FIELDS}


class GateBlocked(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise GateBlocked(code)


def read_packet(path):
    # No private keys, tokens, Firebase identity IDs or credentials permitted.
    require(path.is_file() and not path.is_symlink(),
            "QA_RELEASE_PACKET_MISSING_OR_SYMLINK")
    data = path.read_bytes()
    require(1 <= len(data) <= 16384,"QA_RELEASE_PACKET_SIZE_INVALID")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise GateBlocked("QA_RELEASE_PACKET_INVALID_JSON") from None
    require(type(parsed) is dict and set(parsed) == REQUIRED,
            "QA_RELEASE_PACKET_FIELDS_INVALID")
    require(parsed["schema"] == SCHEMA
            and parsed["environment"] == "qa_isolated_external_mtls"
            and parsed["workflow_status"] in ("PENDING_APPROVAL","REVIEW_ONLY"),
            "QA_RELEASE_PACKET_CONTEXT_INVALID")
    require(all(type(parsed[k]) is bool for k in APPROVAL_FIELDS),
            "QA_RELEASE_PACKET_APPROVAL_TYPES_INVALID")
    require(all(type(parsed[k]) is str
                and 1 <= len(parsed[k]) <= 512
                for k in TEXT_FIELDS),"QA_RELEASE_PACKET_TEXT_FIELDS_INVALID")
    # Never accept strings implying secrets in text fields, even if uploaded.
    for key in TEXT_FIELDS:
        value = parsed[key]
        lower = value.lower()
        require(not any(fragment in lower for fragment in
                ("-----begin", "private key", "password=", "idtoken",
                 "sessioncookie", "apikey=", "bearer ", "firebase_uid=")),
                "QA_RELEASE_PACKET_POSSIBLE_SECRET")
    return parsed


def review_packet(packet):
    missing = [key for key in APPROVAL_FIELDS if packet[key] is not True]
    for name in TEXT_FIELDS:
        if packet[name].strip() in ("", "PENDING", "NOT_PROVIDED", "TBD"):
            missing.append(name)
    name = packet["qa_fqdn"].lower()
    if name != "pending":
        require(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{1,251}[a-z0-9])?",name)
                and "." in name and not name.endswith(".invalid")
                and not name.endswith(".local") and not name.endswith(".internal")
                and "localhost" not in name
                and "sslip.io" not in name,
                "QA_APPROVED_FQDN_INVALID_OR_TEMPORARY")
    cidrs=packet["approved_source_cidrs"]
    if cidrs!="PENDING":
        chunks=[c.strip() for c in cidrs.split(",")]
        require(0 < len(chunks) <= 8,"QA_FIREWALL_CIDR_LIST_INVALID")
        for c in chunks:
            try:
                net=ipaddress.ip_network(c,strict=True)
            except ValueError:
                raise GateBlocked("QA_FIREWALL_CIDR_LIST_INVALID") from None
            # Do not treat an unscoped public internet rule as acceptable.
            require(str(net) not in ("0.0.0.0/0","::/0"),
                    "QA_UNSCOPED_FIREWALL_RULE_NOT_APPROVED")
    # Never claim verified DNS or CA materials based solely on boolean
    # fields. This reports operator *declarations*, not remote verification.
    print("DB_R31_11_4K_APPROVAL_PACKET_SCHEMA=PASS_STRICT_NO_SECRETS",
          flush=True)
    if missing:
        print("DB_R31_11_4K_APPROVAL_PACKET=INCOMPLETE",flush=True)
        print("DB_R31_11_4K_PENDING_FIELD_COUNT="+str(len(missing)),flush=True)
        print("DB_R31_11_4K_PENDING_FIELD_NAMES="+",".join(sorted(missing)),
              flush=True)
    else:
        print("DB_R31_11_4K_APPROVAL_PACKET=DECLARED_COMPLETE_REVIEW_ONLY",
              flush=True)
        print("DB_R31_11_4K_PENDING_FIELD_COUNT=0",flush=True)
    return missing


def inspect_inactive_caddy_template():
    require(TEMPLATE_CADDY.is_file() and not TEMPLATE_CADDY.is_symlink(),
            "QA_INACTIVE_CADDY_TEMPLATE_MISSING")
    data=TEMPLATE_CADDY.read_text("utf-8")
    require(
        "DO NOT IMPORT OR DEPLOY" in data
        and "qa-r3114k.example.invalid" in data
        and "client_auth" in data
        and "mode require_and_verify" in data
        and "trust_pool file" in data
        and 'respond "QA ROUTE NOT APPROVED" 503' in data
        and "reverse_proxy" not in data
        and "file_server" not in data
        and "sbi-r31-auth-private-qa" not in data,
        "QA_CADDY_PLACEHOLDER_NOT_FAIL_CLOSED")
    print("DB_R31_11_4K_INACTIVE_CADDY_CANDIDATE=PASS_503_NO_UPSTREAM",
          flush=True)


def audit_live_readonly(source_sha):
    # Predecessor operator-reported PASS; must recheck now, not assume.
    j.audit_baseline(source_sha)
    inspect_inactive_caddy_template()
    checksum=g.caddy_preflight()
    require(checksum==h.EXPECTED_4G_CADDY_SHA256,
            "QA_CADDY_BASELINE_DRIFT")
    container=g.inspect_one("container",g.CADDY)
    mounts=container.get("Mounts") or []
    for mount in mounts:
        source=(mount.get("Source") or "").lower()
        dest=(mount.get("Destination") or "").lower()
        require(not any(s in (source,dest) for s in
                    ("/var/run/docker.sock","/run/docker.sock")),
                "QA_CADDY_DOCKER_SOCKET_MOUNT_UNSAFE")
    print("DB_R31_11_4K_RUNNING_CADDY=PASS_EXISTING_BASELINE_READONLY",
          flush=True)
    print("DB_R31_11_4K_EXTERNAL_INGRESS=NOT_DEPLOYED_BY_THIS_PHASE",
          flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4K external mTLS gate")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--packet",type=Path,default=TEMPLATE_PACKET)
    parser.add_argument("--mode",choices=("audit","packet-review"),default="audit")
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4K EXTERNAL MTLS DEPLOYMENT APPROVAL READINESS ===",
          flush=True)
    try:
        # Always run genuine read-only host/DB/Caddy + original 4I receipt,
        # no 'shortcut' mode that could permit unverified deployment review.
        audit_live_readonly(args.source_sha)
        packet=read_packet(args.packet)
        missing=review_packet(packet)
        require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
                "QA_CADDY_CHANGED_DURING_AUDIT")
        g.check_database_isolation()
        g.ephemeral_cleanup()
        print("DB_R31_11_4K_POST_AUDIT_DB_CADDY=PASS_UNCHANGED",flush=True)
        if args.mode=="packet-review" and missing:
            print("DB_R31_11_4K_RELEASE_REVIEW=WAITING_FOR_APPROVAL_PACKET",
                  flush=True)
        else:
            print("DB_R31_11_4K_RELEASE_REVIEW=NO_DEPLOYMENT_AUTHORIZATION",
                  flush=True)
        print("DB_R31_11_4K_READINESS_AUDIT=PASS_PREPARATION_ONLY",flush=True)
        return 0
    except Exception:
        # No raw cloud errors, cert strings, hostnames, Firebase UIDs, or
        # secret / configuration file content reaches output.
        print("STOP=DB_R31_11_4K_READINESS_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4K_CERT_AND_DNS_APPROVAL=NOT_ESTABLISHED_BY_SCRIPT",
              flush=True)
        print("DB_R31_11_4K_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4K_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4K_FIREBASE_EXPIRED_REVOKED_SESSION=NOT_TESTED",
              flush=True)
        print("DB_R31_11_4K_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4K_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4K_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
