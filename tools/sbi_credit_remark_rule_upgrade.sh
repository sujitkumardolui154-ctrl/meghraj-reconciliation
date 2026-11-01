#!/usr/bin/env bash
# CREDIT NOTE owner rule v2: Column U may contain CREDIT NOTE / CREDIT NORTE
# followed by a date, reference, punctuation, or further remarks.
# Local code patch + read-only export + private audit; no Firestore writes.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
umask 077
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import ast, os, shutil
p=Path("backend_source/sbi_credit_firestore_all_v2.py")
if not p.is_file():
    raise SystemExit("STOP: Current CREDIT NOTE generator not found")
source=p.read_text(encoding="utf-8")
marker="DIL_CREDIT_REMARK_MATCH_V2"
old='''def is_credit(value):
    return " ".join(str(value or "").upper().split()) == "CREDIT NOTE"
'''
new='''def is_credit(value):
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
'''
if marker in source:
    print("REMARK MATCH PATCH: ALREADY INSTALLED")
else:
    if source.count(old)!=1:
        raise SystemExit("STOP: Unexpected original matching function; no modification")
    updated=source.replace(old,new,1)
    ast.parse(updated,filename=str(p))
    bdir=Path("backups/credit_note_repairs")
    bdir.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=bdir/("before_credit_remark_rule_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".py")
    shutil.copy2(p,backup)
    tmp=p.with_suffix(".py.tmp")
    tmp.write_text(updated,encoding="utf-8")
    os.replace(tmp,p)
    print("REMARK MATCH PATCH: INSTALLED")
    print("SOURCE BACKUP:",backup)
PY
python3 -m py_compile backend_source/sbi_credit_firestore_all_v2.py
PYTHONPATH=backend_source python3 - <<'PY'
from sbi_credit_firestore_all_v2 import is_credit, synthetic_test, build
positive=[
  "CREDIT NOTE",
  "credit note @ 30/11/2024",
  "CREDIT NORTE @ 30/11/2024",
  "credit note against invoice reference",
  "SBI: CREDIT NOTE REF123",
  " CREDIT-NORTE / adjustment 2026",
  "CREDIT NOTE123"
]
negative=["PAID","PARTIAL PAYMENT","CREDIT NOTEBOOK","NOTED","CREDIT NOTED","CREDIT NORTHERN"]
for text in positive:
    assert is_credit(text),("Missing expected match",text)
for text in negative:
    assert not is_credit(text),("Unsafe match",text)
synthetic_test()
headers=[f"field{i}" for i in range(17)]+["Credi note"]
data=[[""]*53 for _ in range(3)]
data[0][12]="MXPTEST001";data[0][20]="CREDIT NOTE @ 30/11/2024"
data[1][12]="MXPTEST002";data[1][20]="Credit Norte - adjustment"
data[2][12]="MXPTEST003";data[2][20]="PAID"
initial=[row.copy() for row in data]
rows,meta=build(data,headers)
assert rows[1][17]=="CREDIT NOTE" and rows[2][17]=="CREDIT NOTE" and rows[3][17]==""
assert meta["credit_note_unique_invoices"]==2
assert data==initial
print("APPROVED REMARK MATCHING: PASS")
print("CREDIT NOTE @ 30/11/2024: PASS")
print("CREDIT NORTE @ 30/11/2024: PASS")
print("NON-MATCHING ROWS BLANK: PASS")
print("ORIGINAL SOURCE PRESERVED: PASS")
PY
LOG="reports/credit_note/remark_rule_$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p reports/credit_note
chmod 700 reports/credit_note
set +e
PYTHONPATH=backend_source timeout 300s python3 -u backend_source/sbi_credit_firestore_all_v2.py >"$LOG" 2>&1
RC=$?
set -e
chmod 600 "$LOG"
echo "===== UPDATED CREDIT NOTE EXPORT ====="
echo "EXIT CODE: $RC"
tail -22 "$LOG"
if [ "$RC" -ne 0 ]; then
  echo "EXPORT: BLOCKED; ORIGINAL DATA UNCHANGED"
  echo "LOG FILE: $LOG"
  echo "FINANCIAL EXECUTION: RESTRICTED"
  exit "$RC"
fi
echo "EXPORT: GENERATED; AWAIT CONFLICT REVIEW"
echo "===== PRIVATE REPORT REVIEW ====="
AUDIT="$(mktemp)"
trap 'rm -f "$AUDIT"' EXIT
curl -fsSL "https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/61274db6adb99f510be2f39a1e3c7021c60f8773/tools/sbi_batch10_credit_private_audit.sh" -o "$AUDIT"
bash "$AUDIT"
echo "REMARK RULE UPGRADE COMPLETE"
