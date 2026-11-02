#!/usr/bin/env python3
"""SBI R2: read-only Firestore/source/receipt/report integrity check.

No write operations, no source rows in logs/GitHub, no production approval.
The real database is accessed only with explicit --live-read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT = "meghraj-reconciliation"
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def evaluate(baseline, imported, metadata, headers, receipt_audit, *,
             dataset_id, report_manifest=None, report_bytes=None,
             approved_headers=None, metadata_stable=True):
    """Return only aggregate counts, non-reversible digests and failure codes."""
    blockers = []

    def reject(reason):
        if reason not in blockers:
            blockers.append(reason)

    headers = list(headers) if isinstance(headers, (list, tuple)) else []
    if (len(headers) != 53 or headers[0] != "Client Name" or
            headers[6] != "Branch Code" or headers[7] != "Client Name" or
            headers[10] != "Branch Code" or headers[12] != "Invoice No" or
            "Payment Received" not in headers[20]):
        reject("SOURCE_HEADER_CONTRACT_INVALID")
    if approved_headers is None:
        reject("INDEPENDENT_APPROVED_HEADERS_NOT_PROVIDED")
    elif approved_headers != headers:
        reject("INDEPENDENT_APPROVED_HEADERS_MISMATCH")
    if metadata_stable is not True:
        reject("DATASET_CHANGED_DURING_READ")
    if not isinstance(metadata, dict):
        reject("DATASET_METADATA_INVALID")
        metadata = {}
    expected = metadata.get("rows")
    source_sha = metadata.get("source_sha256")
    if (type(expected) is not int or not (1 <= expected <= 20000) or
            not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha) or
            metadata.get("state") != "READY" or
            metadata.get("original_headers") != headers or
            metadata.get("original_column_count") != 53 or
            metadata.get("original_columns_row_count") != expected):
        reject("SOURCE_METADATA_CONTRACT_INVALID")
    if not isinstance(baseline, list):
        baseline = []
        reject("BASELINE_ROWS_INVALID")
    if len(baseline) != expected:
        reject("BASELINE_ROW_COUNT_MISMATCH")
    if not isinstance(imported, list):
        imported = []
        reject("IMPORTED_ROWS_INVALID")

    nums = set()
    invoice_counts = Counter()
    digest = hashlib.sha256()
    for i, row in enumerate(baseline + imported):
        if not isinstance(row, dict):
            reject("SOURCE_ROW_INVALID")
            continue
        values = row.get("export_values")
        if (not isinstance(values, list) or len(values) != 53 or
                any(not isinstance(v, str) for v in values)):
            reject("SOURCE_ROW_POSITIONAL_VALUES_INVALID")
            continue
        if i < len(baseline):
            number = row.get("source_row")
            if type(number) is not int or number < 2 or number in nums:
                reject("BASELINE_SOURCE_ROW_NUMBER_INVALID")
            else:
                nums.add(number)
            if row.get("source_sha256") != source_sha:
                reject("BASELINE_ROW_SOURCE_SHA_MISMATCH")
        elif not re.fullmatch(r"[a-f0-9]{32}", str(row.get("import_receipt", ""))):
            reject("IMPORTED_ROW_RECEIPT_INVALID")
        if values[12]:
            invoice_counts[values[12]] += 1
        canonical = [i < len(baseline), row.get("source_row"),
                     row.get("import_receipt") if i >= len(baseline) else None, values]
        digest.update((json.dumps(canonical, ensure_ascii=False, default=str,
                                  separators=(",", ":")) + "\n").encode("utf-8"))
    if type(expected) is int and nums != set(range(2, expected + 2)):
        reject("BASELINE_SOURCE_ROW_SEQUENCE_INCOMPLETE")

    if not isinstance(receipt_audit, dict) or receipt_audit.get("result") != "PASS_ZERO_IMPORTS":
        reject("IMPORT_LEDGER_NOT_INDEPENDENTLY_CERTIFIED")
    if isinstance(receipt_audit, dict) and receipt_audit.get("completed_import_row_count") != len(imported):
        reject("IMPORT_LEDGER_ROW_COUNT_MISMATCH")

    if not isinstance(report_manifest, dict):
        reject("PRIVATE_REPORT_MANIFEST_NOT_PROVIDED")
        report_manifest = {}
    else:
        checks = {
            "dataset_id": dataset_id, "source_sha256": source_sha,
            "baseline_rows": len(baseline),
            "completed_import_rows": len(imported),
            "all_invoice_rows": len(baseline) + len(imported),
            "full_schema_columns": 53, "report_columns": 18,
        }
        if any(type(report_manifest.get(key)) is not type(val) or
               report_manifest.get(key) != val for key, val in checks.items()):
            reject("PRIVATE_REPORT_MANIFEST_MISMATCH")
        if report_manifest.get("release_status") != "PASSED":
            reject("CREDIT_NOTE_REPORT_REQUIRES_REVIEW")
        expected_digest = report_manifest.get("report_sha256")
        if not isinstance(expected_digest, str) or not SHA_RE.fullmatch(expected_digest):
            reject("PRIVATE_REPORT_SHA_INVALID")
        elif report_bytes is None:
            reject("PRIVATE_REPORT_CSV_NOT_PROVIDED")
        elif hashlib.sha256(report_bytes).hexdigest() != expected_digest:
            reject("PRIVATE_REPORT_CSV_SHA_MISMATCH")
        else:
            try:
                rows = csv.reader(io.StringIO(report_bytes.decode("utf-8-sig"), newline=""))
                header = next(rows)
                if len(header) != 18:
                    reject("PRIVATE_REPORT_HEADER_INVALID")
                nrows = 0
                for values in rows:
                    nrows += 1
                    if len(values) != 18 or nrows > 20000:
                        reject("PRIVATE_REPORT_ROWS_INVALID")
                        break
                if nrows != len(baseline) + len(imported):
                    reject("PRIVATE_REPORT_ROW_COUNT_MISMATCH")
            except (StopIteration, csv.Error, UnicodeDecodeError, ValueError):
                reject("PRIVATE_REPORT_CSV_UNREADABLE")

    return {
        "result": "R2_EVIDENCE_COLLECTED_NOT_RELEASE_APPROVAL" if not blockers else "REVIEW_REQUIRED",
        "scope": "SOURCE_RECEIPT_REPORT_READ_ONLY",
        "source_header_columns": len(headers),
        "source_header_sha256": _sha(headers),
        "baseline_rows": len(baseline),
        "completed_import_rows": len(imported),
        "total_invoice_rows": len(baseline) + len(imported),
        "distinct_nonblank_invoice_numbers": len(invoice_counts),
        "duplicate_invoice_numbers": sum(count > 1 for count in invoice_counts.values()),
        "rowset_sha256": digest.hexdigest(),
        "import_receipt_audit_result": receipt_audit.get("result") if isinstance(receipt_audit, dict) else None,
        "import_receipt_blockers": receipt_audit.get("blockers", []) if isinstance(receipt_audit, dict) else [],
        "blockers": blockers,
        "snapshot_freshness": "NOT_INDEPENDENTLY_CERTIFIED",
        "production_release_approved": False,
        "financial_execution": "RESTRICTED",
        "database_writes": False,
        "cloud_deployment": False,
    }


def _json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only, private SBI R2 source and report audit")
    p.add_argument("--live-read", action="store_true", help="Explicitly permit Firestore reads")
    p.add_argument("--manifest", help="Private CREDIT NOTE report manifest; never commit")
    p.add_argument("--report-csv", help="Private 18-column CREDIT NOTE CSV; never commit")
    p.add_argument("--approved-headers", help="Independently approved 53-header JSON list")
    p.add_argument("--output-dir", default=str(Path.home() / "sbi-private-audits"))
    args = p.parse_args(argv)
    if not args.live_read:
        p.error("Firestore was NOT accessed. Pass --live-read to permit read-only queries.")
    if bool(args.manifest) != bool(args.report_csv):
        p.error("--manifest and --report-csv must be supplied together")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
    from google.cloud import firestore
    from report_api import DATASET, load_report_rows_v142
    from import_receipt_audit import audit_firestore_v140
    from invoice_source_schema import HEADERS_53

    manifest = _json_file(args.manifest)
    approved = _json_file(args.approved_headers)
    if approved is not None and not isinstance(approved, list):
        raise ValueError("Approved header evidence must be a JSON list")
    csv_bytes = Path(args.report_csv).read_bytes() if args.report_csv else None
    db = firestore.Client(project=PROJECT, database="(default)")
    dataset = db.collection("dashboard_report_datasets").document(DATASET)
    before = dataset.get(timeout=30, retry=None)
    if not before.exists:
        raise ValueError("Expected baseline dataset does not exist")
    baseline, imported = load_report_rows_v142(db)
    receipts = audit_firestore_v140(db, manifest if isinstance(manifest, dict) else {})
    after = dataset.get(timeout=30, retry=None)
    stable = (after.exists and before.update_time == after.update_time and
              before.to_dict() == after.to_dict())
    outcome = evaluate(
        baseline, imported, after.to_dict() if after.exists else {},
        HEADERS_53, receipts, dataset_id=DATASET,
        report_manifest=manifest, report_bytes=csv_bytes,
        approved_headers=approved, metadata_stable=stable,
    )
    outcome["checked_utc"] = datetime.now(timezone.utc).isoformat()
    outcome["project"] = PROJECT
    folder = Path(args.output_dir).expanduser()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = folder / ("SBI_R2_READ_ONLY_" + stamp + ".json")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(outcome, out, indent=2, sort_keys=True)
        out.write("\n")
    print("R2_AUDIT_RESULT=" + outcome["result"])
    print("BASELINE_ROWS=" + str(outcome["baseline_rows"]))
    print("COMPLETED_IMPORT_ROWS=" + str(outcome["completed_import_rows"]))
    print("TOTAL_INVOICE_ROWS=" + str(outcome["total_invoice_rows"]))
    print("DUPLICATE_INVOICE_NUMBERS=" + str(outcome["duplicate_invoice_numbers"]))
    print("BLOCKERS=" + (",".join(outcome["blockers"]) or "NONE"))
    print("LOCAL_PRIVATE_RECEIPT=" + str(path))
    print("DATABASE_WRITES=0")
    print("FINANCIAL_EXECUTION=RESTRICTED")
    return 0 if not outcome["blockers"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Error messages may include private Firestore values: never echo them.
        print("R2_AUDIT_RESULT=ERROR")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("DATABASE_WRITES=0")
        sys.exit(3)
