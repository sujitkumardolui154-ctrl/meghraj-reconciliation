#!/usr/bin/env bash
# Batch 10: Credit Note integrity and conflict review; read-only.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
umask 077
PYTHONPATH=backend_source python3 - <<'PY'
from __future__ import annotations
import csv
import hashlib
import json
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from credit_note_53_adapter import REPORT_HEADERS
from sbi_credit_firestore_all_v2 import is_credit

folder = Path("reports/credit_note")
manifests = sorted(folder.glob("SBI_CREDIT_NOTE_ALL_INVOICES_*.json"),key=lambda p:p.stat().st_mtime)
if not manifests:
    raise SystemExit("STOP: No real report manifest found")
manifest_path = manifests[-1]
csv_path = manifest_path.with_suffix(".csv")
if not csv_path.is_file():
    raise SystemExit("STOP: Matching CSV missing")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
fingerprint = hashlib.sha256(csv_path.read_bytes()).hexdigest()
if fingerprint != manifest.get("report_sha256"):
    raise SystemExit("STOP: CSV SHA-256 mismatches source manifest")
invoice_statuses = defaultdict(set)
invoice_rows = defaultdict(list)
credit_ids = set()
all_invoice_rows = 0
duplicate_counts = Counter()
with csv_path.open("r",encoding="utf-8-sig",newline="") as f:
    reader = csv.reader(f)
    headers = next(reader, [])
    if headers != list(REPORT_HEADERS):
        raise SystemExit("STOP: Report columns/order do not match approved 18-column schema")
    for rowno,row in enumerate(reader,start=2):
        if len(row) != 18:
            raise SystemExit(f"STOP: 18-column width mismatch at report row {rowno}")
        all_invoice_rows += 1
        invoice = row[8].strip()
        matched = is_credit(row[16])
        expected = "CREDIT NOTE" if matched else ""
        if row[17] != expected:
            raise SystemExit(f"STOP: Column U to R mismatch at report row {rowno}")
        if invoice:
            invoice_statuses[invoice].add(matched)
            duplicate_counts[invoice] += 1
            if matched:
                credit_ids.add(invoice)
            invoice_rows[invoice].append({
                "report_row": rowno,
                "source_column_u": row[16],
                "output_column_r": row[17],
            })
conflicts = sorted(i for i,states in invoice_statuses.items() if len(states)>1)
confirmed = credit_ids - set(conflicts)
checks = {
    "all_invoice_rows":all_invoice_rows,
    "unique_invoice_numbers":len(invoice_statuses),
    "credit_note_unique_invoices":len(credit_ids),
    "credit_note_confirmed_unique_invoices":len(confirmed),
    "conflicting_duplicate_invoice_numbers":len(conflicts),
    "duplicate_invoice_extra_rows":sum(n-1 for n in duplicate_counts.values()),
}
for key,value in checks.items():
    if manifest.get(key) is not None and manifest[key] != value:
        raise SystemExit(f"STOP: Manifest mismatch for {key} (manifest {manifest[key]}, computed {value})")
if all_invoice_rows != manifest.get("baseline_rows",0)+manifest.get("completed_import_rows",0):
    raise SystemExit("STOP: CSV total differs from manifest baseline + imports")
receipt_statuses = {}
receipt_sample_count = 0
receipt_check = "UNVERIFIED"
try:
    from google.cloud import firestore
    db = firestore.Client(project="meghraj-reconciliation", database="(default)")
    docs = list(db.collection("dashboard_import_receipts_v140").limit(100).get(timeout=45))
    receipt_sample_count = len(docs)
    for doc in docs:
        obj=doc.to_dict() or {}
        state=str(obj.get("status",obj.get("state",obj.get("import_status","UNKNOWN"))))
        receipt_statuses[state]=receipt_statuses.get(state,0)+1
    receipt_check = "SAMPLED_UP_TO_100_ONLY"
except Exception as exc:
    receipt_check = "UNVERIFIED_"+type(exc).__name__
review_path = folder / ("CREDIT_NOTE_CONFLICT_REVIEW_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".json")
review = {
    "report":csv_path.name,
    "report_sha256_verified":True,
    "generated_utc":datetime.now(timezone.utc).isoformat(),
    "computed_counts":checks,
    "import_receipt_status_check":receipt_check,
    "import_receipt_sample_size":receipt_sample_count,
    "import_receipt_status_counts":receipt_statuses,
    "release_status":"REVIEW_REQUIRED" if conflicts else "INTEGRATION_PENDING",
    "conflicts":[{"invoice_no":invoice,"rows":invoice_rows[invoice]} for invoice in conflicts],
    "decision":"No source values or payment statuses automatically changed",
}
with review_path.open("x",encoding="utf-8") as f:
    json.dump(review,f,indent=2,ensure_ascii=False)
review_path.chmod(0o600)
print("===== BATCH 10 PRIVATE AUDIT RESULT =====")
print("REPORT SHA256: PASS")
print("18-COLUMN STRUCTURE: PASS")
print("COLUMN U TO COLUMN R: PASS")
print("ALL INVOICE ROWS:",all_invoice_rows)
print("CREDIT NOTE OBSERVED UNIQUE:",len(credit_ids))
print("CREDIT NOTE UNAMBIGUOUS UNIQUE:",len(confirmed))
print("CONFLICTED INVOICE COUNT:",len(conflicts))
for inv in conflicts:
    print("CONFLICT INVOICE:",inv)
    for entry in invoice_rows[inv]:
        print("  REPORT ROW:",entry["report_row"],"SOURCE U:",repr(entry["source_column_u"]),"OUTPUT R:",repr(entry["output_column_r"]))
print("COMPLETED IMPORT ROWS RECORDED:",manifest.get("completed_import_rows"))
print("IMPORT RECEIPTS:",receipt_check,receipt_statuses)
print("REVIEW FILE:",review_path)
print("RELEASE STATUS:",review["release_status"])
print("FIRESTORE WRITES: NONE")
print("FINANCIAL EXECUTION: RESTRICTED")
print("BATCH 10 COMPLETE")
PY
