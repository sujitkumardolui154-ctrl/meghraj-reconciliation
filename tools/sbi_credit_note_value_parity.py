#!/usr/bin/env python3
"""Independent offline 53-source-to-18-CREDIT-NOTE value parity.

Source and report CSV bytes MUST have separately supplied expected SHA256
digests. This tool never retrieves the financial DB, calls a report generator,
reconciles bank payments, changes status or uploads customer data.

Every original approved field is compared by position and text (including
financial values), never by a duplicate header label or a fuzzy invoice key.
Exact multiset comparison preserves duplicate rows without silently deduping.
Only aggregate diagnostics are emitted. A match is not release approval.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEADERS = json.loads(
    (ROOT / "backend_source/invoice_import_contract.json").read_text(encoding="utf-8")
)["headers"]
SOURCE_POSITIONS = (1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
CREDIT_NOTE_HEADERS = (
    "FY", "Invoice Branch", "Invoice Generate Location", "Month",
    "Invoice Date", "Branch Code", "Client Name", "GST NO", "Invoice No",
    "Taxable Amount", "CGST", "SGST", "Total Bill Amount", "Less TDS",
    "Actual Reciaveable Ammount Deductionof TDS (Including GST)",
    "Taxable Amount Less TDS (Without GST)",
    "Payment Received (If With GST or Excluding GST)", "Credi note",
)
SOURCE_INVOICE_INDEX = 12
SOURCE_PAYMENT_INDEX = 20
SOURCE_BASELINE_ROWS = 14374
MAX_ROWS = 20000
MAX_FILE_BYTES = 100 * 1024 * 1024
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
# Approved narration token and common typo; CREDIT NOTEBOOK is not a credit note.
CREDIT_NOTE_RE = re.compile(
    r"(?<!\w)CREDIT\s+NO(?:TE|RTE)(?!\w)", re.IGNORECASE
)
MONETARY_FIELDS = (9, 10, 11, 12, 13, 14, 15, 16)


class AuditBlocked(ValueError):
    pass


def _csv_protect(value):
    """Mirror the declared CSV injection safety encoding, never modify source."""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def _read_verified_csv(path, expected_sha, expected_headers):
    """Strict, bounded local CSV with external digest and exact header position."""
    if not isinstance(expected_sha, str) or not DIGEST_RE.fullmatch(expected_sha):
        raise AuditBlocked("INDEPENDENT_FILE_SHA256_REQUIRED")
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
        raise AuditBlocked("PRIVATE_FILE_UNSAFE_OR_NOT_FOUND")
    raw = file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise AuditBlocked("EXPECTED_FILE_SHA256_MISMATCH")
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader)
        if header != list(expected_headers):
            raise AuditBlocked("ORDERED_REPORT_HEADER_MISMATCH")
        rows = []
        for row in reader:
            if len(row) != len(expected_headers):
                raise AuditBlocked("REPORT_ROW_WIDTH_INVALID")
            rows.append(tuple(row))
            if len(rows) > MAX_ROWS:
                raise AuditBlocked("ROW_LIMIT_EXCEEDED")
        return rows
    except (UnicodeError, csv.Error, StopIteration):
        raise AuditBlocked("PRIVATE_CSV_INVALID") from None


def _expected_credit_note(source_row):
    fields = tuple(_csv_protect(source_row[pos]) for pos in SOURCE_POSITIONS)
    return fields + (
        "CREDIT NOTE" if CREDIT_NOTE_RE.search(source_row[SOURCE_PAYMENT_INDEX]) else "",
    )


def evaluate(source_rows, credit_note_rows, *, baseline_rows=SOURCE_BASELINE_ROWS):
    """Independent comparison. Does NOT validate actual payment classification."""
    if (
        not isinstance(source_rows, list) or not isinstance(credit_note_rows, list)
        or type(baseline_rows) is not int or baseline_rows < 0
        or len(source_rows) > MAX_ROWS or len(credit_note_rows) > MAX_ROWS
    ):
        raise AuditBlocked("INPUT_ROWS_INVALID")
    for label, rows, width in (
        ("SOURCE", source_rows, 53),
        ("CREDIT_NOTE", credit_note_rows, 18),
    ):
        if any(
            not isinstance(row, (tuple, list)) or len(row) != width
            or any(not isinstance(cell, str) for cell in row)
            for row in rows
        ):
            raise AuditBlocked(label + "_ROW_WIDTH_OR_CELL_INVALID")

    expected = [_expected_credit_note(row) for row in source_rows]
    observed = [tuple(row) for row in credit_note_rows]
    expected_values = Counter(row[:17] for row in expected)
    observed_values = Counter(row[:17] for row in observed)
    expected_all = Counter(expected)
    observed_all = Counter(observed)
    # Aggregated multiset deltas do not disclose identifiers or monetary values.
    value_missing = sum((expected_values - observed_values).values())
    value_extra = sum((observed_values - expected_values).values())
    row_missing = sum((expected_all - observed_all).values())
    row_extra = sum((observed_all - expected_all).values())

    fields = {}
    for i in range(17):
        want = Counter(row[i] for row in expected)
        got = Counter(row[i] for row in observed)
        deficit = sum((want - got).values())
        excess = sum((got - want).values())
        if deficit or excess:
            fields[str(i + 1).zfill(2)] = {
                "field": CREDIT_NOTE_HEADERS[i],
                "source_only_values": deficit,
                "report_only_values": excess,
            }

    invoice_records = defaultdict(list)
    missing_invoices = 0
    for row in source_rows:
        invoice = row[SOURCE_INVOICE_INDEX].strip()
        if not invoice:
            missing_invoices += 1
            continue
        invoice_records[invoice].append(
            (
                bool(CREDIT_NOTE_RE.search(row[SOURCE_PAYMENT_INDEX])),
                tuple(row[pos] for pos in SOURCE_POSITIONS),
            )
        )
    duplicate_groups = sum(len(group) > 1 for group in invoice_records.values())
    conflict_groups = sum(
        len(group) > 1 and any(flag for flag, _ in group)
        and (len({flag for flag, _ in group}) > 1
             or len({cells for _, cells in group}) > 1)
        for group in invoice_records.values()
    )
    flagged = sum(row[17] == "CREDIT NOTE" for row in observed)
    invalid_labels = sum(row[17] not in ("", "CREDIT NOTE") for row in observed)

    blockers = []
    if len(source_rows) != baseline_rows:
        blockers.append("BASELINE_SOURCE_ROW_COUNT_MISMATCH")
    if len(observed) != len(source_rows):
        blockers.append("REPORT_ROW_COUNT_MISMATCH")
    if value_missing or value_extra or fields:
        blockers.append("CREDIT_NOTE_SOURCE_VALUE_MISMATCH")
    if row_missing or row_extra:
        blockers.append("CREDIT_NOTE_FULL_ROW_OR_FLAG_MISMATCH")
    if invalid_labels:
        blockers.append("UNAPPROVED_CREDIT_NOTE_LABEL")
    if missing_invoices:
        blockers.append("INVOICE_NUMBER_MISSING_REVIEW")
    if duplicate_groups:
        blockers.append("DUPLICATE_INVOICE_GROUPS_REQUIRE_REVIEW")
    if conflict_groups:
        blockers.append("CREDIT_NOTE_CONFLICT_GROUPS_REQUIRE_REVIEW")

    status = (
        "REVIEW_REQUIRED" if blockers
        else "VALUE_PARITY_MATCH_SOURCE_APPROVAL_PENDING"
    )
    return {
        "status": status,
        "mode": "independent_offline_source_to_credit_note_value_parity",
        "original_53_headers_preserved": True,
        "credit_note_18_headers_preserved": True,
        "source_rows": len(source_rows),
        "credit_note_rows": len(observed),
        "expected_baseline_rows": baseline_rows,
        "all_17_original_fields_compared": True,
        "source_only_projected_records": value_missing,
        "report_only_projected_records": value_extra,
        "source_only_complete_records": row_missing,
        "report_only_complete_records": row_extra,
        "field_discrepancies": fields,
        "credit_note_flagged_report_rows": flagged,
        "credit_note_invalid_labels": invalid_labels,
        "missing_invoice_number_rows": missing_invoices,
        "duplicate_invoice_groups": duplicate_groups,
        "credit_note_conflict_groups": conflict_groups,
        "external_independent_source_approval_verified": False,
        "bank_payment_values_independently_certified": False,
        "financial_execution": "RESTRICTED",
        "financial_writes": 0,
        "source_rows_modified": 0,
        "production_release_approved": False,
        "blockers": sorted(set(blockers)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-53", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--credit-note-18", required=True, type=Path)
    parser.add_argument("--credit-note-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if len(SOURCE_HEADERS) != 53 or len(CREDIT_NOTE_HEADERS) != 18:
            raise AuditBlocked("APPROVED_CONTRACT_WIDTH_INVALID")
        source = _read_verified_csv(
            args.source_53, args.source_sha256, SOURCE_HEADERS
        )
        report = _read_verified_csv(
            args.credit_note_18, args.credit_note_sha256, CREDIT_NOTE_HEADERS
        )
        summary = evaluate(source, report)
    except (AuditBlocked, OSError, ValueError, TypeError, KeyError) as exc:
        issue = str(exc) if isinstance(exc, AuditBlocked) else "PRIVATE_INPUT_INVALID"
        summary = {
            "status": "REVIEW_REQUIRED",
            "blockers": [issue],
            "financial_execution": "RESTRICTED",
            "financial_writes": 0,
            "production_release_approved": False,
            "source_rows_modified": 0,
        }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if summary["status"] == "VALUE_PARITY_MATCH_SOURCE_APPROVAL_PENDING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
