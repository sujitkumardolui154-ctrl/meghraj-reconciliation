#!/usr/bin/env python3
"""DB-R31.11.4M: all-in-one READ-ONLY mTLS approval evidence preflight.

Re-runs accepted 4L/4K/4J private security checks against dedicated QA PG16
and current Caddy checksum. Examines a NONSECRET, exact 23-field evidence
register. No approvals are fabricated: submitted references/hashes alone do
not prove DNS, PKI, sign-off, network controls, or external mTLS acceptance.

No Firebase password prompt, no data changes, DNS calls, TLS listener,
certificate creation/import, container creation/deletion, or Caddy edits.
R31.12 QA design active, financial Apply locked, production blocked.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

import r31_11_4l_combined_design_gate as l
import r31_11_4k_external_mtls_readiness as k
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

HERE=Path(__file__).resolve().parent
REGISTER=HERE/"r31_11_4m_evidence_register.json"
SCHEMA="DB-R31.11.4M-APPROVAL-EVIDENCE-REGISTER-V1"
EXPECTED_FIELDS=tuple(k.APPROVAL_FIELDS)+tuple(k.TEXT_FIELDS)
PENDING="PENDING"
SUBMITTED="SUBMITTED_UNVERIFIED"
REVIEWED="REVIEWED_METADATA_ONLY"
ALLOWED_STATUSES={PENDING,SUBMITTED,REVIEWED}
ENTRY_KEYS={"field","status","evidence_ticket","evidence_sha256",
            "review_ticket","reviewed_at_utc"}
ROOT_KEYS={"schema","classification","environment","source_packet_schema",
           "release_authorization","entries","disclaimer"}
TICKET_PATTERN=re.compile(r"[A-Z][A-Z0-9_-]{4,79}\Z")
HEX_PATTERN=re.compile(r"[0-9a-f]{64}\Z")
SENSITIVE_MARKERS=(
    "PASSWORD","TOKEN","SECRET","CREDENTIAL","PRIVATEKEY","BEARER",
    "COOKIE","FIREBASE_UID","APIKEY","BEGIN"
)


class EvidenceBlocked(RuntimeError):
    """Only fixed, non-sensitive diagnostic codes may reach operator logs."""


def require(ok, code):
    if not ok:
        raise EvidenceBlocked(code)


def ticket_ok(value):
    return (type(value) is str
            and TICKET_PATTERN.fullmatch(value) is not None
            and not any(s in value for s in SENSITIVE_MARKERS))


def validate_timestamp(value):
    if type(value) is not str or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",value):
        return False
    try:
        instant=datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return instant.year>=2026
    except ValueError:
        return False


def read_register(path):
    require(path.is_file() and not path.is_symlink(),
            "EVIDENCE_REGISTER_MISSING_OR_SYMLINK")
    raw=path.read_bytes()
    require(1<=len(raw)<=32768,"EVIDENCE_REGISTER_SIZE_INVALID")
    try:
        doc=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError):
        raise EvidenceBlocked("EVIDENCE_REGISTER_INVALID_JSON") from None
    require(type(doc) is dict and set(doc)==ROOT_KEYS,
            "EVIDENCE_REGISTER_ROOT_SCHEMA_INVALID")
    require(doc["schema"]==SCHEMA
            and doc["classification"]=="NONSECRET_METADATA_ONLY_NOT_AUTHORIZATION"
            and doc["environment"]=="qa_isolated_external_mtls"
            and doc["source_packet_schema"]==k.SCHEMA
            and doc["release_authorization"]=="NOT_GRANTED",
            "EVIDENCE_REGISTER_RELEASE_CONTEXT_CHANGED")
    disclaimer=doc["disclaimer"]
    require(type(disclaimer) is str and 50<=len(disclaimer)<=350
            and "not independently verified" in disclaimer,
            "EVIDENCE_REGISTER_DISCLAIMER_CHANGED")
    entries=doc["entries"]
    require(type(entries) is list and len(entries)==23,
            "EVIDENCE_REGISTER_NOT_23_FIELDS")
    require([e.get("field") if type(e) is dict else None for e in entries]
            ==list(EXPECTED_FIELDS),
            "EVIDENCE_REGISTER_FIELDS_NOT_EXACT")

    counts={PENDING:0,SUBMITTED:0,REVIEWED:0}
    for entry in entries:
        require(type(entry) is dict and set(entry)==ENTRY_KEYS,
                "EVIDENCE_ENTRY_SCHEMA_INVALID")
        status=entry["status"]
        require(type(status) is str and status in ALLOWED_STATUSES,
                "EVIDENCE_ENTRY_STATUS_NOT_ALLOWED")
        evidence=entry["evidence_ticket"]
        digest=entry["evidence_sha256"]
        review=entry["review_ticket"]
        reviewed=entry["reviewed_at_utc"]
        if status==PENDING:
            require(all(value==PENDING for value in
                        (evidence,digest,review,reviewed)),
                    "EVIDENCE_PENDING_WITH_UNREVIEWED_DATA")
        elif status==SUBMITTED:
            require(ticket_ok(evidence)
                    and type(digest) is str and HEX_PATTERN.fullmatch(digest) is not None
                    and review==PENDING and reviewed==PENDING,
                    "EVIDENCE_SUBMISSION_METADATA_INVALID")
        else:
            require(ticket_ok(evidence) and ticket_ok(review)
                    and evidence!=review
                    and type(digest) is str and HEX_PATTERN.fullmatch(digest) is not None
                    and validate_timestamp(reviewed),
                    "EVIDENCE_REVIEW_METADATA_INVALID")
        counts[status]+=1
    return counts


def verify_packet_consistency(packet_path,counts):
    # The original 4K packet and statuses are purely declarations. This
    # phase cannot certify independently submitted DNS/PKI/audit evidence.
    packet=k.read_packet(packet_path)
    missing=k.review_packet(packet)
    require(len(missing)==23 or counts[REVIEWED]>0,
            "EVIDENCE_PENDING_VERSUS_APPROVAL_PACKET_MISMATCH")
    # Independent approval closure must be separate. For now reject any
    # claim of approved/review-only in the 4K packet, even if some metadata
    # has been marked reviewed in the 4M register.
    require(packet["workflow_status"]=="PENDING_APPROVAL"
            and all(packet[field] is False for field in k.APPROVAL_FIELDS)
            and all(packet[field]=="PENDING" for field in k.TEXT_FIELDS),
            "APPROVAL_PACKET_CHANGED_REQUIRES_SEPARATE_REVIEW")
    print("DB_R31_11_4M_4K_APPROVALS=23_OF_23_PENDING",flush=True)


def combined_preflight(sha,register_path,packet_path):
    # Real read-only QA infrastructure checks, including source pin,
    # two approved Firebase user records, 4I local auth receipt,
    # PostgreSQL RLS, no customer rows, original Caddy hash, no remnants.
    l.combined_audit(sha,packet_path)
    print("DB_R31_11_4M_4L_COMBINED_SECURITY=PASS_READONLY",flush=True)

    counts=read_register(register_path)
    print("DB_R31_11_4M_REGISTER_SCHEMA=PASS_EXACT_23_FIELDS_NO_SECRETS",flush=True)
    print("DB_R31_11_4M_EVIDENCE_PENDING="+str(counts[PENDING]),flush=True)
    print("DB_R31_11_4M_EVIDENCE_SUBMITTED_UNVERIFIED="+str(counts[SUBMITTED]),
          flush=True)
    print("DB_R31_11_4M_EVIDENCE_METADATA_REVIEWED="+str(counts[REVIEWED]),
          flush=True)
    verify_packet_consistency(packet_path,counts)

    # No registered metadata, even reviewed, is an automatic independent
    # approval. The 22 E2E cases remain NOT_TESTED_EXTERNAL.
    l.inspect_design()
    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "CADDY_FINGERPRINT_CHANGED")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4M_22_EXTERNAL_CASES=ALL_NOT_TESTED",flush=True)
    print("DB_R31_11_4M_AFTER_AUDIT_DB_CADDY=PASS_UNCHANGED",flush=True)
    print("DB_R31_11_4M_COMBINED_EVIDENCE_PREFLIGHT=PASS_READONLY_NO_DEPLOY",
          flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="R31.11.4M combined QA evidence audit")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--register",type=Path,default=REGISTER)
    parser.add_argument("--packet",type=Path,default=k.TEMPLATE_PACKET)
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4M EXTERNAL MTLS EVIDENCE COMBINED PREFLIGHT ===",
          flush=True)
    try:
        combined_preflight(args.source_sha,args.register,args.packet)
        return 0
    except EvidenceBlocked as exc:
        allow={
            "EVIDENCE_REGISTER_MISSING_OR_SYMLINK",
            "EVIDENCE_REGISTER_SIZE_INVALID",
            "EVIDENCE_REGISTER_INVALID_JSON",
            "EVIDENCE_REGISTER_ROOT_SCHEMA_INVALID",
            "EVIDENCE_REGISTER_RELEASE_CONTEXT_CHANGED",
            "EVIDENCE_REGISTER_DISCLAIMER_CHANGED",
            "EVIDENCE_REGISTER_NOT_23_FIELDS",
            "EVIDENCE_REGISTER_FIELDS_NOT_EXACT",
            "EVIDENCE_ENTRY_SCHEMA_INVALID",
            "EVIDENCE_ENTRY_STATUS_NOT_ALLOWED",
            "EVIDENCE_PENDING_WITH_UNREVIEWED_DATA",
            "EVIDENCE_SUBMISSION_METADATA_INVALID",
            "EVIDENCE_REVIEW_METADATA_INVALID",
            "EVIDENCE_PENDING_VERSUS_APPROVAL_PACKET_MISMATCH",
            "APPROVAL_PACKET_CHANGED_REQUIRES_SEPARATE_REVIEW",
            "CADDY_FINGERPRINT_CHANGED",
        }
        code=str(exc)
        print("DB_R31_11_4M_BLOCK_REASON="+
              (code if code in allow else "REVIEW_REQUIRED"),flush=True)
        print("STOP=DB_R31_11_4M_EVIDENCE_AUDIT_REVIEW_REQUIRED",flush=True)
        return 2
    except Exception:
        print("DB_R31_11_4M_BLOCK_REASON=REVIEW_REQUIRED",flush=True)
        print("STOP=DB_R31_11_4M_EVIDENCE_AUDIT_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4M_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4M_REVOCATION_TESTS=NOT_TESTED",flush=True)
        print("DB_R31_11_4M_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4M_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4M_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
