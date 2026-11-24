"""SBI R28: Owner's no-certification requirement for calculation/report deployment.

NO financial certificate is a prerequisite for a read-only CALCULATION_AND_REPORT
application release. Technical execution integrity, source provenance and
authenticated access remain prerequisites. A rule-failed invoice/payment is
excluded individually; independent eligible records remain candidates.

This module is a pure *policy and candidate-screening contract*, not the actual
v2.51/v2.39 rule evaluator, XLSX writer, AWS deployer or financial executor.
It cannot certify that caller-provided screening results, security checks or
bank events are true and cannot assign a payment OK status.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re

STAGE="SBI_R28_OWNER_CALCULATION_DEPLOYMENT_POLICY_NO_FINANCE_CERT"
DEPLOYMENT_SCOPE="CALCULATION_AND_REPORT_NO_FINANCIAL_WRITE"
SPECIFICATION="MASTER_V251_MATRIX_V239"
OUTPUT_CONTRACT="V218"
SHA256=re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_SCREEN_RESULTS=frozenset(("PASS","EXCLUDE","HOLD"))
ALLOWED_ROLES=frozenset(("INVOICE","PAYMENT"))
MAX_RECORDS=100000
MAX_CANDIDATES=200000


class DeploymentScopeRefusal(ValueError):
    """Fail closed on unsafe application contract, no private data in errors."""


def check(condition,code):
    if not condition:
        raise DeploymentScopeRefusal(code)


@dataclass(frozen=True)
class ScreenedSourceRecord:
    role:str
    source_row:int
    source_identity:str
    result:str
    reasons:tuple[str,...]=()


@dataclass(frozen=True)
class ScreenedMatch:
    invoice_row:int
    payment_row:int
    result:str
    reasons:tuple[str,...]=()


@dataclass(frozen=True)
class OperatorTechnicalChecks:
    """Self-reported here. Deployment host must independently attest checks."""
    source_file_fresh:bool
    release_code_tests_passed:bool
    access_control_and_role_deny_verified:bool
    immutable_source_and_audit_verified:bool
    production_financial_write_disabled:bool


def _reasons(reasons):
    check(type(reasons) is tuple and len(reasons)<=10,
          "INVALID_SCREEN_REASON_CONTAINER")
    check(all(type(x) is str and re.fullmatch(r"[A-Z0-9_:-]{2,100}",x)
              for x in reasons),"INVALID_SCREEN_REASON")
    check(len(set(reasons))==len(reasons),"DUPLICATED_SCREEN_REASON")


def _screen_ok(x):
    check(x.result in ALLOWED_SCREEN_RESULTS,"UNKNOWN_RECORD_SCREEN_RESULT")
    _reasons(x.reasons)
    check((x.result=="PASS") == (len(x.reasons)==0),
          "SCREEN_RESULT_REASON_INCONSISTENT")


def assess_calculation_deployment(checks:OperatorTechnicalChecks, *,
                                  scope=DEPLOYMENT_SCOPE,
                                  financial_apply="LOCKED",
                                  formal_financial_certificate=None):
    """No formal financial certification gate, but no fictitious actual deploy."""
    check(type(checks) is OperatorTechnicalChecks,"TECHNICAL_CHECKS_REQUIRED")
    check(scope==DEPLOYMENT_SCOPE,"FINANCIAL_WRITE_DEPLOYMENT_SCOPE_FORBIDDEN")
    check(financial_apply=="LOCKED" and checks.production_financial_write_disabled is True,
          "FINANCIAL_APPLY_AND_DB_WRITE_MUST_REMAIN_DISABLED")
    # A certificate does not upgrade the permitted deployment scope.
    # No formal certificate is required to make a CALCULATION_ONLY candidate.
    # Explicitly reject a user-supplied certificate to avoid token-gate bypass.
    check(formal_financial_certificate is None,
          "FINANCIAL_CERTIFICATE_NOT_A_DEPLOYMENT_PERMISSION_TOKEN")
    prereqs={
        "fresh_user_source":checks.source_file_fresh is True,
        "technical_tests":checks.release_code_tests_passed is True,
        "effective_access_controls":checks.access_control_and_role_deny_verified is True,
        "source_preservation_and_audit":checks.immutable_source_and_audit_verified is True,
        "financial_writes_off":checks.production_financial_write_disabled is True,
    }
    return {
        "stage":STAGE,
        "deployment_scope":DEPLOYMENT_SCOPE,
        "formal_financial_certification_required_for_deployment":False,
        "operator_reported_technical_prerequisites":prereqs,
        "operator_reported_deployment_candidate":all(prereqs.values()),
        "technical_prerequisites_independently_attested_by_module":False,
        "aws_or_production_deployment_performed":False,
        "full_v251_v239_engine_implemented_or_certified_by_module":False,
        "payment_status_assignment_authorized":False,
        "financial_apply_locked":True,
        "database_financial_writes_authorized":False,
        "finance_release_gate_unmodified":True,
    }


def partition_screened_source(records, matches, *, source_sha256,
                              financial_apply="LOCKED"):
    """Retain all sources, exclude failed rows without halting other candidates.

    Inputs must already be screened against the approved v2.51/v2.39 rules.
    Does not verify screening evidence or allocate money. Every rejection is
    surfaced by source row and constant reason code. A duplicate invoice/bank
    identity only excludes that identity's group, not the entire upload.
    """
    check(financial_apply=="LOCKED","FINANCIAL_APPLY_LOCK_REQUIRED")
    check(type(source_sha256) is str and SHA256.fullmatch(source_sha256),
          "ORIGINAL_SOURCE_SHA256_REQUIRED")
    check(type(records) is tuple and len(records)<=MAX_RECORDS
          and all(type(r) is ScreenedSourceRecord for r in records),
          "TYPED_SOURCE_RECORDS_REQUIRED")
    check(type(matches) is tuple and len(matches)<=MAX_CANDIDATES
          and all(type(m) is ScreenedMatch for m in matches),
          "TYPED_METHOD_SCREEN_REQUIRED")
    by_row={}; duplicate_ids=defaultdict(list)
    for r in records:
        check(r.role in ALLOWED_ROLES and type(r.source_row) is int
              and r.source_row>=2 and type(r.source_identity) is str
              and bool(r.source_identity.strip()) and len(r.source_identity)<=160,
              "UNSAFE_SOURCE_RECORD_IDENTITY")
        _screen_ok(r)
        key=(r.role,r.source_row)
        check(key not in by_row,"DUPLICATE_OR_FORGED_SOURCE_ROW")
        by_row[key]=r
        duplicate_ids[(r.role,r.source_identity.strip())].append(r.source_row)
    duplicate_keys={key for key,rows in duplicate_ids.items() if len(rows)>1}
    excluded=[]; held=[]; eligible=[]
    for record in records:
        duplicate=(record.role,record.source_identity.strip()) in duplicate_keys
        detail={
            "role":record.role,
            "source_row":record.source_row,
            "source_identity":record.source_identity,
            "reason_codes":tuple(record.reasons)+(
                ("DUPLICATE_SOURCE_IDENTITY",) if duplicate
                and "DUPLICATE_SOURCE_IDENTITY" not in record.reasons else ()),
        }
        if duplicate or record.result=="EXCLUDE":
            if not detail["reason_codes"]:
                detail["reason_codes"]=("RULE_EXCLUDED",)
            excluded.append(detail)
        elif record.result=="HOLD":
            held.append(detail)
        else:
            eligible.append(record)
    excluded_ids={(x["role"],x["source_row"]) for x in excluded}
    held_ids={(x["role"],x["source_row"]) for x in held}
    eligible_by_role={
        role:{r.source_row for r in eligible if r.role==role}
        for role in ALLOWED_ROLES
    }
    seen_match_pairs=set()
    candidate_pairs=[]
    excluded_pairs=[]
    held_pairs=[]
    for match in matches:
        check(type(match.invoice_row) is int and type(match.payment_row) is int
              and match.invoice_row>=2 and match.payment_row>=2,
              "INVALID_MATCH_SOURCE_ROW")
        _screen_ok(match)
        pair=(match.invoice_row,match.payment_row)
        check(pair not in seen_match_pairs,"DUPLICATE_SCREENED_EDGE")
        seen_match_pairs.add(pair)
        check(("INVOICE",match.invoice_row) in by_row
              and ("PAYMENT",match.payment_row) in by_row,
              "MATCH_REFERENCES_UNKNOWN_SOURCE_ROW")
        reasons=list(match.reasons)
        if ("INVOICE",match.invoice_row) in excluded_ids or (
            "PAYMENT",match.payment_row) in excluded_ids:
            reasons.append("SOURCE_RECORD_EXCLUDED")
            group=excluded_pairs
        elif ("INVOICE",match.invoice_row) in held_ids or (
            "PAYMENT",match.payment_row) in held_ids:
            reasons.append("SOURCE_RECORD_ON_HOLD")
            group=held_pairs
        elif match.result=="EXCLUDE":
            group=excluded_pairs
        elif match.result=="HOLD":
            group=held_pairs
        else:
            group=candidate_pairs
        group.append({
            "invoice_source_row":match.invoice_row,
            "payment_source_row":match.payment_row,
            "reason_codes":tuple(dict.fromkeys(reasons)),
        })
    summary={
        "source_record_count":len(records),
        "eligible_invoice_rows":len(eligible_by_role["INVOICE"]),
        "eligible_payment_rows":len(eligible_by_role["PAYMENT"]),
        "excluded_record_count":len(excluded),
        "held_record_count":len(held),
        "method_candidate_pair_count":len(candidate_pairs),
        "excluded_pair_count":len(excluded_pairs),
        "held_pair_count":len(held_pairs),
    }
    integrity=sha256(json.dumps({"sha":source_sha256,"counts":summary},
                  sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {
        "stage":STAGE,
        "source_sha256":source_sha256,
        "specification":SPECIFICATION,
        "output_contract":OUTPUT_CONTRACT,
        "source_preserved":True,
        "source_rows_deleted":0,
        "screening_results_externally_verified":False,
        "eligible_records":tuple((r.role,r.source_row,r.source_identity) for r in eligible),
        "excluded_records":tuple(excluded),
        "held_records":tuple(held),
        "method_candidates":tuple(candidate_pairs),
        "excluded_pairs":tuple(excluded_pairs),
        "held_pairs":tuple(held_pairs),
        "summary":summary,
        "summary_digest_sha256":integrity,
        "real_bank_allocations":0,
        "payment_status_column_m_written":False,
        "real_database_writes":0,
        "financial_apply_locked":True,
        "full_engine_financial_certification_claimed":False,
        "production_deployment_claimed":False,
    }
