#!/usr/bin/env python3
"""Private reporting evidence preflight. No network, cloud, Docker, or database writes.

Required private input files are passed explicitly. Missing independent evidence
always yields REVIEW_REQUIRED, never approval. Prints no invoice IDs or source rows.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_MANIFEST_COUNTS = (
    "all_invoice_rows",
    "credit_note_unique_invoices",
    "credit_note_confirmed_unique_invoices",
    "conflicting_duplicate_invoice_numbers",
)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def verify(*, report=None, manifest=None, headers=None, contract=None,
           conflict_review=None, runtime_attestation=None):
    checks = {}
    blockers = []

    def mark(name, ok, reason):
        checks[name] = "PASS" if ok else "PENDING"
        if not ok:
            blockers.append(reason)

    independent_headers = False
    try:
        if not headers or not contract:
            raise ValueError()
        raw_headers = json.loads(Path(headers).read_text(encoding="utf-8"))
        expected = json.loads(Path(contract).read_text(encoding="utf-8"))["headers"]
        independent_headers = (
            isinstance(raw_headers, list) and len(raw_headers) == 53
            and all(isinstance(x, str) for x in raw_headers)
            and raw_headers == expected
        )
    except (OSError, ValueError, TypeError, KeyError):
        pass
    mark("INDEPENDENT_53_HEADERS", independent_headers,
         "ORIGINAL_APPROVED_53_HEADERS_NOT_VERIFIED")

    report_verified = False
    conflicts_count = None
    try:
        if not report or not manifest:
            raise ValueError()
        raw = Path(report).read_bytes()
        meta = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or not SHA.fullmatch(str(meta.get("report_sha256", ""))):
            raise ValueError()
        if sha256(raw) != meta["report_sha256"]:
            raise ValueError()
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        header = next(rows)
        if len(header) != 18 or header[8] != "Invoice No" or header[17] != "Credi note":
            raise ValueError()
        if not header[16].lower().startswith("payment received"):
            raise ValueError()
        counts = defaultdict(set)
        all_rows = 0
        for row in rows:
            if len(row) != 18 or row[17] not in ("", "CREDIT NOTE"):
                raise ValueError()
            all_rows += 1
            if row[8].strip():
                counts[row[8].strip()].add(row[17] == "CREDIT NOTE")
        marked = {k for k, states in counts.items() if True in states}
        contradictory = {k for k, states in counts.items() if len(states) > 1}
        observed = {
            "all_invoice_rows": all_rows,
            "credit_note_unique_invoices": len(marked),
            "credit_note_confirmed_unique_invoices": len(marked - contradictory),
            "conflicting_duplicate_invoice_numbers": len(contradictory),
        }
        if any(type(meta.get(k)) is not int or meta[k] != observed[k]
               for k in REQUIRED_MANIFEST_COUNTS):
            raise ValueError()
        if meta.get("release_status") != "REVIEW_REQUIRED":
            raise ValueError()
        report_verified = True
        conflicts_count = len(contradictory)
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, StopIteration):
        pass
    mark("PRIVATE_REPORT_HASH_STRUCTURE_COUNTS", report_verified,
         "PRIVATE_REPORT_MANIFEST_CSV_NOT_VERIFIED")

    # A resolution requires an independent signed decision, not merely a review CSV.
    reviewed = False
    try:
        if not conflict_review:
            raise ValueError()
        review = json.loads(Path(conflict_review).read_text(encoding="utf-8"))
        reviewed = (report_verified and isinstance(review, dict)
                    and review.get("decision") == "APPROVED_FOR_REPORTING_ONLY"
                    and review.get("report_sha256") == sha256(Path(report).read_bytes())
                    and isinstance(review.get("reviewer"), str)
                    and bool(review["reviewer"].strip())
                    and review.get("reviewed_conflicts") == conflicts_count
                    and review.get("unresolved_conflicts") == 0)
    except (OSError, ValueError, TypeError):
        pass
    mark("INDEPENDENT_CONFLICT_ADJUDICATION", reviewed,
         "INDEPENDENT_CONFLICT_DECISION_PENDING")

    # Runtime, IAM, real HTTP and rollback require separately captured, source-bound
    # evidence. This file is an informational inventory; no self-attestation pass.
    mark("PRIVATE_IAM_REAL_HTTP_ROLLBACK", False,
         "LIVE_IAM_HTTP_ROLLBACK_NOT_INDEPENDENTLY_ATTESTED")
    mark("FIRESTORE_SOURCE_RECEIPT_AUDIT", False,
         "READ_ONLY_LIVE_FIRESTORE_R2_NOT_ATTESTED")

    return {
        "result": "REVIEW_REQUIRED",
        "release_approved": False,
        "deployment_authorized": False,
        "financial_execution": "RESTRICTED",
        "checks": checks,
        "blockers": blockers,
        "observed_conflict_groups": conflicts_count,
        "private_data_disclosed": False,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report")
    p.add_argument("--manifest")
    p.add_argument("--approved-headers")
    p.add_argument("--contract", default="backend_source/invoice_import_contract.json")
    p.add_argument("--conflict-decision")
    p.add_argument("--output", help="Private local destination, not GitHub")
    a = p.parse_args()
    result = verify(report=a.report, manifest=a.manifest, headers=a.approved_headers,
                    contract=a.contract, conflict_review=a.conflict_decision)
    if a.output:
        path = Path(a.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        import os
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
