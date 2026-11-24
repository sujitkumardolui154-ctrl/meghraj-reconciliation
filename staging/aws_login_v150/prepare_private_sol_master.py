"""Private one-time adapter for the existing approved SBI SOL Branch Master XLSX.

Run ONLY on an authorized private host. No file contents/branch records go to
GitHub, Actions or stdout. Does not change the original workbook. Source
identity collisions are held; cannot auto-map an ambiguous SOL.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from openpyxl import load_workbook
import argparse
import json
import os
import re
import stat

SCHEMA="sbi-private-approved-sol-master/v1"
MANUAL_OWNER_REVIEW_SOL=frozenset(("3970","6884","6928","99922"))


def normalize_sol(value):
    if isinstance(value,bool) or value is None:return None
    if isinstance(value,int):return str(value) if value>0 else None
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}",value.strip()):
        return None
    return value.strip().lstrip("0") or None


def prepare(source):
    book=load_workbook(source,read_only=True,data_only=True,keep_links=False)
    try:
        sheet=book["Clean Branch Master"]
        headers=[cell.value for cell in next(sheet.iter_rows(min_row=1,max_row=1))]
        if headers.count("SOL ID")!=1 or headers.count("Official Branch Name")!=1:
            raise ValueError("APPROVED_SOL_SOURCE_HEADERS_INVALID")
        sol_index=headers.index("SOL ID")
        name_index=headers.index("Official Branch Name")
        names=defaultdict(set)
        for cells in sheet.iter_rows(min_row=2):
            key=normalize_sol(cells[sol_index].value)
            raw=cells[name_index].value
            if not key or type(raw) is not str or not raw.strip():
                continue
            name=raw.strip()
            if len(name)>180:
                raise ValueError("APPROVED_BRANCH_NAME_TOO_LONG")
            names[key].add(name)
        if not names or len(names)>5000:
            raise ValueError("APPROVED_SOL_MASTER_POPULATION_INVALID")
        branches=[]
        flagged=[]
        for sol,options in sorted(names.items(),key=lambda x:int(x[0])):
            safe=(len(options)==1 and sol not in MANUAL_OWNER_REVIEW_SOL)
            if not safe:flagged.append(sol)
            for name in sorted(options):
                branches.append({
                    "sol_id":sol,"official_branch_name":name,
                    "approved":safe,
                })
        return {
            "schema":SCHEMA,
            "branches":branches,
        },flagged
    finally:
        book.close()


def persist(source,dest):
    src=Path(source);out=Path(dest)
    if not src.is_file() or not src.name.lower().endswith(".xlsx"):
        raise ValueError("APPROVED_SOL_XLSX_REQUIRED")
    if not out.is_absolute() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError("PRIVATE_DESTINATION_REQUIRED")
    if out.exists():
        raise FileExistsError("DESTINATION_EXISTS_REFUSE_OVERWRITE")
    data,flagged=prepare(src)
    raw=(json.dumps(data,sort_keys=True,ensure_ascii=False,
                    separators=(",",":"))+"\n").encode()
    fd=os.open(str(out),os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    if stat.S_IMODE(out.stat().st_mode)!=0o600:
        raise ValueError("PRIVATE_OUTPUT_PERMISSIONS_INVALID")
    return {
        "sol_code_count":len(set(entry["sol_id"] for entry in data["branches"])),
        "source_name_entry_count":len(data["branches"]),
        "unambiguous_approved_code_count":len(set(
            row["sol_id"] for row in data["branches"] if row["approved"])),
        "review_sol_ids":flagged,
        "private_sha256":sha256(raw).hexdigest(),
        "private_file_bytes":len(raw),
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("approved_source_xlsx")
    p.add_argument("private_destination_json")
    args=p.parse_args()
    summary=persist(args.approved_source_xlsx,args.private_destination_json)
    print(json.dumps(summary,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
