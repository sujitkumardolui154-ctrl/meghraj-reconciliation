"""One-document Firestore metadata attestation; no invoice rows or writes.

Independent diagnostic for a restricted GCP operator environment. This module is
NOT copied into, imported by, or enabled in the AWS preview Docker image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PROJECT = "meghraj-reconciliation"
SOURCE_SHA256 = "433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"
DATASET = SOURCE_SHA256 + "-report-v1"
COLLECTION = "dashboard_report_datasets"
BASELINE_ROWS = 14374
UNPAID_ROWS = 2430
APPROVED_BASIS = "PAYMENT_RECEIVED_COLUMN_U_BLANK_OR_ZERO"
CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend_source" / "invoice_import_contract.json"
)


def approved_headers(contract_path=CONTRACT_PATH):
    """Load the existing ordered header contract; never rewrite it."""
    document = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    headers = document["headers"]
    if not isinstance(headers, list) or len(headers) != 53:
        raise ValueError("APPROVED_HEADER_CONTRACT_NOT_53")
    if not all(isinstance(value, str) and value for value in headers):
        raise ValueError("APPROVED_HEADER_CONTRACT_INVALID")
    return headers


def header_fingerprint(headers):
    payload = json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit(metadata, expected_headers):
    """Compare a single metadata document with the frozen baseline.

    No row, payment, invoice, customer name, credential, or header value is
    returned in the attestation. All comparisons are position-sensitive.
    """
    failures = []
    if not isinstance(metadata, dict):
        return ["DATASET_METADATA_MISSING"]
    checks = (
        ("state", "READY", "DATASET_NOT_READY"),
        ("source_sha256", SOURCE_SHA256, "SOURCE_HASH_MISMATCH"),
        ("rows", BASELINE_ROWS, "BASELINE_ROW_COUNT_MISMATCH"),
        ("unpaid_payment_state", "READY", "UNPAID_SNAPSHOT_NOT_READY"),
        ("unpaid_payment_count", UNPAID_ROWS, "UNPAID_COUNT_MISMATCH"),
        ("unpaid_payment_basis", APPROVED_BASIS, "UNPAID_BASIS_MISMATCH"),
        ("original_columns_state", "READY", "ORIGINAL_COLUMNS_NOT_READY"),
        ("original_column_count", len(expected_headers), "COLUMN_COUNT_MISMATCH"),
        ("original_columns_row_count", BASELINE_ROWS, "ORIGINAL_ROW_COUNT_MISMATCH"),
        ("original_headers", expected_headers, "ORDERED_HEADER_MISMATCH"),
    )
    for field, expected, issue in checks:
        actual = metadata.get(field)
        if isinstance(expected, int):
            matching = type(actual) is int and actual == expected
        else:
            matching = actual == expected
        if not matching:
            failures.append(issue)
    return failures


def read_metadata_once(client):
    """Exactly one Firestore document GET; no collection query or writes."""
    snap = (
        client.collection(COLLECTION)
        .document(DATASET)
        .get(timeout=10, retry=None)
    )
    if not snap.exists:
        return None
    return snap.to_dict()


def result(status, *, header_digest=None, checks=()):
    # Deliberately omit metadata/document content and error exception strings.
    return {
        "status": status,
        "mode": "single_document_metadata_only",
        "firestore_read_verified": status == "PASS_METADATA_ONLY",
        "aws_backend_connected": False,
        "report_data_certified": False,
        "financial_execution_enabled": False,
        "financial_writes_performed": 0,
        "source_sha256": SOURCE_SHA256,
        "dataset_id": DATASET,
        "header_contract_sha256": header_digest,
        "blockers": list(checks),
    }


def run(*, live_read=False, client=None, contract_path=CONTRACT_PATH):
    try:
        headers = approved_headers(contract_path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return result("BLOCKED", checks=["APPROVED_HEADER_CONTRACT_UNAVAILABLE"])
    digest = header_fingerprint(headers)
    if not live_read:
        return result("DRY_RUN_NO_DATABASE_ACCESS", header_digest=digest,
                      checks=["EXPLICIT_READ_ONLY_APPROVAL_NOT_REQUESTED"])
    try:
        if client is None:
            # Application Default Credentials; never load a service account key
            # or accept a password/token/credential path from CLI options.
            from google.cloud import firestore
            client = firestore.Client(project=PROJECT)
        metadata = read_metadata_once(client)
    except Exception:
        # Never echo exception text: cloud SDK errors can include identities.
        return result("BLOCKED", header_digest=digest,
                      checks=["FIRESTORE_AUTH_OR_CONNECTIVITY_FAILED"])
    findings = audit(metadata, headers)
    if findings:
        return result("BLOCKED", header_digest=digest, checks=findings)
    return result("PASS_METADATA_ONLY", header_digest=digest)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only, metadata-only SBI report snapshot check"
    )
    parser.add_argument(
        "--live-read-only-metadata", action="store_true",
        help="Attempt one document GET with existing Application Default Credentials"
    )
    args = parser.parse_args(argv)
    status = run(live_read=args.live_read_only_metadata)
    print(json.dumps(status, sort_keys=True))
    return 0 if status["status"] in ("DRY_RUN_NO_DATABASE_ACCESS",
                                      "PASS_METADATA_ONLY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
