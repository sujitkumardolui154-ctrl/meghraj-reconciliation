#!/usr/bin/env bash
# SBI Batch 8: targeted read-only Firestore pagination repair.
# Does not deploy Cloud Run, write Firestore, or change financial statuses.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import ast, os, shutil

path=Path("backend_source/sbi_credit_firestore_all_v2.py")
if not path.is_file():
    raise SystemExit("STOP: report generator missing")
source=path.read_text(encoding="utf-8")
marker="DIL_FIRESTORE_PAGINATION_V1"

old_d='''    documents = [
        (doc, doc.to_dict() or {})
        for doc in db.collection(
            "dashboard_report_datasets"
        ).stream()
    ]'''
new_d='''    documents = [
        (doc, doc.to_dict() or {})
        for doc in paged_snapshots(
            db.collection("dashboard_report_datasets")
        )
    ]'''
old_r='''    for snapshot in parent.reference.collection("rows").stream():'''
new_r='''    for snapshot in paged_snapshots(
        parent.reference.collection("rows")
    ):'''

helper='''# DIL_FIRESTORE_PAGINATION_V1
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


'''
if marker in source:
    print("PAGINATION PATCH: ALREADY INSTALLED", flush=True)
else:
    if source.count("def live():") != 1 or source.count(old_d) != 1 or source.count(old_r) != 1:
        raise SystemExit("STOP: unexpected source structure; no changes made")
    changed=(source.replace("def live():", helper+"def live():", 1)
            .replace(old_d,new_d,1).replace(old_r,new_r,1))
    ast.parse(changed, filename=str(path))
    folder=Path("backups/credit_note_repairs")
    folder.mkdir(parents=True, exist_ok=True)
    backup=folder/("before_batch8_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".py")
    shutil.copy2(path,backup)
    temp=path.with_suffix(".py.tmp")
    temp.write_text(changed,encoding="utf-8")
    os.replace(temp,path)
    print("PAGINATION PATCH: INSTALLED", flush=True)
    print("SOURCE BACKUP:",backup,flush=True)
PY
python3 -m py_compile backend_source/sbi_credit_firestore_all_v2.py
mkdir -p reports/credit_note
chmod 700 reports/credit_note
LOG="reports/credit_note/batch8_$(date -u +%Y%m%dT%H%M%SZ).log"
set +e
PYTHONPATH=backend_source timeout 300s python3 -u - >"$LOG" 2>&1 <<'PY'
import traceback
from sbi_credit_firestore_all_v2 import synthetic_test, live
synthetic_test()
try:
    live()
except Exception as exc:
    print("EXPORT BLOCKED:",type(exc).__name__, str(exc)[:250],flush=True)
    traceback.print_exc(limit=8)
    raise
PY
RC=$?
set -e
echo "===== BATCH 8 FINAL RESULT ====="
echo "EXIT CODE: $RC"
if [ "$RC" -eq 0 ]; then
    echo "REPORT GENERATION: SUCCESS"
elif [ "$RC" -eq 124 ]; then
    echo "REPORT GENERATION: TIMEOUT"
else
    echo "REPORT GENERATION: BLOCKED"
fi
tail -30 "$LOG"
echo "EXECUTION LOG: $LOG"
echo "DEFAULT FIRESTORE WRITES: NONE BY EXPORTER"
echo "FINANCIAL EXECUTION: RESTRICTED"
echo "BATCH 8 COMPLETE"
exit "$RC"
