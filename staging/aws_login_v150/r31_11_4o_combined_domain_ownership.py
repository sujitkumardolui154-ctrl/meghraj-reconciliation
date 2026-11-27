#!/usr/bin/env python3
"""R31.11.4O: full combined READ-ONLY QA + domain/DNS ownership evidence.

Runs the accepted 4N -> 4M -> 4L -> 4K -> 4J -> 4H security chain against
the existing private QA environment. Audits a strictly structured,
NONSECRET six-control domain ownership dossier. No evidence of domain
ownership is invented or derived from source-only CI.

This script NEVER runs dig/nslookup/curl, issues DNS records, certificates,
Firebase login tokens, exposes a port, starts an HTTP listener, deploys
Caddy, alters Docker/PG/IAM or unlocks financial Apply. Real registrar
and DNS-provider identity must be verified independently later.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True

import r31_11_4n_combined_dns_pki_preflight as n
import r31_11_4m_combined_evidence_preflight as m
import r31_11_4k_external_mtls_readiness as k
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

HERE=Path(__file__).resolve().parent
DOSSIER=HERE/"r31_11_4o_domain_ownership_dossier.json"
SCHEMA="DB-R31.11.4O-DOMAIN-OWNERSHIP-EVIDENCE-V1"
ROOT_FIELDS={
    "schema","classification","environment","deployment_authorization",
    "qa_fqdn","parent_dns_zone","source_4n_intake",
    "source_4m_register","source_4k_approval_packet",
    "evidence","security_position","warning",
}
EVIDENCE_ITEMS=(
    ("change_authorization",
     "Approved change request for QA DNS/hostname selection"),
    ("registrant_ownership",
     "Owner-authorized registrant or organizational domain entitlement proof"),
    ("dns_zone_administration",
     "Authorized DNS provider/zone administrator evidence"),
    ("authoritative_delegation",
     "Authoritative nameserver delegation evidence reference"),
    ("dns_record_change_control",
     "DNS test record change approval and controlled change evidence"),
    ("independent_owner_review",
     "Independent authorized reviewer sign-off reference"),
)
EVIDENCE_KEYS={
    "kind","purpose","state","evidence_ticket","evidence_sha256",
    "independent_review_ticket","reviewed_at_utc",
}
LOCKED_POSITION={
    "domain_registration_verified":"NOT_VERIFIED",
    "dns_delegation_verified":"NOT_VERIFIED",
    "dns_record_change_verified":"NOT_VERIFIED",
    "owner_approval_verified":"NOT_VERIFIED",
    "external_tls_test":"NOT_TESTED",
    "financial_apply":"LOCKED",
    "r3112":"ACTIVE_QA_DESIGN_RELEASE_GATED",
    "production_release":"BLOCKED",
}

class OwnershipBlocked(RuntimeError):
    """Fixed nonsecret diagnostic only."""


def require(condition,code):
    if not condition:
        raise OwnershipBlocked(code)


def check_review_time(value):
    require(m.validate_timestamp(value),"DNS_OWNER_REVIEW_TIMESTAMP_INVALID")
    instant=datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    require(instant<=datetime.now(timezone.utc)+timedelta(minutes=10),
            "DNS_OWNER_REVIEW_TIMESTAMP_IN_FUTURE")


def read_dossier(path):
    require(path.is_file() and not path.is_symlink(),
            "DNS_OWNER_DOSSIER_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    require(1 <= len(raw) <= 16384,"DNS_OWNER_DOSSIER_SIZE_INVALID")
    try:
        document=json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError):
        raise OwnershipBlocked("DNS_OWNER_DOSSIER_INVALID_JSON") from None
    require(type(document) is dict and set(document)==ROOT_FIELDS,
            "DNS_OWNER_DOSSIER_ROOT_SCHEMA_INVALID")
    require(document["schema"]==SCHEMA
            and document["classification"]=="NONSECRET_PROVENANCE_ONLY_NOT_CONTROL_PROOF"
            and document["environment"]=="qa_isolated_external_mtls"
            and document["deployment_authorization"]=="NOT_GRANTED",
            "DNS_OWNER_DOSSIER_RELEASE_SCOPE_CHANGED")
    require(document["source_4n_intake"]==n.INTAKE.name
            and document["source_4m_register"]==m.REGISTER.name
            and document["source_4k_approval_packet"]==k.TEMPLATE_PACKET.name,
            "DNS_OWNER_DOSSIER_SOURCE_REFERENCES_INVALID")
    require(document["security_position"]==LOCKED_POSITION,
            "DNS_OWNER_SECURITY_POSITION_NOT_LOCKED")
    warning=document["warning"]
    require(type(warning) is str and 100<=len(warning)<=350
            and "do not prove ownership" in warning,
            "DNS_OWNER_DOSSIER_WARNING_CHANGED")
    host=document["qa_fqdn"]
    zone=document["parent_dns_zone"]
    require(type(host) is str and type(zone) is str,
            "DNS_OWNER_HOST_ZONE_TYPE_INVALID")
    if host=="PENDING":
        require(zone=="PENDING","DNS_OWNER_ZONE_WITHOUT_HOST")
    else:
        require(host==host.lower() and n.valid_name(host),
                "DNS_OWNER_HOST_NOT_ALLOWED")
        require(zone==zone.lower() and n.valid_name(zone)
                and host.endswith("."+zone),
                "DNS_OWNER_ZONE_NOT_PARENT")

    evidence=document["evidence"]
    require(type(evidence) is list and len(evidence)==len(EVIDENCE_ITEMS),
            "DNS_OWNER_EVIDENCE_ITEM_COUNT_CHANGED")
    counts={n.PENDING:0,n.REFERENCED:0,n.REVIEWED:0}
    for item,(kind,purpose) in zip(evidence,EVIDENCE_ITEMS):
        require(type(item) is dict and set(item)==EVIDENCE_KEYS
                and item["kind"]==kind and item["purpose"]==purpose,
                "DNS_OWNER_EVIDENCE_ITEM_SCHEMA_CHANGED")
        state=item["state"]
        require(type(state) is str and state in counts,
                "DNS_OWNER_EVIDENCE_STATUS_UNSUPPORTED")
        ticket=item["evidence_ticket"]
        digest=item["evidence_sha256"]
        reviewer=item["independent_review_ticket"]
        reviewed=item["reviewed_at_utc"]
        if state==n.PENDING:
            require(ticket==digest==reviewer==reviewed=="PENDING",
                    "DNS_OWNER_PENDING_ITEM_CONTAINS_CLAIM")
        elif state==n.REFERENCED:
            require(m.ticket_ok(ticket) and type(digest) is str
                    and m.HEX_PATTERN.fullmatch(digest) is not None
                    and reviewer=="PENDING" and reviewed=="PENDING",
                    "DNS_OWNER_REFERENCED_METADATA_INVALID")
        else:
            require(m.ticket_ok(ticket) and m.ticket_ok(reviewer)
                    and ticket!=reviewer and type(digest) is str
                    and m.HEX_PATTERN.fullmatch(digest) is not None,
                    "DNS_OWNER_REVIEW_METADATA_INVALID")
            check_review_time(reviewed)
        counts[state]+=1
    return document,counts


def correlate_with_4n(dossier, intake_path):
    """Identical proposed hostname + zone must agree across 4O and 4N."""
    intake,_=n.validate_intake(intake_path)
    require(dossier["qa_fqdn"]==intake["qa_hostname"]
            and dossier["parent_dns_zone"]==intake["dns_zone"],
            "DNS_OWNER_FQDN_NOT_LINKED_TO_4N")
    # Prevent use of a made-up 4O proof while all original 4N/4M
    # evidence remains PENDING. A metadata-referenced status is never an
    # approved domain; it requires corresponding 4N references.
    corresponding={
        "change_authorization":"change_ticket",
        "registrant_ownership":"fqdn_owner_approved",
        "dns_zone_administration":"dns_control_verified",
        "authoritative_delegation":"dns_control_verified",
        "dns_record_change_control":"dns_control_verified",
        "independent_owner_review":"fqdn_owner_approved",
    }
    by_field={item["field"]:item for item in intake["items"]}
    for item in dossier["evidence"]:
        source=by_field[corresponding[item["kind"]]]
        if item["state"]!=n.PENDING:
            require(source["state"]!=n.PENDING,
                    "DNS_OWNER_EVIDENCE_NOT_LINKED_TO_4N_REFERENCES")


def full_combined_preflight(sha,dossier_path,intake_path,register_path,packet_path):
    dossier,counts=read_dossier(dossier_path)
    correlate_with_4n(dossier,intake_path)
    print("DB_R31_11_4O_DOMAIN_DOSSIER=PASS_STRICT_SIX_GATES_NO_SECRETS",
          flush=True)
    print("DB_R31_11_4O_OWNER_EVIDENCE_PENDING="+str(counts[n.PENDING]),flush=True)
    print("DB_R31_11_4O_OWNER_EVIDENCE_REFERENCED_UNVERIFIED="+str(counts[n.REFERENCED]),
          flush=True)
    print("DB_R31_11_4O_OWNER_METADATA_REVIEWED_NOT_APPROVED="+str(counts[n.REVIEWED]),
          flush=True)
    print("DB_R31_11_4O_QA_HOSTNAME="+
          ("NOT_PROVIDED" if dossier["qa_fqdn"]=="PENDING" else "PROPOSED_ONLY"),
          flush=True)

    # The existing 4N pipeline re-evaluates real QA source commit, PG16
    # role grants/RLS, Firebase Admin account records, secret metadata,
    # owner receipt, Caddy SHA, zero financial source rows and no leftovers.
    n.run_combined(sha,intake_path,register_path,packet_path)
    print("DB_R31_11_4O_4N_THROUGH_4H_COMBINED_QA=PASS_READONLY",flush=True)

    # Guard against unauthorized infrastructure drift during the full run.
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "DNS_OWNER_CADDY_BASELINE_CHANGED")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4O_AFTER_QA_CADDY_PG=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4O_REGISTRANT_AUTHORITY=NOT_INDEPENDENTLY_VERIFIED",flush=True)
    print("DB_R31_11_4O_ZONE_DELEGATION=NOT_INDEPENDENTLY_VERIFIED",flush=True)
    print("DB_R31_11_4O_DNS_CHANGE_RIGHTS=NOT_INDEPENDENTLY_VERIFIED",flush=True)
    print("DB_R31_11_4O_DOMAIN_OWNER_APPROVAL=NOT_ESTABLISHED",flush=True)
    print("DB_R31_11_4O_COMBINED_DOMAIN_PREFLIGHT=PASS_PREPARATION_ONLY",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4O domain ownership evidence QA")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--dossier",type=Path,default=DOSSIER)
    parser.add_argument("--intake",type=Path,default=n.INTAKE)
    parser.add_argument("--register",type=Path,default=m.REGISTER)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4O FULL COMBINED DOMAIN/DNS OWNER EVIDENCE ===",flush=True)
    try:
        full_combined_preflight(args.source_sha,args.dossier,args.intake,
                                args.register,args.packet)
        return 0
    except OwnershipBlocked as exc:
        allowed={
            "DNS_OWNER_DOSSIER_MISSING_OR_SYMLINK",
            "DNS_OWNER_DOSSIER_SIZE_INVALID",
            "DNS_OWNER_DOSSIER_INVALID_JSON",
            "DNS_OWNER_DOSSIER_ROOT_SCHEMA_INVALID",
            "DNS_OWNER_DOSSIER_RELEASE_SCOPE_CHANGED",
            "DNS_OWNER_DOSSIER_SOURCE_REFERENCES_INVALID",
            "DNS_OWNER_SECURITY_POSITION_NOT_LOCKED",
            "DNS_OWNER_DOSSIER_WARNING_CHANGED",
            "DNS_OWNER_HOST_ZONE_TYPE_INVALID",
            "DNS_OWNER_ZONE_WITHOUT_HOST",
            "DNS_OWNER_HOST_NOT_ALLOWED",
            "DNS_OWNER_ZONE_NOT_PARENT",
            "DNS_OWNER_EVIDENCE_ITEM_COUNT_CHANGED",
            "DNS_OWNER_EVIDENCE_ITEM_SCHEMA_CHANGED",
            "DNS_OWNER_EVIDENCE_STATUS_UNSUPPORTED",
            "DNS_OWNER_PENDING_ITEM_CONTAINS_CLAIM",
            "DNS_OWNER_REFERENCED_METADATA_INVALID",
            "DNS_OWNER_REVIEW_METADATA_INVALID",
            "DNS_OWNER_REVIEW_TIMESTAMP_INVALID",
            "DNS_OWNER_REVIEW_TIMESTAMP_IN_FUTURE",
            "DNS_OWNER_FQDN_NOT_LINKED_TO_4N",
            "DNS_OWNER_EVIDENCE_NOT_LINKED_TO_4N_REFERENCES",
            "DNS_OWNER_CADDY_BASELINE_CHANGED",
        }
        reason=str(exc)
        print("DB_R31_11_4O_BLOCK_REASON="+
              (reason if reason in allowed else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4O_DOMAIN_EVIDENCE_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        # Cloud/SQL/credential exceptions must not be printed.
        print("DB_R31_11_4O_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4O_DOMAIN_EVIDENCE_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4O_REAL_DNS_OWNER_VERIFICATION=NOT_PERFORMED",flush=True)
        print("DB_R31_11_4O_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4O_EXTERNAL_ACCEPTANCE_22=NOT_TESTED",flush=True)
        print("DB_R31_11_4O_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4O_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4O_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
