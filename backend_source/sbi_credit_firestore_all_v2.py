"""Read-only CREDIT NOTE export from verified 53-column Firestore rows."""

import csv
import hashlib
import inspect
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

IDX = (1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)


def is_credit(value):
    """Match CREDIT NOTE or CREDIT NORTE phrases anywhere in original column U.

    Accept additional dates/references/remarks, but avoid NOTEBOOK/NOTED.
    Do not inspect or alter any other financial field.
    """
    # DIL_CREDIT_REMARK_MATCH_V2
    text = str(value or "").upper()
    return re.search(
        r"(?<![A-Z0-9])CREDIT[\s._/:-]+NOR?TE(?![A-Z])",
        text,
    ) is not None


def decode(record):
    if not isinstance(record, dict) or not isinstance(
        record.get("original_values"), list
    ):
        raise ValueError("Lossless original_values unavailable")

    values = record["original_values"]

    if len(values) != 53:
        raise ValueError("Source row is not 53 columns")

    types = record.get("original_cell_types")

    if types is not None and (
        not isinstance(types, list) or len(types) != 53
    ):
        raise ValueError("Original cell type count mismatch")

    if any(
        value is not None
        and not isinstance(value, (str, int, float, bool))
        for value in values
    ):
        raise ValueError("Unsupported source cell type")

    return ["" if value is None else str(value) for value in values]


def build(rows, headers):
    output = [list(headers)]
    statuses = defaultdict(set)
    counts = Counter()
    credit_invoices = set()
    # DIL_CREDIT_CONFLICT_REVIEW_V1
    row_positions = defaultdict(lambda: {"credit_note_rows": [], "other_rows": []})
    blank_invoice_rows = 0

    for original in rows:
        invoice = original[12].strip()
        matched = is_credit(original[20])

        if invoice:
            statuses[invoice].add(matched)
            counts[invoice] += 1
            row_positions[invoice][
                "credit_note_rows" if matched else "other_rows"
            ].append(len(output) + 1)
            if matched:
                credit_invoices.add(invoice)
        else:
            blank_invoice_rows += 1

        values = [original[index] for index in IDX]

        for value in values:
            text = value.lstrip()

            if (
                text.startswith(("=", "+", "@", "\t", "\r", "\n"))
                or (
                    text.startswith("-")
                    and len(text) > 1
                    and not re.fullmatch(
                        r"-\d+(?:\.\d+)?", text
                    )
                )
            ):
                raise ValueError(
                    "Potential CSV formula value; export blocked"
                )

        output.append(
            values + ["CREDIT NOTE" if matched else ""]
        )

    conflicts = sorted(
        invoice for invoice, status_set in statuses.items()
        if len(status_set) > 1
    )
    conflicted = set(conflicts)
    # Conflicting invoice IDs are recorded ONLY in the private manifest.
    review = [
        {"invoice_no": invoice,
         "credit_note_report_rows": row_positions[invoice]["credit_note_rows"],
         "non_credit_note_report_rows": row_positions[invoice]["other_rows"]}
        for invoice in conflicts
    ]

    summary = {
        "all_invoice_rows": len(rows),
        "unique_invoice_numbers": len(statuses),
        "credit_note_unique_invoices": len(credit_invoices),
        "credit_note_observed_unique_invoices": len(credit_invoices),
        "credit_note_confirmed_unique_invoices": len(credit_invoices - conflicted),
        "credit_note_conflicting_unique_invoices": len(credit_invoices & conflicted),
        "conflicting_duplicate_invoice_numbers": len(conflicts),
        "conflicts_review": review,
        "release_status": "REVIEW_REQUIRED" if conflicts else "PASSED",
        "blank_invoice_number_rows": blank_invoice_rows,
        "duplicate_invoice_extra_rows": sum(
            count - 1
            for count in counts.values()
            if count > 1
        ),
    }

    return output, summary


# DIL_FIRESTORE_PAGINATION_V1
def paged_snapshots(collection, page_size=125):
    """Read Firestore documents in bounded pages; never writes."""
    from google.api_core.retry import Retry
    query = collection.order_by("__name__")
    cursor = None
    pages = 0
    while True:
        current = query.limit(page_size)
        if cursor is not None:
            current = current.start_after(cursor)
        documents = list(current.get(
            retry=Retry(initial=0.5, maximum=5, multiplier=2, timeout=60),
            timeout=45,
        ))
        if not documents:
            return
        yield from documents
        pages += 1
        if pages % 10 == 0:
            print("FIRESTORE PAGES READ:", pages, flush=True)
        if len(documents) < page_size:
            return
        cursor = documents[-1]


def live():
    from google.cloud import firestore
    from invoice_source_schema import HEADERS_53
    from credit_note_53_adapter import REPORT_HEADERS
    from report_api import completed_import_rows

    db = firestore.Client(
        project="meghraj-reconciliation",
        database="(default)"
    )

    documents = [
        (doc, doc.to_dict() or {})
        for doc in paged_snapshots(
            db.collection("dashboard_report_datasets")
        )
    ]

    candidates = [
        (doc, metadata)
        for doc, metadata in documents
        if metadata.get("original_headers") == list(HEADERS_53)
        and metadata.get("original_column_count") == 53
    ]

    selected = os.environ.get("SBI_DATASET_ID", "")

    if selected:
        candidates = [
            item for item in candidates
            if item[0].id == selected
        ]

    if len(candidates) != 1:
        print(
            "VALID DATASET IDS:",
            [doc.id for doc, _ in candidates][:10]
        )
        raise ValueError(
            "Dataset selection is not unique or unavailable"
        )

    parent, metadata = candidates[0]

    if (
        len(HEADERS_53) != 53
        or len(REPORT_HEADERS) != 18
        or HEADERS_53[20]
        != "Payment Received ( If With GST or Excluding GST)"
    ):
        raise ValueError("Approved report schema changed")

    if (
        list(HEADERS_53[6:8])
        != ["Branch Code", "Client Name"]
        or HEADERS_53[12] != "Invoice No"
    ):
        raise ValueError("G/H/M source mapping changed")

    expected = metadata.get("rows")
    source_sha = metadata.get("source_sha256")

    if (
        type(expected) is not int
        or not 1 <= expected <= 25000
        or not isinstance(source_sha, str)
        or not source_sha
    ):
        raise ValueError("Dataset count or source fingerprint invalid")

    if metadata.get(
        "original_columns_row_count"
    ) not in (None, expected):
        raise ValueError("Baseline row counts inconsistent")

    if len(
        inspect.signature(completed_import_rows).parameters
    ) != 1:
        raise ValueError("Completed import interface changed")

    imports = completed_import_rows(db)

    if not isinstance(imports, list):
        raise ValueError("Completed import response invalid")

    import_hash = hashlib.sha256(
        json.dumps(
            imports, sort_keys=True, default=str
        ).encode()
    ).hexdigest()

    baseline = []
    source_row_ids = set()

    for snapshot in paged_snapshots(
        parent.reference.collection("rows")
    ):
        record = snapshot.to_dict() or {}

        if record.get(
            "original_columns_source_sha256"
        ) not in (None, "", source_sha):
            raise ValueError("Source SHA mismatch")

        row_number = record.get("source_row")

        if (
            type(row_number) is not int
            or row_number in source_row_ids
        ):
            raise ValueError("Duplicate or missing source row number")

        source_row_ids.add(row_number)
        baseline.append((row_number, decode(record)))

        if len(baseline) > 25000:
            raise ValueError("Row safety limit exceeded")

    if len(baseline) != expected:
        raise ValueError(
            f"Incomplete baseline: expected {expected}, "
            f"received {len(baseline)}"
        )

    baseline.sort(key=lambda item: item[0])

    rows = [record for _, record in baseline]

    for imported in imports:
        rows.append(decode(imported))

    if len(rows) > 25000:
        raise ValueError("Total row limit exceeded")

    current = parent.reference.get().to_dict() or {}

    for key in (
        "rows",
        "original_headers",
        "original_columns_row_count",
        "source_sha256",
    ):
        if current.get(key) != metadata.get(key):
            raise ValueError("Baseline changed during export")

    imports_after = completed_import_rows(db)

    second_hash = hashlib.sha256(
        json.dumps(
            imports_after, sort_keys=True, default=str
        ).encode()
    ).hexdigest()

    if second_hash != import_hash:
        raise ValueError("Completed imports changed during export")

    report, summary = build(rows, REPORT_HEADERS)

    folder = Path("reports/credit_note")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    csv_path = folder / (
        f"SBI_CREDIT_NOTE_ALL_INVOICES_{stamp}.csv"
    )

    with csv_path.open(
        "x", newline="", encoding="utf-8-sig"
    ) as file:
        csv.writer(file).writerows(report)

    csv_path.chmod(0o600)

    summary.update({
        "baseline_rows": expected,
        "completed_import_rows": len(imports),
        "dataset_id": parent.id,
        "source_sha256": source_sha,
        "report_sha256": hashlib.sha256(
            csv_path.read_bytes()
        ).hexdigest(),
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "financial_execution": "RESTRICTED",
        "firestore_writes": 0,
        "full_schema_columns": 53,
        "report_columns": 18,
    })

    manifest = csv_path.with_suffix(".json")

    with manifest.open(
        "x", encoding="utf-8"
    ) as file:
        json.dump(summary, file, indent=2)

    manifest.chmod(0o600)

    print("VERIFIED BASELINE ROWS:", expected)
    print("COMPLETED IMPORT ROWS:", len(imports))
    print("REPORT ROWS:", summary["all_invoice_rows"])
    print(
        "UNIQUE CREDIT NOTE COUNT:",
        summary["credit_note_unique_invoices"]
    )
    print("REPORT:", csv_path)
    print("MANIFEST:", manifest)
    print("OBSERVED UNIQUE CREDIT NOTE COUNT:", summary["credit_note_unique_invoices"])
    print("CONFIRMED UNIQUE CREDIT NOTE COUNT:", summary["credit_note_confirmed_unique_invoices"])
    print("CONFLICTING INVOICE NUMBERS:", summary["conflicting_duplicate_invoice_numbers"])
    print("REPORT RELEASE STATUS:", summary["release_status"])
    if summary["release_status"] == "REVIEW_REQUIRED":
        print("REAL READ-ONLY EXPORT: GENERATED_FOR_REVIEW_ONLY")
    else:
        print("REAL READ-ONLY EXPORT: PASS")


def synthetic_test():
    first = [""] * 53
    first[6] = "0016642"
    first[7] = "TEST CLIENT"
    first[12] = "MXPTEST001"
    first[20] = " credit note "

    second = first.copy()
    second[12] = "MXPTEST002"
    second[20] = "PAID"

    headers = [
        f"field{i}" for i in range(17)
    ] + ["Credi note"]

    report, summary = build(
        [first, second], headers
    )

    assert len(report[1]) == 18
    assert report[1][17] == "CREDIT NOTE"
    assert report[2][17] == ""
    assert report[1][5] == "0016642"
    assert summary["credit_note_unique_invoices"] == 1

    conflicting = first.copy()
    conflicting[20] = "PAID"

    conflict_report, conflict_summary = build(
        [first, conflicting], headers
    )
    assert len(conflict_report) == 3
    assert conflict_report[1][17] == "CREDIT NOTE"
    assert conflict_report[2][17] == ""
    assert conflict_summary["conflicting_duplicate_invoice_numbers"] == 1
    assert conflict_summary["credit_note_unique_invoices"] == 1
    assert conflict_summary["credit_note_confirmed_unique_invoices"] == 0
    assert conflict_summary["release_status"] == "REVIEW_REQUIRED"
    assert conflict_summary["conflicts_review"][0]["credit_note_report_rows"] == [2]
    assert conflict_summary["conflicts_review"][0]["non_credit_note_report_rows"] == [3]

    print("SYNTHETIC 53-TO-18 REPORT: PASS")
    print("DUPLICATE CONFLICT VALIDATION: PASS")


if __name__ == "__main__":
    os.umask(0o077)

    try:
        synthetic_test()

        if "--synthetic-only" not in sys.argv:
            live()

    except Exception as exc:
        print(
            "EXPORT BLOCKED:",
            type(exc).__name__,
            str(exc)[:500]
        )
        print("ORIGINAL FIRESTORE WRITES: NONE")
        sys.exit(2)
