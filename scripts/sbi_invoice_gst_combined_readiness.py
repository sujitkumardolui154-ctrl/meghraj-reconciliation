#!/usr/bin/env python3
"""One-command, fail-closed Invoice/GST private acceptance preflight.

Reuses existing source/isolated-DB/ingress preflight and the private QA gate.
Does not authenticate users, migrate databases, certify PDF parity, attribute
GST months, approve corrections, unlock finance, or deploy. No secrets logged.
Requires separate independently verified real acceptance and release approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "scripts/sbi_invoice_gst_aws_staging_readiness.py"
QA_GATE = ROOT / "scripts/sbi_invoice_gst_private_qa_gate.py"

PENDING_EXTERNAL = (
    "INV02_AUTHENTICATED_FIREBASE_CREATOR_VIEWER_E2E",
    "INV02_REAL_CSRF_SESSION_TENANT_DENIAL",
    "INV03_PRIVATE_APPROVED_BRANCH_ROW_PROVENANCE",
    "INV04_PDF_FULL_ANNEXURE_PRIVATE_OUTPUT_PARITY",
    "INV04_GST_16_COLUMN_EXACT_SOURCE_PARITY",
    "GST01_MULTI_MONTH_TAX_PERIOD_POLICY_APPROVAL",
    "INV05_CORRECTION_CREDIT_NOTE_FILING_POLICY_APPROVAL",
    "INV06_SEPARATE_OWNER_PRODUCTION_RELEASE_APPROVAL",
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("REQUIRED_PREEXISTING_MODULE_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def combine(preflight, evaluate):
    """Classify only source prerequisites; never infer live test completion."""
    decision = evaluate(preflight)
    if decision.get("production_deployment") != "NOT_AUTHORIZED":
        raise ValueError("INVALID_PRODUCTION_GATE")
    if decision.get("financial_allocation") != "NOT_PERMITTED":
        raise ValueError("INVALID_FINANCIAL_GATE")
    ready = decision.get("ready_for_authenticated_private_qa") is True
    return {
        "milestone": "INV_GST_COMBINED_PRIVATE_ACCEPTANCE_PREFLIGHT",
        "status": ("STAGING_PREREQUISITES_READY_EXTERNAL_ACCEPTANCE_PENDING"
                   if ready else "BLOCKED_PRIVATE_PREREQUISITES"),
        "source_gate": decision.get("status"),
        "source_outstanding": decision.get("outstanding", []),
        "source_checks": decision.get("checks", {}),
        "required_independent_acceptance": list(PENDING_EXTERNAL),
        "authenticated_aws_e2e": "NOT_TESTED_BY_THIS_COMMAND",
        "pdf_parity": "NOT_TESTED_BY_THIS_COMMAND",
        "gst_reporting_parity": "NOT_TESTED_BY_THIS_COMMAND",
        "cross_month_gst_policy": "PENDING_ACCOUNTING_APPROVAL",
        "correction_policy": "PENDING_ACCOUNTING_OWNER_APPROVAL",
        "production_deployment": "BLOCKED",
        "financial_apply": "LOCKED",
        "database_write": "NONE",
        "reconciliation_write": "NONE",
    }


def collect(readiness, *, master=None, vendor=None, pdf=None,
            qa_db=False, check_public_ingress=False):
    """Opt-in reads only. Without source paths or QA DB: fail closed."""
    source = readiness.source_review(master, vendor, pdf)
    database = (readiness.database_review() if qa_db
                else {"status": "NOT_CONNECTED_NOT_TESTED"})
    ingress = (readiness.public_access_review(readiness.PUBLIC_AWS_HOST)
               if check_public_ingress
               else {"status": "NOT_CONNECTED_NOT_TESTED"})
    return {
        "source": source,
        "isolated_qa_database": database,
        "aws_ingress": ingress,
        "authenticated_aws_staging_test": "NOT_PERFORMED",
        "reconciliation_financial_writes": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path)
    parser.add_argument("--vendor-bundle", type=Path)
    parser.add_argument("--approved-pdf", type=Path)
    parser.add_argument("--qa-db", action="store_true",
                        help="metadata-only, requires existing private invoice_qa DSN")
    parser.add_argument("--check-public-ingress", action="store_true",
                        help="unauthenticated GET on existing approved preview host")
    parser.add_argument("--preflight-json", type=Path,
                        help="reuse a previously generated trusted preflight instead")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--assert-source-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        gate = _load("sbi_invoice_gst_existing_private_gate", QA_GATE)
        if args.preflight_json:
            if any((args.master, args.vendor_bundle, args.approved_pdf,
                    args.qa_db, args.check_public_ingress)):
                raise ValueError("PREEXISTING_PREFLIGHT_CANNOT_MIX_WITH_NEW_READS")
            preflight = json.loads(args.preflight_json.read_text(encoding="utf-8"))
        else:
            readiness = _load("sbi_invoice_gst_existing_readiness", READINESS)
            preflight = collect(
                readiness, master=args.master, vendor=args.vendor_bundle,
                pdf=args.approved_pdf, qa_db=args.qa_db,
                check_public_ingress=args.check_public_ingress,
            )
        result = combine(preflight, gate.evaluate_staging_preflight)
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 2 if args.assert_source_ready and (
            result["status"] != "STAGING_PREREQUISITES_READY_EXTERNAL_ACCEPTANCE_PENDING"
        ) else 0
    except (OSError, ValueError, RuntimeError, ImportError, TypeError) as exc:
        # Do not emit exception messages: libraries may embed DSNs/private paths.
        print(json.dumps({
            "milestone": "INV_GST_COMBINED_PRIVATE_ACCEPTANCE_PREFLIGHT",
            "status": "BLOCKED_INVALID_OR_UNAVAILABLE_EVIDENCE",
            "error_class": type(exc).__name__,
            "production_deployment": "BLOCKED",
            "financial_apply": "LOCKED",
        }))
        return 3


if __name__ == "__main__":
    sys.exit(main())
