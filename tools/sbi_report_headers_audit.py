#!/usr/bin/env python3
"""Read-only SBI A03 header audit with independently supplied reference files.

Use locally with approved files, never commit private report files:
  python tools/sbi_report_headers_audit.py \
    --approved-53-json /private/approved_source_53.json \
    --approved-v218-json /private/approved_v218_headers.json \
    --observed-v218-csv /private/report_v218.csv \
    [--observed-53-csv /private/original_53_export.csv]

A match certifies neither the provenance of caller references, the financial
values, nor release permission. It compares EXACT positions including duplicate
labels and source capitalization, and keeps customer data out of stdout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend_source" / "invoice_import_contract.json"
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ROWS = 50000
MAX_JSON_BYTES = 65536


class ReportHeaderReviewRequired(ValueError):
    pass


def _canonical_hash(values):
    return hashlib.sha256(json.dumps(
        values, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _exact_headers(data, expected_width=None):
    if (not isinstance(data, list) or not data
            or any(not isinstance(value, str) or value == "" for value in data)
            or (expected_width is not None and len(data) != expected_width)):
        raise ReportHeaderReviewRequired("HEADER_REFERENCE_INVALID")
    return data


def _read_headers_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ReportHeaderReviewRequired("APPROVED_REFERENCE_MISSING_OR_UNSAFE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ReportHeaderReviewRequired("APPROVED_REFERENCE_UNREADABLE") from None
    return _exact_headers(data)


def _csv_stats(path):
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > MAX_CSV_BYTES):
        raise ReportHeaderReviewRequired("OBSERVED_CSV_MISSING_OR_UNSAFE")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = _exact_headers(next(reader))
            count = 0
            for row in reader:
                if len(row) != len(headers):
                    raise ReportHeaderReviewRequired("OBSERVED_CSV_ROW_WIDTH_MISMATCH")
                count += 1
                if count > MAX_ROWS:
                    raise ReportHeaderReviewRequired("OBSERVED_CSV_TOO_MANY_ROWS")
            return headers, count
    except (StopIteration, UnicodeError, csv.Error, OSError):
        raise ReportHeaderReviewRequired("OBSERVED_CSV_UNREADABLE") from None


def audit(approved53, approved_v218, observed_v218,
          observed53=None):
    """Compare source/report headers by position, not normalized labels."""
    contract53 = _exact_headers(
        json.loads(SOURCE.read_text(encoding="utf-8"))["headers"], 53
    )
    approved53 = _exact_headers(approved53, 53)
    approved_v218 = _exact_headers(approved_v218)
    observed_v218 = _exact_headers(observed_v218)
    blockers = []
    if approved53 != contract53:
        blockers.append("ORIGINAL_53_APPROVED_POSITIONS_MISMATCH")
    if observed_v218 != approved_v218:
        blockers.append("V218_OUTPUT_HEADER_POSITIONS_MISMATCH")
    if observed53 is not None and _exact_headers(observed53) != approved53:
        blockers.append("ORIGINAL_53_EXPORT_HEADER_POSITIONS_MISMATCH")
    return {
        "result": ("HEADER_LAYOUT_MATCH_CANDIDATE_REVIEW_REQUIRED"
                   if not blockers else "REVIEW_REQUIRED"),
        "blockers": blockers,
        "source_53_columns": len(contract53),
        "approved_53_sha256": _canonical_hash(approved53),
        "repository_53_sha256": _canonical_hash(contract53),
        "approved_v218_columns": len(approved_v218),
        "approved_v218_header_sha256": _canonical_hash(approved_v218),
        "observed_v218_header_sha256": _canonical_hash(observed_v218),
        "checked_original_53_export": observed53 is not None,
        "independent_reference_authenticity_verified": False,
        "financial_values_compared": False,
        "source_rows_modified": 0,
        "financial_production_release": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-53-json", type=Path, required=True)
    parser.add_argument("--approved-v218-json", type=Path, required=True)
    parser.add_argument("--observed-v218-csv", type=Path, required=True)
    parser.add_argument("--observed-53-csv", type=Path)
    args = parser.parse_args(argv)
    try:
        approved53 = _read_headers_json(args.approved_53_json)
        approved_v218 = _read_headers_json(args.approved_v218_json)
        observed_v218, count = _csv_stats(args.observed_v218_csv)
        observed53 = None
        if args.observed_53_csv:
            observed53, original_count = _csv_stats(args.observed_53_csv)
        result = audit(approved53, approved_v218, observed_v218, observed53)
    except (ReportHeaderReviewRequired, OSError, ValueError, KeyError) as error:
        reason = (str(error) if isinstance(error, ReportHeaderReviewRequired)
                  else "LOCAL_HEADER_INPUT_INVALID")
        result = {
            "result": "REVIEW_REQUIRED", "blockers": [reason],
            "financial_production_release": False,
            "source_rows_modified": 0,
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if not result["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
