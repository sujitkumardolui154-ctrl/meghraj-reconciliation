#!/usr/bin/env python3
"""A08 private read-only 53-column source vs exported report parity audit.

Only independently provided local source files and expected SHA256 digests are
used. It neither fetches Firestore nor recalculates settlement or TDS.
All 53 original positions and duplicate header labels are preserved.
The three primary reports must exactly partition all original rows; the
Balance Review report is allowed to overlap but must be source-contained.
Only aggregate exception counts/hashes are printed. Original source rows,
customer names, invoice IDs and monetary values never leave the local host.

Example (manifest contains approval-source-provided SHA256, not auto-filled):
  python tools/sbi_financial_report_parity.py \
    --original private/ORIGINAL_53.csv \
    --source-sha256 <independently authenticated 64-hex digest> \
    --report-manifest private/approved_report_manifest.json

Report manifest: {"reports": {"unpaid":{"path":"...","sha256":"..."},
 "ok": {...},"error-value":{...},"balance-review":{...}}}
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEADERS = json.loads(
    (ROOT / "backend_source" / "invoice_import_contract.json").read_text(
        encoding="utf-8")
)["headers"]
PRIMARY = ("unpaid", "ok", "error-value")
OPTIONAL = ("balance-review",)
MAX_BYTES = 100 * 1024 * 1024
MAX_ROWS = 20000
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
MONEY_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


class ParityBlocked(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load_verified_csv(path, expected_sha):
    if (not isinstance(expected_sha, str)
            or SHA_RE.fullmatch(expected_sha) is None):
        raise ParityBlocked("INDEPENDENT_SOURCE_DIGEST_REQUIRED")
    path = Path(path)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > MAX_BYTES):
        raise ParityBlocked("PRIVATE_CSV_MISSING_OR_UNSAFE")
    raw = path.read_bytes()
    if _sha(raw) != expected_sha:
        raise ParityBlocked("EXTERNAL_SOURCE_SHA256_MISMATCH")
    try:
        lines = iter(csv.reader(raw.decode("utf-8-sig").splitlines(), strict=True))
        headers = next(lines)
        if headers != SOURCE_HEADERS:
            raise ParityBlocked("ORIGINAL_53_HEADER_ORDER_MISMATCH")
        result = []
        for row in lines:
            if len(row) != 53:
                raise ParityBlocked("REPORT_ROW_WIDTH_NOT_53")
            result.append(tuple(row))
            if len(result) > MAX_ROWS:
                raise ParityBlocked("REPORT_ROW_LIMIT_EXCEEDED")
    except (UnicodeError, csv.Error, StopIteration):
        raise ParityBlocked("PRIVATE_CSV_INVALID") from None
    return result


def _export_cell(value):
    if (value.lstrip().startswith(("=", "+", "-", "@"))
            or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


def _amount(value):
    text = value.strip()
    if not text or MONEY_RE.fullmatch(text) is None:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def evaluate(source_rows, report_rows):
    """Compare exact original records to 53-column output, never financial edits."""
    if not isinstance(source_rows, list):
        raise ParityBlocked("SOURCE_ROWS_INVALID")
    if not isinstance(report_rows, dict) or set(report_rows) not in (
        set(PRIMARY), set(PRIMARY + OPTIONAL),
    ):
        raise ParityBlocked("PRIMARY_REPORT_PARTITION_REQUIRED")
    for name, rows in [("source", source_rows)] + list(report_rows.items()):
        if (not isinstance(rows, list) or len(rows) > MAX_ROWS
                or any(not isinstance(r, (list, tuple)) or len(r) != 53
                       or any(not isinstance(cell, str) for cell in r)
                       for r in rows)):
            raise ParityBlocked("MALFORMED_SOURCE_OR_REPORT_ROW")
    expected = Counter(tuple(_export_cell(v) for v in row)
                       for row in source_rows)
    union = Counter()
    blockers = []
    for kind in PRIMARY:
        group = Counter(tuple(row) for row in report_rows[kind])
        if not (group <= expected):
            blockers.append("SOURCE_TO_" + kind.upper().replace("-", "_")
                            + "_REPORT_MISMATCH")
        union.update(group)
    if union != expected:
        blockers.append("PRIMARY_REPORT_TOTAL_OR_ROWSET_MISMATCH")
    if "balance-review" in report_rows and not (
            Counter(tuple(row) for row in report_rows["balance-review"])
            <= expected):
        blockers.append("BALANCE_REVIEW_SOURCE_MISMATCH")

    invoice_counts = Counter(str(row[12]).strip() for row in source_rows
                             if row[12].strip())
    # Arithmetic is an independent, *diagnostic* comparison of raw source
    # taxable+CGST+SGST to raw gross. Do not rewrite amounts or infer TDS.
    gst_mismatches = 0
    gst_unverifiable = 0
    cents = Decimal("0.01")
    for row in source_rows:
        amounts = [_amount(row[pos]) for pos in (13, 14, 15, 16)]
        if any(v is None for v in amounts):
            gst_unverifiable += 1
            continue
        gross_expected = sum(amounts[:3], Decimal("0")).quantize(
            cents, rounding=ROUND_HALF_UP)
        gross_actual = amounts[3].quantize(cents, rounding=ROUND_HALF_UP)
        if gross_expected != gross_actual:
            gst_mismatches += 1
    if gst_mismatches:
        blockers.append("GST_SOURCE_ARITHMETIC_EXCEPTIONS_REQUIRE_REVIEW")
    if gst_unverifiable:
        blockers.append("GST_SOURCE_VALUES_NOT_ALL_NUMERIC")
    if any(count > 1 for count in invoice_counts.values()):
        blockers.append("DUPLICATE_INVOICE_GROUPS_REQUIRE_REVIEW")

    return {
        "result": "REVIEW_REQUIRED" if blockers else "PARTITION_MATCH_SOURCE_APPROVAL_PENDING",
        "source_rows": len(source_rows),
        "partition_report_rows": sum(len(report_rows[k]) for k in PRIMARY),
        "report_row_counts": {key: len(value) for key, value in report_rows.items()},
        "duplicate_invoice_groups": sum(v > 1 for v in invoice_counts.values()),
        "gst_arithmetic_mismatch_rows": gst_mismatches,
        "gst_arithmetic_unverifiable_rows": gst_unverifiable,
        "status_comparison_with_bank_payments": "NOT_PERFORMED",
        "settlement_or_tds_recalculation": False,
        "original_values_mutated": False,
        "external_independent_provenance_verified": False,
        "blockers": sorted(set(blockers)),
        "financial_execution": "RESTRICTED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--report-manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        mf = args.report_manifest
        if mf.is_symlink() or not mf.is_file() or mf.stat().st_size > 65536:
            raise ParityBlocked("REPORT_MANIFEST_MISSING_OR_UNSAFE")
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        entries = manifest.get("reports") if isinstance(manifest, dict) else None
        if not isinstance(entries, dict):
            raise ParityBlocked("REPORT_MANIFEST_INVALID")
        source = _load_verified_csv(args.original, args.source_sha256)
        reports = {}
        for kind, spec in entries.items():
            if (kind not in PRIMARY + OPTIONAL or not isinstance(spec, dict)
                    or not isinstance(spec.get("path"), str)):
                raise ParityBlocked("REPORT_MANIFEST_ITEM_INVALID")
            reports[kind] = _load_verified_csv(spec["path"], spec.get("sha256"))
        result = evaluate(source, reports)
    except (ParityBlocked, OSError, ValueError, TypeError, KeyError) as exc:
        blocker = str(exc) if isinstance(exc, ParityBlocked) else "PRIVATE_INPUT_INVALID"
        result = {"result": "REVIEW_REQUIRED", "blockers": [blocker],
                  "financial_execution": "RESTRICTED",
                  "original_values_mutated": False}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["result"] == "PARTITION_MATCH_SOURCE_APPROVAL_PENDING" else 2


if __name__ == "__main__":
    sys.exit(main())
