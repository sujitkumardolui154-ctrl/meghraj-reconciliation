#!/usr/bin/env python3
"""Fail-closed go/no-go gate for the SBI Invoice/GST *private QA* candidate.

Consumes the JSON produced by scripts/sbi_invoice_gst_aws_staging_readiness.py.
It CANNOT authorize financial production or assert live auth success. It only
decides whether an isolated staging operator has source, vendor and schema
prerequisites to begin authenticated end-to-end QA. No DB/network calls.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def evaluate_staging_preflight(payload):
    if not isinstance(payload, dict):
        raise ValueError("PREFLIGHT_JSON_OBJECT_REQUIRED")
    source = payload.get("source") or {}
    database = payload.get("isolated_qa_database") or {}
    ingress = payload.get("aws_ingress") or {}
    if not all(isinstance(x, dict) for x in (source, database, ingress)):
        raise ValueError("INVALID_PREFLIGHT_SECTION")

    checks = {
        "OWNER_REFERENCE_FORMAT_APPROVED": (
            source.get("owner_approved_pdf_template") == "APPROVED_REFERENCE_LOCKED"
        ),
        "MASTER_FILE_SHA256_VERIFIED": source.get("branch_master_hash_checked") is True,
        "APPROVED_PDF_SHA256_VERIFIED": source.get("approved_pdf_sha256_checked") is True,
        "SOURCE_REVIEW_NOT_MISREPRESENTED_AS_FINAL": (
            source.get("branch_master_source_status")
            == "WORKING_REVIEW_NOT_APPROVED_FOR_AUTOMATIC_IMPORT"
        ),
        "OWNER_VENDOR_BUNDLE_SHA256_VERIFIED": (
            source.get("private_vendor_bundle_status")
            == "OWNER_SOURCE_ARCHIVE_HASH_VERIFIED"
            and source.get("original_logo_hash_checked") is True
        ),
        "ISOLATED_QA_DATABASE_SCHEMAS_PRESENT": (
            database.get("status") == "STAGING_SCHEMA_PRESENT"
        ),
        "PRIVATE_VENDOR_PROFILE_INSERTED": (
            database.get("private_vendor_profile_present") is True
        ),
        "INDEPENDENTLY_VERIFIED_SBI_BRANCHES_EXIST": (
            type(database.get("verified_branch_records")) is int
            and database["verified_branch_records"] > 0
        ),
        "NO_PRODUCTION_FINANCIAL_WRITES": (
            payload.get("reconciliation_financial_writes") is False
            and database.get("production_write") is False
        ),
        "PUBLIC_AWS_ACCESS_NOT_PROVEN_OPEN": (
            ingress.get("status") in (
                "UNAUTHENTICATED_INGRESS_PROTECTED",
                "FEATURE_INACTIVE_OR_UNAVAILABLE",
            )
        ),
    }
    missing = sorted(key for key, passed in checks.items() if not passed)
    ready_for_signed_in_qa = not missing
    # Never claim the preflight alone proved authenticated AWS integration,
    # authorization, backup/restore or approval for financial live traffic.
    return {
        "milestone": "SBI_INVOICE_GST_PRIVATE_QA_GATE",
        "status": ("READY_FOR_OPERATOR_AUTHENTICATED_PRIVATE_QA"
                   if ready_for_signed_in_qa
                   else "BLOCKED_PENDING_PRIVATE_QA_PREREQUISITES"),
        "ready_for_authenticated_private_qa": ready_for_signed_in_qa,
        "checks": checks,
        "outstanding": missing,
        "authenticated_aws_e2e": "NOT_VERIFIED_BY_THIS_GATE",
        "production_deployment": "NOT_AUTHORIZED",
        "financial_allocation": "NOT_PERMITTED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-json", type=Path, required=True)
    parser.add_argument("--assert-ready", action="store_true",
                        help="nonzero exit unless private QA preconditions all pass")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.preflight_json.read_text(encoding="utf-8"))
        report = evaluate_staging_preflight(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "PREFLIGHT_INPUT_INVALID",
                          "detail": type(exc).__name__}))
        return 3
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.assert_ready and not report["ready_for_authenticated_private_qa"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
