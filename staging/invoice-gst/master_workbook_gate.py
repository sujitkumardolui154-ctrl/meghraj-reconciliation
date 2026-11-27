"""Read-only gate for the exact private SBI_SOL_Branch_Master_FINAL.xlsx layout.

This workbook has a 1,484-record canonical 'Clean Branch Master' table,
followed by supplementary review records. A separate 'Review Summary' declares
'WORKING REVIEW — NOT FINAL'. Never silently promote this to a verified DB.

This code reads the file in the PRIVATE runtime; no source workbook or customer
addresses should be uploaded to public GitHub or into CI logs.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

MASTER_TAB = "Clean Branch Master"
SUMMARY_TAB = "Review Summary"
REQUIRED = ("Official Branch Name", "SOL ID", "Address", "Pincode",
            "Billing Location (Most Frequent)", "Review Flag")
SOL_RE = re.compile(r"^[0-9]{5}$")


class MasterReviewError(ValueError):
    pass


def _approved_count_and_status(workbook):
    if SUMMARY_TAB not in workbook.sheetnames:
        raise MasterReviewError("REVIEW_SUMMARY_SHEET_MISSING")
    sheet = workbook[SUMMARY_TAB]
    values = {}
    for row in sheet.iter_rows(min_row=1, max_col=3, values_only=True):
        if row and isinstance(row[0], str):
            values[row[0].strip()] = row[1]
    count = values.get("Canonical master rows")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise MasterReviewError("CANONICAL_COUNT_NOT_PROVEN")
    status = values.get("Production status")
    if not isinstance(status, str):
        raise MasterReviewError("PRODUCTION_STATUS_NOT_PROVEN")
    return count, status


def inspect_private_workbook(path: str | Path):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise MasterReviewError("SOURCE_XLSX_REQUIRED")
    blob = path.read_bytes()
    file_digest = hashlib.sha256(blob).hexdigest()
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if MASTER_TAB not in workbook.sheetnames:
            raise MasterReviewError("CLEAN_BRANCH_MASTER_TAB_MISSING")
        expected_count, declared_status = _approved_count_and_status(workbook)
        sheet = workbook[MASTER_TAB]
        matrix = sheet.iter_rows(values_only=True)
        headers = next(matrix, ())
        names = {str(name).strip(): i for i, name in enumerate(headers) if name is not None}
        if any(h not in names for h in REQUIRED):
            raise MasterReviewError("MASTER_HEADER_CONTRACT_MISMATCH")
        if sheet.max_row < expected_count + 1:
            raise MasterReviewError("CANONICAL_ROW_COUNT_SHORT")
        candidates = []
        issues = []
        seen_sols = {}
        alias_owner = {}
        review_flags = Counter()
        full_count = 0
        supplemental_count = 0
        for n, row in enumerate(matrix, start=2):
            fields = {key: row[index] if index < len(row) else None
                      for key,index in names.items()}
            if n > expected_count + 1:
                supplemental_count += 1
                continue
            full_count += 1
            official = fields["Official Branch Name"]
            sol = fields["SOL ID"]
            if not isinstance(official, str) or not official.strip():
                issues.append((n, "OFFICIAL_NAME_UNVERIFIED"))
                continue
            if not isinstance(sol, str) or not SOL_RE.fullmatch(sol):
                issues.append((n, "SOURCE_SOL_NOT_EXACT_FIVE_DIGIT_TEXT"))
                continue
            if sol in seen_sols:
                issues.append((n, "DUPLICATE_CANONICAL_SOL"))
                continue
            seen_sols[sol] = n
            address = fields.get("Address")
            pin = fields.get("Pincode")
            flag = fields.get("Review Flag")
            if isinstance(flag, str) and flag.strip():
                review_flags[flag.strip()] += 1
            if not isinstance(address, str) or not address.strip():
                issues.append((n, "CANONICAL_ADDRESS_MISSING"))
            if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6}", pin.strip()):
                issues.append((n, "CANONICAL_PINCODE_NOT_TEXT_SIX_DIGIT"))
            if fields.get("Billing Location Selection Status") == "No billing location found":
                # This does not prove client is wrong, but it explicitly blocks
                # auto-populating the invoice generation location.
                issues.append((n, "INVOICE_GENERATION_LOCATION_NOT_PROVEN"))
            aliases = []
            for k in ("Search Aliases", "Search Aliases2"):
                raw = fields.get(k)
                if raw is not None and str(raw).strip():
                    aliases.extend(x.strip() for x in str(raw).split(";") if x.strip())
            # Alias collisions require review; never use master aliases to
            # override a SOL or infer a different official name.
            for alias in aliases:
                norm = re.sub(r"[^A-Z0-9]+", " ", alias.upper()).strip()
                owner = alias_owner.setdefault(norm, (sol,n))
                if owner[0] != sol:
                    issues.append((n, "ALIAS_POINTS_TO_MULTIPLE_SOL"))
            candidates.append({
                "source_row": n,
                "Official Branch Name": official.strip(),
                "SOL ID": sol,
                "Search Aliases": fields.get("Search Aliases") or "",
                "Address": address if isinstance(address, str) else "",
                "Pincode": pin if isinstance(pin, str) else "",
                "Review Flag": flag or "",
            })
        if full_count != expected_count:
            raise MasterReviewError("CANONICAL_COUNT_DISAGREES_WITH_SOURCE")
        # Never pretend that a WORKING REVIEW workbook is released.
        if "WORKING REVIEW" in declared_status.upper() or "NOT FINAL" in declared_status.upper():
            source_status = "WORKING_REVIEW_NOT_APPROVED_FOR_AUTOMATIC_IMPORT"
        else:
            source_status = "DECLARED_STATUS_REQUIRES_INDEPENDENT_AUTHORIZATION"
        return {
            "source_sha256": file_digest,
            "source_name": path.name,
            "canonical_count": full_count,
            "supplemental_review_rows_excluded": supplemental_count,
            "canonical_candidates": len(candidates),
            "issue_count": len(issues),
            "issue_counts": dict(Counter(code for _,code in issues)),
            "review_flag_counts": dict(review_flags),
            "source_status": source_status,
            "declared_production_status": declared_status,
            "candidates": candidates,
            "issues": [{"row": n, "code": code} for n,code in issues],
            "automatic_database_write": False,
        }
    finally:
        workbook.close()


def export_private_canonical_csv(source_xlsx, destination_csv, *, expected_source_sha):
    """Export only canonical SOL candidates to a local private 0600 CSV.

    The source remains WORKING REVIEW and this export is not verified master
    approval. It exists solely to feed the separate evidence-gated QA importer.
    Do not put this CSV into GitHub.
    """
    import csv
    import os
    if not re.fullmatch(r"[a-f0-9]{64}", expected_source_sha or ""):
        raise MasterReviewError("APPROVED_SOURCE_SHA_REQUIRED")
    audit = inspect_private_workbook(source_xlsx)
    if audit["source_sha256"] != expected_source_sha:
        raise MasterReviewError("SOURCE_WORKBOOK_DIGEST_MISMATCH")
    target = Path(destination_csv)
    if target.suffix.lower() != ".csv" or target.exists():
        raise MasterReviewError("PRIVATE_CSV_TARGET_MUST_BE_NEW")
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=("Official Branch Name", "SOL ID", "Search Aliases")
            )
            writer.writeheader()
            for row in audit["candidates"]:
                writer.writerow({key: row[key] for key in writer.fieldnames})
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        "source_sha256": audit["source_sha256"],
        "canonical_candidate_rows_exported": len(audit["candidates"]),
        "supplemental_review_rows_excluded": audit["supplemental_review_rows_excluded"],
        "source_status": audit["source_status"],
        "verified_customer_records_imported": 0,
    }


def safe_audit_summary(audit):
    """No branch addresses, names, aliases or SOL IDs leave private runtime."""
    keys = ("source_sha256","source_name","canonical_count",
            "supplemental_review_rows_excluded","canonical_candidates",
            "issue_count","issue_counts","review_flag_counts",
            "source_status","declared_production_status",
            "automatic_database_write")
    return {k:audit[k] for k in keys}

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--source-xlsx", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--candidate-output", required=True,
                        help="PRIVATE destination, do not commit to GitHub")
    parser.add_argument("--audit-output",
                        help="Optional PRIVATE machine-readable counts, no client rows")
    args = parser.parse_args()
    result = export_private_canonical_csv(
        args.source_xlsx,
        args.candidate_output,
        expected_source_sha=args.expected_sha256
    )
    if args.audit_output:
        Path(args.audit_output).write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    print("CANONICAL_CANDIDATES_EXPORTED=", result["canonical_candidate_rows_exported"])
    print("SUPPLEMENTAL_REVIEW_ROWS_EXCLUDED=", result["supplemental_review_rows_excluded"])
    print("STATUS=", result["source_status"])
    print("DATABASE_WRITES=NONE")
