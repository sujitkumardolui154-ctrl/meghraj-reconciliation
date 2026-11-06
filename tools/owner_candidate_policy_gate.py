"""Read-only OWNER policy gate for SBI candidate-screen review (Issue #76).

This gate proves preservation/authorization of review methods, never actual
bank-to-invoice settlement. It has no database or network calls.
"""
import csv
import hashlib
from collections import Counter
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path

POLICY = {
    "SINGLE_POTENTIAL_SAME_SOL_TDS": "OWNER-RULE-01",
    "MULTIPLE_POTENTIAL_INVOICES": "OWNER-RULE-02",
    "NO_NEAR_EXACT_SAME_SOL_CANDIDATE": "OWNER-RULE-03",
}

REQUIRED_POLICY = {
    "Owner Review Policy Approval": "APPROVED_BY_ACCOUNT_HOLDER_POLICY_ONLY",
    "Independent Per-Row Payment Evidence": "NOT_VERIFIED_IN_OWNER_REVIEW_CSV",
    "New Owner-Approved Financial Allocation": "NONE_CONFIRMED_IN_THIS_REVIEW",
    "Financial Release Permission": "NOT_GRANTED_BY_POLICY_REVIEW",
    "Provisional Model Decision (NO WRITE)": "UNRESOLVED_REVIEW_REQUIRED",
    "New Allocation Approved": "NO",
}


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_owner_policy(original_file, reviewed_file, expected_counts=None):
    """Check exact original 32 CSV cells per row plus independent owner policy.

    Raise ValueError on any source alteration, unsupported assignment, double
    bank row, schema damage or unrecognized rule. Do not generate a payment OK.
    """
    counts = Counter()
    keys = set()
    with open(original_file, encoding="utf-8-sig", newline="") as a, open(
        reviewed_file, encoding="utf-8-sig", newline=""
    ) as b:
        original = csv.DictReader(a)
        reviewed = csv.DictReader(b)
        h = original.fieldnames
        r = reviewed.fieldnames
        if not h or len(h) != 32 or len(set(h)) != len(h):
            raise ValueError("Incorrect canonical 32-column screening schema")
        if not r or len(r) != 43 or len(set(r)) != len(r) or r[:32] != h:
            raise ValueError("Owner-review file changed original source headers")
        if not all(k in r for k in REQUIRED_POLICY):
            raise ValueError("Owner-review fields missing")
        for row_no, (left, right) in enumerate(zip_longest(original, reviewed), 2):
            if left is None or right is None:
                raise ValueError("Source/review row-count mismatch")
            if None in left or None in right:
                raise ValueError("Malformed CSV row width")
            if any(left[k] != right[k] for k in h):
                raise ValueError(f"Original bank row altered at CSV row {row_no}")
            bank_id = left["Bank Source Row (PAYMNENT)"]
            if not bank_id.isdigit() or bank_id in keys:
                raise ValueError(f"Duplicate/invalid original bank row {row_no}")
            keys.add(bank_id)
            category = left["Candidate Category (SCREEN ONLY)"]
            if category not in POLICY:
                raise ValueError(f"Unknown candidate class {row_no}")
            if right.get("Owner Review Business Rule ID") != POLICY[category]:
                raise ValueError(f"Wrong approved category/rule mapping {row_no}")
            for field, required in REQUIRED_POLICY.items():
                if right.get(field) != required:
                    raise ValueError(f"Unapproved transaction/finance state {row_no}: {field}")
            for field in ("Owner Approved Conditional Treatment",
                          "Required Evidence Before Per-Transaction OK"):
                if not right.get(field, "").strip():
                    raise ValueError(f"Missing transaction safeguards {row_no}: {field}")
            try:
                credit = Decimal(left["Bank Credit Column I (Original)"])
                if not credit.is_finite() or credit <= 0:
                    raise InvalidOperation
            except InvalidOperation:
                raise ValueError(f"Invalid positive bank credit {row_no}") from None
            counts[category] += 1
    if expected_counts is not None and dict(counts) != dict(expected_counts):
        raise ValueError("Changed candidate bucket counts")
    return {
        "owner_method_approval": "PASS_3_OF_3" if set(counts) == set(POLICY) else "INCOMPLETE",
        "rows_verified": len(keys),
        "source_fields_preserved": 32,
        "category_counts": dict(sorted(counts.items())),
        "original_source_sha256": _hash(original_file),
        "owner_review_sha256": _hash(reviewed_file),
        "individual_payment_allocations": 0,
        "financial_payment_parity": "NOT_VERIFIED",
        "production_release": "BLOCKED",
        "financial_database_writes": 0,
    }
