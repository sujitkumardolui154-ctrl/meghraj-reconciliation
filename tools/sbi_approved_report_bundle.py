#!/usr/bin/env python3
"""Offline, fail-closed SBI consolidated approved-report CSV ZIP creator.

Input is a LOCAL private manifest and an explicit private report root.
No Firestore access, financial calculation, status mutation, web calls, or
production release. A manifest's approval declaration is caller-provided,
not independent evidence of approver authority.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

MAX_REPORT_BYTES = 40 * 1024 * 1024
MAX_REPORTS = 20
HASH = re.compile(r"[0-9a-f]{64}\Z")
IDS = frozenset({
    "unpaid", "ok", "balance_review", "suspense",
    "reconciliation_changes", "credit_note", "other_approved",
})


class ReportBundleBlocked(ValueError):
    pass


def _verified_report(spec: dict, private_root: Path) -> tuple[str, bytes, dict]:
    if not isinstance(spec, dict):
        raise ReportBundleBlocked("INVALID_REPORT_ENTRY")
    report_id = spec.get("report_id")
    relpath = spec.get("source_path")
    digest = spec.get("sha256")
    headers = spec.get("headers")
    rows = spec.get("expected_rows")
    approval = spec.get("approval_reference")
    if report_id not in IDS:
        raise ReportBundleBlocked("UNAPPROVED_REPORT_TYPE")
    if spec.get("approval_state") != "APPROVED" or not isinstance(approval, str) or not approval.strip():
        raise ReportBundleBlocked("APPROVAL_EVIDENCE_MISSING")
    if not isinstance(relpath, str) or not relpath or Path(relpath).is_absolute():
        raise ReportBundleBlocked("UNSAFE_REPORT_PATH")
    p = Path(relpath)
    if ".." in p.parts or p.suffix.lower() != ".csv":
        raise ReportBundleBlocked("UNSAFE_REPORT_PATH")
    source = (private_root / p).resolve()
    if not source.is_relative_to(private_root) or not source.is_file() or source.is_symlink():
        raise ReportBundleBlocked("UNSAFE_REPORT_FILE")
    if not isinstance(digest, str) or HASH.fullmatch(digest) is None:
        raise ReportBundleBlocked("INVALID_REPORT_SHA256")
    if (not isinstance(headers, list) or not headers or
            not all(isinstance(h, str) for h in headers) or
            not isinstance(rows, int) or isinstance(rows, bool) or rows < 0):
        raise ReportBundleBlocked("INVALID_REPORT_SCHEMA")
    if source.stat().st_size > MAX_REPORT_BYTES:
        raise ReportBundleBlocked("REPORT_TOO_LARGE")
    data = source.read_bytes()
    real_digest = hashlib.sha256(data).hexdigest()
    if real_digest != digest:
        raise ReportBundleBlocked("SOURCE_REPORT_SHA256_MISMATCH")
    try:
        text = data.decode("utf-8-sig")
        csv_reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        actual_headers = next(csv_reader)
        if actual_headers != headers:
            raise ReportBundleBlocked("APPROVED_HEADER_MISMATCH")
        count = 0
        for row in csv_reader:
            if len(row) != len(headers):
                raise ReportBundleBlocked("ROW_WIDTH_MISMATCH")
            count += 1
        if count != rows:
            raise ReportBundleBlocked("REPORT_ROW_COUNT_MISMATCH")
    except (UnicodeError, csv.Error, StopIteration):
        raise ReportBundleBlocked("INVALID_REPORT_CSV") from None
    archive_name = report_id + ".csv"
    metadata = {
        "report_id": report_id,
        "archive_name": archive_name,
        "sha256": real_digest,
        "rows": count,
        "columns": len(headers),
        "approved_header_order": headers,
        "approval_reference": approval,
        "approval_independently_verified": False,
    }
    return archive_name, data, metadata


def make_bundle(manifest: dict, private_root: Path, output: Path) -> dict:
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
        raise ReportBundleBlocked("MANIFEST_VERSION_REQUIRED")
    dataset_hash = manifest.get("source_dataset_sha256")
    reports = manifest.get("reports")
    if not isinstance(dataset_hash, str) or HASH.fullmatch(dataset_hash) is None:
        raise ReportBundleBlocked("DATASET_SHA256_REQUIRED")
    if not isinstance(reports, list) or not (1 <= len(reports) <= MAX_REPORTS):
        raise ReportBundleBlocked("REPORT_COUNT_INVALID")
    private_root = private_root.resolve(strict=True)
    if not private_root.is_dir():
        raise ReportBundleBlocked("PRIVATE_REPORT_ROOT_MISSING")
    if output.suffix.lower() != ".zip" or output.exists() or output.is_symlink():
        raise ReportBundleBlocked("OUTPUT_MUST_BE_NEW_ZIP")
    if not output.parent.is_dir():
        raise ReportBundleBlocked("OUTPUT_DIRECTORY_MISSING")
    checked = [_verified_report(item, private_root) for item in reports]
    names = [name for name, _, _ in checked]
    if len(set(names)) != len(names):
        raise ReportBundleBlocked("DUPLICATE_REPORT_TYPE")
    metadata = {
        "manifest_version": 1,
        "source_dataset_sha256": dataset_hash,
        "bundle_kind": "APPROVED_INPUT_CSVS_OFFLINE",
        "authorization_claim": "CALLER_PROVIDED_NOT_INDEPENDENTLY_CERTIFIED",
        "financial_reconciliation_executed": False,
        "financial_production_release": False,
        "reports": [details for _, _, details in sorted(checked)],
    }
    payload = (json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".sbi-bundle.", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as sink:
            with ZipFile(sink, mode="w", compression=ZIP_DEFLATED,
                         compresslevel=6, allowZip64=False) as archive:
                for name, data in [(n, b) for n, b, _ in sorted(checked)] + [("manifest.json", payload)]:
                    info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, data, compress_type=ZIP_DEFLATED)
            sink.flush()
            os.fsync(sink.fileno())
        os.chmod(temp, 0o600)
        # Hard link provides atomic create-if-absent; never overwrite user output.
        os.link(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {
        "status": "OFFLINE_BUNDLE_PREPARED_REVIEW_REQUIRED",
        "report_count": len(checked),
        "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "financial_writes": 0,
        "financial_release": "RESTRICTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = make_bundle(manifest, args.private_root, args.output)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        reason = str(error) if isinstance(error, ReportBundleBlocked) else "LOCAL_INPUT_ERROR"
        print("SBI_REPORT_BUNDLE=BLOCKED")
        print("BLOCKER=" + reason)
        print("FINANCIAL_WRITES=0")
        return 2
    print("SBI_REPORT_BUNDLE=" + result["status"])
    print("REPORT_COUNT=" + str(result["report_count"]))
    print("BUNDLE_SHA256=" + result["bundle_sha256"])
    print("FINANCIAL_WRITES=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
