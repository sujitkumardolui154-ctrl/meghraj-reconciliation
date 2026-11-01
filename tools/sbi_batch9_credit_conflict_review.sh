#!/usr/bin/env bash
# Batch 9: preserve all invoice rows; separate conflicted status review.
# Read-only Firestore export. No Cloud Run or financial write operations.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import ast, os, shutil

path = Path("backend_source/sbi_credit_firestore_all_v2.py")
if not path.is_file():
    raise SystemExit("STOP: CREDIT NOTE source module missing")
original = path.read_text(encoding="utf-8")
marker = "DIL_CREDIT_CONFLICT_REVIEW_V1"
if marker in original:
    print("CONFLICT REVIEW PATCH: ALREADY INSTALLED")
else:
    replacements = [
        (
            '''    credit_invoices = set()
    blank_invoice_rows = 0
''',
            '''    credit_invoices = set()
    # DIL_CREDIT_CONFLICT_REVIEW_V1
    row_positions = defaultdict(lambda: {"credit_note_rows": [], "other_rows": []})
    blank_invoice_rows = 0
''',
        ),
        (
            '''            statuses[invoice].add(matched)
            counts[invoice] += 1
''',
            '''            statuses[invoice].add(matched)
            counts[invoice] += 1
            row_positions[invoice][
                "credit_note_rows" if matched else "other_rows"
            ].append(len(output) + 1)
''',
        ),
        (
            '''    conflicts = sum(
        len(status_set) > 1
        for status_set in statuses.values()
    )

    if conflicts:
        raise ValueError(
            f"{conflicts} invoice numbers have conflicting "
            "CREDIT NOTE statuses"
        )
''',
            '''    conflicts = sorted(
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
''',
        ),
        (
            '''        "credit_note_unique_invoices": len(credit_invoices),
''',
            '''        "credit_note_unique_invoices": len(credit_invoices),
        "credit_note_observed_unique_invoices": len(credit_invoices),
        "credit_note_confirmed_unique_invoices": len(credit_invoices - conflicted),
        "credit_note_conflicting_unique_invoices": len(credit_invoices & conflicted),
        "conflicting_duplicate_invoice_numbers": len(conflicts),
        "conflicts_review": review,
        "release_status": "REVIEW_REQUIRED" if conflicts else "PASSED",
''',
        ),
        (
            '''    try:
        build([first, conflicting], headers)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Conflicting duplicate not rejected"
        )
''',
            '''    conflict_report, conflict_summary = build(
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
''',
        ),
        (
            '''    print("REAL READ-ONLY EXPORT: PASS")
''',
            '''    print("OBSERVED UNIQUE CREDIT NOTE COUNT:", summary["credit_note_unique_invoices"])
    print("CONFIRMED UNIQUE CREDIT NOTE COUNT:", summary["credit_note_confirmed_unique_invoices"])
    print("CONFLICTING INVOICE NUMBERS:", summary["conflicting_duplicate_invoice_numbers"])
    print("REPORT RELEASE STATUS:", summary["release_status"])
    if summary["release_status"] == "REVIEW_REQUIRED":
        print("REAL READ-ONLY EXPORT: GENERATED_FOR_REVIEW_ONLY")
    else:
        print("REAL READ-ONLY EXPORT: PASS")
''',
        ),
    ]
    modified = original
    for old, new in replacements:
        occurrences = modified.count(old)
        if occurrences != 1:
            raise SystemExit(
                f"STOP: Unexpected generator structure (target count={occurrences}); "
                "no changes made"
            )
        modified = modified.replace(old, new, 1)
    ast.parse(modified, filename=str(path))
    folder = Path("backups/credit_note_repairs")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = folder / ("before_batch9_conflict_review_" + stamp + ".py")
    shutil.copy2(path, backup)
    tmp = path.with_suffix(".py.tmp")
    tmp.write_text(modified, encoding="utf-8")
    os.replace(tmp, path)
    print("CONFLICT REVIEW PATCH: INSTALLED")
    print("ORIGINAL SOURCE BACKUP:", backup)
PY
python3 -m py_compile backend_source/sbi_credit_firestore_all_v2.py
PYTHONPATH=backend_source python3 backend_source/sbi_credit_firestore_all_v2.py --synthetic-only
mkdir -p reports/credit_note
chmod 700 reports/credit_note
LOG="reports/credit_note/batch9_$(date -u +%Y%m%dT%H%M%SZ).log"
set +e
PYTHONPATH=backend_source timeout 300s python3 -u backend_source/sbi_credit_firestore_all_v2.py >"$LOG" 2>&1
RC=$?
set -e
chmod 600 "$LOG"
echo "===== BATCH 9 FINAL RESULT ====="
echo "EXIT CODE: $RC"
if [ "$RC" -eq 0 ]; then echo "EXPORT EXECUTION: COMPLETED";
elif [ "$RC" -eq 124 ]; then echo "EXPORT EXECUTION: TIMEOUT";
else echo "EXPORT EXECUTION: BLOCKED"; fi
tail -25 "$LOG"
echo "LOG FILE: $LOG"
echo "DEFAULT FIRESTORE WRITES: NONE BY EXPORTER"
echo "FINANCIAL EXECUTION: RESTRICTED"
echo "BATCH 9 COMPLETE"
exit "$RC"
