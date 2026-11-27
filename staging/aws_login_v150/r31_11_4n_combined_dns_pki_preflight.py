#!/usr/bin/env python3
"""R31.11.4N — DNS/PKI evidence intake + 4M combined READ-ONLY QA.

Checks ten DNS/CA/certificate-related approval references without inventing
domain ownership, issuing certificates, opening a TLS listener or treating
a metadata 'reviewed' state as genuine security approval.

All actual AWS security checks are delegated to 4M (read-only private
PG16/Firebase approved user *metadata*/Caddy source and checksum). No
secrets, email/UID or private keys are read by the 4N evidence validator.
No network DNS queries, file writes, Docker changes, Firebase sign-ins,
PKI mutation, Caddy reload, IAM changes or financial Apply.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True

import r31_11_4m_combined_evidence_preflight as m
import r31_11_4k_external_mtls_readiness as k
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

HERE=Path(__file__).resolve().parent
INTAKE=HERE/"r31_11_4n_dns_pki_evidence_intake.json"
SCHEMA="DB-R31.11.4N-DNS-PKI-EVIDENCE-INTAKE-V1"
FIELDS=(
    "change_ticket","qa_fqdn","fqdn_owner_approved",
    "dns_control_verified","qa_client_ca_owner_approved",
    "qa_client_cert_inventory_approved",
    "qa_client_revocation_mechanism_approved",
    "server_certificate_lifecycle_approved","server_certificate_provider",
    "client_ca_metadata_reference",
)
PENDING="PENDING"
REFERENCED="REFERENCED_UNVERIFIED"
REVIEWED="METADATA_REVIEWED_NOT_APPROVED"
STATES={PENDING,REFERENCED,REVIEWED}
ITEM_KEYS={
    "field","state","evidence_ticket","evidence_sha256",
    "reviewer_ticket","reviewed_at_utc",
}
ROOT_KEYS={
    "schema","classification","environment","qa_hostname","dns_zone",
    "source_4m_register","source_4k_packet",
    "release_authorization","items","warning",
}
RESTRICTED_SUFFIXES=(".invalid",".localhost",".local",".internal",".test",
                     ".example")
DNS_LABEL=re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PROTECTED_MESSAGE="DO_NOT_EQUATE_REFERENCES_TO_SECURITY_APPROVAL"


class IntakeBlocked(RuntimeError):
    """Fixed non-sensitive status codes only."""


def need(test,code):
    if not test:
        raise IntakeBlocked(code)


def valid_name(name):
    if type(name) is not str or len(name)<5 or len(name)>253:
        return False
    name=name.lower()
    if ("*" in name or ":" in name or "/" in name
        or "sslip.io" in name or "nip.io" in name or
        any(name.endswith(suffix) for suffix in RESTRICTED_SUFFIXES)):
        return False
    try:
        ipaddress.ip_address(name)
        return False
    except ValueError:
        pass
    parts=name.split(".")
    return (len(parts)>=2
            and all(DNS_LABEL.fullmatch(label) is not None for label in parts)
            and not parts[-1].isdigit())


def validate_host_zone(doc):
    host=doc["qa_hostname"]
    zone=doc["dns_zone"]
    need(type(host) is str and type(zone) is str,
         "QA_HOSTNAME_ZONE_TYPE_INVALID")
    if host==PENDING:
        need(zone==PENDING,"QA_ZONE_CANNOT_BE_DEFINED_WITHOUT_QA_FQDN")
        return False
    need(valid_name(host) and host==host.lower(),
         "QA_PROPOSED_FQDN_INVALID")
    need(zone==PENDING or
         (valid_name(zone) and zone==zone.lower()
          and host.endswith("."+zone)),
         "QA_DNS_ZONE_NOT_PARENT_OF_QA_FQDN")
    return True


def validate_intake(path):
    need(path.is_file() and not path.is_symlink(),
         "QA_INTAKE_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    need(1<=len(raw)<=24576,"QA_INTAKE_SIZE_INVALID")
    try:
        doc=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise IntakeBlocked("QA_INTAKE_INVALID_JSON") from None
    need(type(doc) is dict and set(doc)==ROOT_KEYS,
         "QA_INTAKE_ROOT_SCHEMA_CHANGED")
    need(doc["schema"]==SCHEMA
         and doc["classification"]=="NONSECRET_REVIEW_METADATA_NOT_APPROVAL"
         and doc["environment"]=="qa_isolated_external_mtls"
         and doc["release_authorization"]=="NOT_GRANTED"
         and doc["source_4m_register"]=="r31_11_4m_evidence_register.json"
         and doc["source_4k_packet"]=="r31_11_4k_external_mtls_approval_packet.json",
         "QA_INTAKE_RELEASE_SCOPE_CHANGED")
    need(type(doc["warning"]) is str
         and 70<=len(doc["warning"])<=350
         and "NOT been independently verified" in doc["warning"],
         "QA_INTAKE_WARNING_CHANGED")
    host_proposed=validate_host_zone(doc)
    items=doc["items"]
    need(type(items) is list and len(items)==len(FIELDS),
         "QA_INTAKE_ITEM_COUNT_CHANGED")
    need([x.get("field") if type(x) is dict else None for x in items]
         ==list(FIELDS),"QA_INTAKE_FIELDS_NOT_EXACT")
    counts={PENDING:0,REFERENCED:0,REVIEWED:0}
    for item in items:
        need(type(item) is dict and set(item)==ITEM_KEYS,
             "QA_INTAKE_ITEM_SCHEMA_CHANGED")
        state=item["state"]
        need(type(state) is str and state in STATES,
             "QA_INTAKE_UNKNOWN_EVIDENCE_STATE")
        ev=item["evidence_ticket"]
        digest=item["evidence_sha256"]
        review=item["reviewer_ticket"]
        at=item["reviewed_at_utc"]
        if state==PENDING:
            need(ev==digest==review==at==PENDING,
                 "QA_INTAKE_PENDING_WITH_UNVERIFIED_VALUES")
        elif state==REFERENCED:
            need(m.ticket_ok(ev) and type(digest) is str
                 and m.HEX_PATTERN.fullmatch(digest) is not None
                 and review==PENDING and at==PENDING,
                 "QA_INTAKE_REFERENCE_METADATA_INVALID")
        else:
            need(m.ticket_ok(ev) and m.ticket_ok(review)
                 and ev!=review and type(digest) is str
                 and m.HEX_PATTERN.fullmatch(digest) is not None
                 and m.validate_timestamp(at),
                 "QA_INTAKE_REVIEW_METADATA_INVALID")
            instant=datetime.strptime(at,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            need(instant<=datetime.now(timezone.utc)+timedelta(minutes=10),
                 "QA_INTAKE_REVIEW_TIMESTAMP_IN_FUTURE")
        counts[state]+=1
    need(not host_proposed or doc["qa_hostname"]!=doc["dns_zone"],
         "QA_ZONE_MATCHES_HOST_UNEXPECTEDLY")
    return doc,counts


def check_predecessor_register(intake,register_path,packet_path):
    # Parse and compare *every* overlapping field with 4M, never promote
    # submitted evidence metadata into approved 4K fields or client trust.
    m.read_register(register_path)
    raw=json.loads(register_path.read_text("utf-8"))
    originals={entry["field"]:entry for entry in raw["entries"]}
    for item in intake["items"]:
        source=originals[item["field"]]
        prior=source["status"]
        current=item["state"]
        if current==PENDING:
            need(prior==m.PENDING,"QA_INTAKE_PRIOR_REGISTER_STATUS_CONFLICT")
        elif prior!=m.PENDING:
            need(item["evidence_ticket"]==source["evidence_ticket"]
                 and item["evidence_sha256"]==source["evidence_sha256"],
                 "QA_INTAKE_EVIDENCE_TICKET_HASH_CONFLICT")
            if prior==m.REVIEWED:
                need(current==REVIEWED
                     and item["reviewer_ticket"]==source["review_ticket"]
                     and item["reviewed_at_utc"]==source["reviewed_at_utc"],
                     "QA_INTAKE_REVIEW_METADATA_CONFLICT")
            else:
                need(current in (REFERENCED,REVIEWED),
                     "QA_INTAKE_REVIEW_METADATA_CONFLICT")
    # Original 4K packet remains unapproved until independent external
    # evidence validation with owner authorization in a future stage.
    packet=k.read_packet(packet_path)
    need(packet["workflow_status"]=="PENDING_APPROVAL"
         and all(packet[field] is False for field in k.APPROVAL_FIELDS)
         and all(packet[field]==PENDING for field in k.TEXT_FIELDS),
         "QA_4K_PACKET_UNEXPECTED_APPROVAL_CHANGE")


def run_combined(sha, intake_path, register_path, packet_path):
    m.combined_preflight(sha,register_path,packet_path)
    print("DB_R31_11_4N_4M_COMBINED_SECURITY=PASS_READONLY",flush=True)
    intake,counts=validate_intake(intake_path)
    check_predecessor_register(intake,register_path,packet_path)
    print("DB_R31_11_4N_DNS_PKI_INTAKE_SCHEMA=PASS_EXACT_TEN_FIELDS",flush=True)
    print("DB_R31_11_4N_EVIDENCE_PENDING="+str(counts[PENDING]),flush=True)
    print("DB_R31_11_4N_EVIDENCE_REFERENCED_UNVERIFIED="+str(counts[REFERENCED]),
          flush=True)
    print("DB_R31_11_4N_METADATA_REVIEWED_NOT_APPROVED="+str(counts[REVIEWED]),
          flush=True)
    print("DB_R31_11_4N_QA_HOSTNAME="+
          ("PROPOSED_UNVERIFIED" if intake["qa_hostname"]!=PENDING
           else "NOT_PROVIDED"),flush=True)
    print("DB_R31_11_4N_DNS_OWNERSHIP=NOT_INDEPENDENTLY_VERIFIED",flush=True)
    print("DB_R31_11_4N_CERT_ISSUANCE_AND_REVOCATION=NOT_VERIFIED",flush=True)
    need(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
         "QA_CADDY_FINGERPRINT_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4N_AFTER_QA_DB_CADDY=PASS_READONLY_UNCHANGED",flush=True)
    print("DB_R31_11_4N_COMBINED_EVIDENCE_PREFLIGHT=PASS_NO_DEPLOY",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4N QA DNS/PKI evidence intake")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--intake",type=Path,default=INTAKE)
    parser.add_argument("--register",type=Path,default=m.REGISTER)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4N QA HOSTNAME DNS CERTIFICATE EVIDENCE ===",flush=True)
    try:
        run_combined(args.source_sha,args.intake,args.register,args.packet)
        return 0
    except IntakeBlocked as exc:
        # All source-derived errors use fixed enumerated, nonsecret codes.
        known={
            "QA_INTAKE_MISSING_OR_SYMLINK","QA_INTAKE_SIZE_INVALID",
            "QA_INTAKE_INVALID_JSON","QA_INTAKE_ROOT_SCHEMA_CHANGED",
            "QA_INTAKE_RELEASE_SCOPE_CHANGED","QA_INTAKE_WARNING_CHANGED",
            "QA_HOSTNAME_ZONE_TYPE_INVALID",
            "QA_ZONE_CANNOT_BE_DEFINED_WITHOUT_QA_FQDN",
            "QA_PROPOSED_FQDN_INVALID","QA_DNS_ZONE_NOT_PARENT_OF_QA_FQDN",
            "QA_INTAKE_ITEM_COUNT_CHANGED","QA_INTAKE_FIELDS_NOT_EXACT",
            "QA_INTAKE_ITEM_SCHEMA_CHANGED","QA_INTAKE_UNKNOWN_EVIDENCE_STATE",
            "QA_INTAKE_PENDING_WITH_UNVERIFIED_VALUES",
            "QA_INTAKE_REFERENCE_METADATA_INVALID",
            "QA_INTAKE_REVIEW_METADATA_INVALID",
            "QA_INTAKE_REVIEW_TIMESTAMP_IN_FUTURE",
            "QA_ZONE_MATCHES_HOST_UNEXPECTEDLY",
            "QA_INTAKE_PRIOR_REGISTER_STATUS_CONFLICT",
            "QA_INTAKE_EVIDENCE_TICKET_HASH_CONFLICT",
            "QA_INTAKE_REVIEW_METADATA_CONFLICT",
            "QA_4K_PACKET_UNEXPECTED_APPROVAL_CHANGE",
            "QA_CADDY_FINGERPRINT_DRIFT",
        }
        code=str(exc)
        print("DB_R31_11_4N_BLOCK_REASON="+
              (code if code in known else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4N_EVIDENCE_INTAKE_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        print("DB_R31_11_4N_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4N_EVIDENCE_INTAKE_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4N_EXTERNAL_HTTPS_MTLS=NOT_TESTED",flush=True)
        print("DB_R31_11_4N_22_EXTERNAL_CASES=NOT_TESTED",flush=True)
        print("DB_R31_11_4N_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4N_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4N_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
