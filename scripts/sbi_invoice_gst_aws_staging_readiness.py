#!/usr/bin/env python3
"""Read-only operator preflight for owner-approved Invoice + GST AWS staging.

Checks exact private file digests, native workbook review status, private
vendor bundle integrity, optional isolated QA PostgreSQL schema and public
unauthenticated ingress. NEVER migrates or writes database rows.

Usage (on authorized isolated AWS staging operator machine):
  python scripts/sbi_invoice_gst_aws_staging_readiness.py \
    --master /private/SBI_SOL_Branch_Master_FINAL.xlsx \
    --vendor-bundle /private/Meghraj_Invoice_Private_Assets_With_Full_Header_20261124.zip \
    --qa-db  # only if SBI_INVOICE_GST_TEST_DSN is configured

This is not a production deploy script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_GATE = REPO_ROOT / "staging/invoice-gst/master_workbook_gate.py"
VENDOR_LOADER = REPO_ROOT / "staging/invoice-gst/private_vendor_loader.py"
APPROVED_MASTER_SHA = "ba90aa8320a3283debe059be9cd6dd3083795782b13874d9823329f2185de3e0"
APPROVED_VENDOR_BUNDLE_SHA = "ae9dfefd1d40c6be399657e7f508751583bab7dc99fcbe0c8239abb882170f8f"
PUBLIC_AWS_HOST = "https://sbi-preview.13-232-241-221.sslip.io"


def _module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("QA_SOURCE_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for buf in iter(lambda: stream.read(1048576), b""):
            sha.update(buf)
    return sha.hexdigest()


def source_review(master, bundle):
    evidence = {
        "owner_approved_pdf_template": "APPROVED_REFERENCE_LOCKED",
        "original_logo_hash_checked": False,
        "branch_master_hash_checked": False,
        "branch_master_source_status": "NOT_READ",
        "private_vendor_bundle_status": "NOT_READ",
        "private_db_import_completed": False,
    }
    if not master or not bundle:
        evidence["missing_source_files"] = True
        return evidence
    if _sha(master) != APPROVED_MASTER_SHA:
        evidence["branch_master_source_status"] = "SOURCE_DIGEST_MISMATCH"
    else:
        evidence["branch_master_hash_checked"] = True
        gate = _module("sbi_master_workbook_gate", MASTER_GATE)
        audit = gate.inspect_private_workbook(master)
        evidence["branch_master_source_status"] = audit["source_status"]
        evidence["canonical_rows"] = audit["canonical_count"]
        evidence["supplemental_review_rows_excluded"] = audit["supplemental_review_rows_excluded"]
        evidence["source_issue_counts"] = audit["issue_counts"]
    if _sha(bundle) != APPROVED_VENDOR_BUNDLE_SHA:
        evidence["private_vendor_bundle_status"] = "VENDOR_ARCHIVE_DIGEST_MISMATCH"
    else:
        loader = _module("sbi_vendor_loader", VENDOR_LOADER)
        _profile, _logo, manifest = loader.unpack_verified_bundle(bundle)
        evidence["private_vendor_bundle_status"] = "OWNER_SOURCE_ARCHIVE_HASH_VERIFIED"
        evidence["original_logo_hash_checked"] = True
        evidence["layout_certification"] = manifest["layout_certification"]
    return evidence


def database_review():
    """Metadata-only read from dedicated DB; never displays financial values."""
    import psycopg
    dsn = os.environ.get("SBI_INVOICE_GST_TEST_DSN", "")
    if not dsn:
        return {"status": "ISOLATED_QA_DSN_MISSING"}
    with psycopg.connect(dsn, connect_timeout=5,
                         options="-c statement_timeout=10000") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            db = cursor.fetchone()[0]
            if db != "invoice_qa":
                return {"status": "REFUSE_NON_ISOLATED_DATABASE"}
            cursor.execute(
                "SELECT to_regclass('sbi_invoice_gst.verified_branches'),"
                "to_regclass('sbi_invoice_gst.vendor_profiles'),"
                "to_regclass('sbi_invoice_gst.invoices'),"
                "to_regclass('sbi_invoice_gst.invoice_lines')"
            )
            tables = cursor.fetchone()
            if any(tab is None for tab in tables):
                return {"status": "STAGING_SCHEMA_NOT_MIGRATED"}
            cursor.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema='sbi_invoice_gst'
                     AND table_name='vendor_profiles'"""
            )
            cols = {x[0] for x in cursor.fetchall()}
            required = {"registered_office", "registered_phone",
                        "registered_email", "head_office", "head_phone",
                        "website", "logo_image"}
            if not required.issubset(cols):
                return {"status": "VENDOR_HEADER_MIGRATION_002_MISSING"}
            cursor.execute(
                """SELECT EXISTS (
                    SELECT 1 FROM sbi_invoice_gst.vendor_profiles
                    WHERE vendor_key='MEGHRAJ_EXPRESS'
                      AND exact_logo_verified=TRUE
                      AND registered_office IS NOT NULL
                      AND head_office IS NOT NULL
                )"""
            )
            vendor_exists = bool(cursor.fetchone()[0])
            cursor.execute(
                """SELECT count(*) FROM sbi_invoice_gst.verified_branches
                   WHERE verified=TRUE"""
            )
            verified_count = cursor.fetchone()[0]
    return {
        "status": "STAGING_SCHEMA_PRESENT",
        "private_vendor_profile_present": vendor_exists,
        "verified_branch_records": verified_count,
        "production_write": False,
    }


def public_access_review(host):
    if host != PUBLIC_AWS_HOST:
        return {"status": "UNRECOGNIZED_AWS_HOST"}
    url = host.rstrip("/") + "/api/invoice-gst/branches"
    req = Request(url, headers={"User-Agent": "SBI-QA-readonly-preflight/1"})
    try:
        with urlopen(req, timeout=8) as r:
            code = r.status
    except HTTPError as e:
        code = e.code
    except (OSError, URLError):
        return {"status": "AWS_INGRESS_UNREACHABLE"}
    # An HTTP 401/403/503 does not prove the actual Flask route exists:
    # Caddy may require login before dispatch. Authenticated testing is separate.
    return {
        "status": "UNAUTHENTICATED_INGRESS_PROTECTED" if code in (401,403)
                  else "FEATURE_INACTIVE_OR_UNAVAILABLE" if code == 503
                  else "UNEXPECTED_PUBLIC_ACCESS_RESULT",
        "http_status": code,
        "authenticated_invoice_route_verified": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--master", type=Path)
    p.add_argument("--vendor-bundle", type=Path)
    p.add_argument("--qa-db", action="store_true")
    p.add_argument("--check-public-ingress", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    report = {
        "milestone": "SBI_INVOICE_GST_PRIVATE_STAGING_PREFLIGHT",
        "source": source_review(args.master, args.vendor_bundle),
        "isolated_qa_database": database_review() if args.qa_db else {
            "status": "NOT_CONNECTED_NOT_TESTED"},
        "aws_ingress": public_access_review(PUBLIC_AWS_HOST)
                        if args.check_public_ingress else {
            "status": "NOT_CONNECTED_NOT_TESTED"},
        "authenticated_aws_staging_test": "NOT_PERFORMED",
        "production_approval": "NOT_REQUESTED",
        "reconciliation_financial_writes": False,
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n",
                               encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    # Exit successful for a read-only audit; never interpret exit 0 as deploy-ready.
    return 0


if __name__=="__main__":
    sys.exit(main())
