#!/usr/bin/env python3
"""R31.11.4Y: validate nonsecret evidence intake metadata, never approve release.

Run with the tracked pending-only template, or an independently maintained
nonsecret candidate file outside the repository using --candidate.
This is structural screening, not DNS/PKI/firewall or reviewer verification.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent
TEMPLATE=HERE/"r31_11_4y_evidence_template.json"
GROUPS=(
    "DOMAIN_DNS_OWNERSHIP",
    "INGRESS_FIREWALL_AND_ROUTE_ISOLATION",
    "TLS_SERVER_CERT_AND_CLIENT_CA_REVOCATION",
    "CHANGE_ROLLBACK_MONITORING_AND_SECURITY_REVIEW",
)
FIELDS=(
    "change_ticket","evidence_reference","evidence_sha256",
    "owner_review_ticket","independent_security_review_ticket","reviewed_at_utc",
)
SAFE_REF=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{2,127}$")
UTC=re.compile(r"^20\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ$")
SHA=re.compile(r"^[0-9a-f]{64}$")

def load(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>16384:
        raise ValueError("EVIDENCE_FILE_UNSAFE")
    return json.loads(path.read_text(encoding="utf-8"))

def review(doc):
    required={"schema","classification","environment","release_authorization",
              "financial_apply","production_release","external_acceptance",
              "evidence_groups","notice"}
    if (type(doc) is not dict or set(doc)!=required or
        doc["schema"]!="DB-R31.11.4Y-INDEPENDENT-EVIDENCE-INTAKE-V1" or
        doc["classification"]!="NONSECRET_PROVENANCE_METADATA_NOT_APPROVAL" or
        doc["environment"]!="qa_isolated_external_mtls" or
        doc["release_authorization"]!="NOT_GRANTED" or
        doc["financial_apply"]!="LOCKED" or
        doc["production_release"]!="BLOCKED" or
        doc["external_acceptance"]!="NOT_TESTED" or
        type(doc["notice"]) is not str):
        raise ValueError("FAIL_CLOSED_SCHEMA_OR_LOCK")
    groups=doc["evidence_groups"]
    if (type(groups) is not list or len(groups)!=len(GROUPS)
        or [x.get("id") for x in groups if type(x) is dict]!=list(GROUPS)):
        raise ValueError("GROUP_MISMATCH")
    submitted=0
    for item in groups:
        if type(item) is not dict or set(item)!={"id","state",*FIELDS}:
            raise ValueError("EVIDENCE_FIELDS_MISMATCH")
        state=item["state"]
        if state not in ("PENDING","SUBMITTED_FOR_INDEPENDENT_REVIEW"):
            raise ValueError("UNAUTHORIZED_APPROVAL_STATE")
        if state=="PENDING":
            if any(item[name]!="PENDING" for name in FIELDS):
                raise ValueError("PARTIAL_PENDING_RECORD")
        else:
            for name in FIELDS:
                value=item[name]
                if type(value) is not str:
                    raise ValueError("INVALID_EVIDENCE_METADATA")
                if name=="evidence_sha256":
                    ok=bool(SHA.fullmatch(value))
                elif name=="reviewed_at_utc":
                    ok=bool(UTC.fullmatch(value))
                else:
                    ok=bool(SAFE_REF.fullmatch(value))
                if not ok:
                    raise ValueError("EVIDENCE_METADATA_UNSAFE_OR_MISSING")
            submitted+=1
    print("DB_R31_11_4Y_EVIDENCE_SCHEMA=PASS")
    print("DB_R31_11_4Y_GROUPS_TOTAL=4")
    print("DB_R31_11_4Y_SUBMITTED_FOR_REVIEW="+str(submitted))
    print("DB_R31_11_4Y_PENDING_GROUPS="+str(4-submitted))
    print("DB_R31_11_4Y_INDEPENDENT_VERIFICATION=NOT_PERFORMED_BY_SCRIPT")
    print("DB_R31_11_4Y_ACTUAL_AUTHORIZATIONS=NOT_GRANTED")
    print("DB_R31_11_4Y_EXTERNAL_ACCEPTANCE=0_OF_22_EXECUTED")
    print("DB_R31_11_4Y_METADATA_SCREEN=PASS_NOT_RELEASE_AUTHORIZATION")
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Validate nonsecret review metadata; never grant approval")
    p.add_argument("--candidate",type=Path,default=TEMPLATE)
    args=p.parse_args()
    try:
        result=review(load(args.candidate))
    except (OSError,ValueError,TypeError,UnicodeError,json.JSONDecodeError):
        print("STOP=DB_R31_11_4Y_INVALID_OR_UNSAFE_EVIDENCE")
        result=2
    finally:
        print("DB_R31_11_4Y_FINANCIAL_APPLY=LOCKED")
        print("DB_R31_11_4Y_PRODUCTION_RELEASE=BLOCKED")
    raise SystemExit(result)
