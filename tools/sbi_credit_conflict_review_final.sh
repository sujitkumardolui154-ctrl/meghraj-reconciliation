#!/usr/bin/env bash
# Read-only five-conflict review of the approved all-invoice CREDIT NOTE report.
# No Firestore write, deployment, status overwrite or auto-resolution.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
umask 077
PYTHONPATH=backend_source python3 - <<'PY'
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from credit_note_53_adapter import REPORT_HEADERS

root=Path("reports/credit_note")
manifests=sorted(root.glob("SBI_CREDIT_NOTE_ALL_INVOICES_*.json"),key=lambda p:p.stat().st_mtime)
if not manifests:
    raise SystemExit("STOP: CREDIT NOTE export manifest missing")
manifest_path=manifests[-1]
manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
report=manifest_path.with_suffix(".csv")
if not report.is_file():
    raise SystemExit("STOP: matching CREDIT NOTE report CSV missing")
sha=hashlib.sha256(report.read_bytes()).hexdigest()
if sha!=manifest.get("report_sha256"):
    raise SystemExit("STOP: export CSV checksum mismatch")

conflicts=manifest.get("conflicts_review",[])
if not isinstance(conflicts,list):
    raise SystemExit("STOP: malformed conflict-review record")
ids=[x.get("invoice_no","") for x in conflicts if isinstance(x,dict)]
if len(ids)!=len(conflicts) or len(ids)!=len(set(ids)) or not all(ids):
    raise SystemExit("STOP: conflicting invoice identifiers invalid")
if len(ids)!=manifest.get("conflicting_duplicate_invoice_numbers"):
    raise SystemExit("STOP: conflict count does not match export")
matched=set(ids)
records=defaultdict(list)
counts=0
with report.open("r",encoding="utf-8-sig",newline="") as f:
    reader=csv.reader(f)
    headers=next(reader,[])
    if headers!=list(REPORT_HEADERS):
        raise SystemExit("STOP: report headers not approved 18-column order")
    for report_row,row in enumerate(reader,start=2):
        if len(row)!=18:
            raise SystemExit(f"STOP: wrong source row width at {report_row}")
        counts+=1
        invoice=row[8].strip()
        if invoice in matched:
            records[invoice].append((report_row,row))
if counts!=manifest.get("all_invoice_rows"):
    raise SystemExit("STOP: invoice row count mismatch")
outrows=[]
for conflict in conflicts:
    invoice=conflict["invoice_no"]
    actual=records.get(invoice,[])
    yes=sorted(rowno for rowno,row in actual if row[17]=="CREDIT NOTE")
    no=sorted(rowno for rowno,row in actual if row[17]!="CREDIT NOTE")
    if yes!=sorted(conflict.get("credit_note_report_rows",[])) or no!=sorted(conflict.get("non_credit_note_report_rows",[])):
        raise SystemExit("STOP: conflict rows differ from export manifest")
    for report_row,row in actual:
        outrows.append([
            invoice,report_row,row[0],row[5],row[6],row[8],
            row[16],row[17],
            "CREDIT_NOTE" if row[17]=="CREDIT NOTE" else "OTHER_STATUS",
            "SOURCE_REVIEW_REQUIRED",
        ])
output=root/("CREDIT_NOTE_CONFLICT_REVIEW_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".csv")
with output.open("x",encoding="utf-8-sig",newline="") as f:
    writer=csv.writer(f)
    writer.writerow(["Invoice No","Report Row","FY","Branch Code","Client Name","Invoice No (Original)","Original Column U","Output Column R","Classification","Review Decision"])
    writer.writerows(outrows)
output.chmod(0o600)
print("===== CREDIT NOTE CONFLICT REVIEW =====")
print("FULL INVOICE ROWS VERIFIED:",counts)
print("REVISED CREDIT NOTE OBSERVED:",manifest.get("credit_note_unique_invoices"))
print("UNAMBIGUOUS CREDIT NOTE:",manifest.get("credit_note_confirmed_unique_invoices"))
print("CONFLICTING INVOICES:",len(ids))
print("CONFLICT REVIEW CSV:",output)
print("REPORT CHECKSUM: PASS")
print("DEFAULT DATABASE WRITES: NONE")
print("RELEASE DECISION: REVIEW_REQUIRED" if ids else "RELEASE DECISION: ADDITIONAL INTEGRATION REQUIRED")
print("FINANCIAL EXECUTION: RESTRICTED")
print("PRIVATE REVIEW FILE COMPLETE")
PY
