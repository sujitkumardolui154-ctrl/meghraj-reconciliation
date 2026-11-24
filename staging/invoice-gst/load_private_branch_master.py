"""QA-only isolated SBI Clean Branch Master importer.

Repo contains approved v2.7 matcher/alias code; the complete customer master
and address evidence must be supplied separately at the PRIVATE runtime.
No production writes and no attempt to guess missing branch identity.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re

from private_master_adapter import prepare_private_master_rows


def verified_private_inputs(master_csv, additional_evidence_json, *, master_sha, evidence_sha):
    blob = Path(master_csv).read_bytes()
    evidence_blob = Path(additional_evidence_json).read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if (not re.fullmatch(r"[a-f0-9]{64}", master_sha or "") or
        not re.fullmatch(r"[a-f0-9]{64}", evidence_sha or "")):
        raise ValueError("PRIVATE_MASTER_HASHES_REQUIRED")
    if digest(blob) != master_sha or digest(evidence_blob) != evidence_sha:
        raise ValueError("PRIVATE_MASTER_EVIDENCE_DIGEST_MISMATCH")
    from io import StringIO
    reader = csv.DictReader(StringIO(blob.decode("utf-8-sig")))
    if not reader.fieldnames or not {
        "Official Branch Name","SOL ID","Search Aliases"
    }.issubset(reader.fieldnames):
        raise ValueError("APPROVED_MASTER_HEADERS_MISSING")
    master = list(reader)
    evidence = json.loads(evidence_blob)
    if not isinstance(evidence, list):
        raise ValueError("PRIVATE_APPROVAL_EVIDENCE_REQUIRED")
    extras = {}
    for row in evidence:
        if not isinstance(row, dict):
            raise ValueError("INVALID_EVIDENCE_ROW")
        name = row.get("official_name")
        sol = row.get("sol_id")
        if not isinstance(name, str) or not isinstance(sol, str):
            raise ValueError("INVALID_EVIDENCE_IDENTITY")
        key = (re.sub(r"[^A-Z0-9]+"," ",name.upper()).strip(),sol.zfill(5))
        if key in extras:
            raise ValueError("DUPLICATE_EVIDENCE_IDENTITY")
        extras[key] = row
    result = prepare_private_master_rows(master,extras)
    errors = [item for item in result if item["status"] != "READY_FOR_PRIVATE_QA_IMPORT"]
    if not master or errors:
        return {"status":"REVIEW_REQUIRED","total":len(master),
                "ready":len(result)-len(errors),"review":errors,
                "rows":[]}
    branch_keys = [x["branch"]["branch_key"] for x in result]
    if len(set(branch_keys)) != len(branch_keys):
        raise ValueError("DUPLICATE_PRIVATE_BRANCH_KEYS")
    return {"status":"READY_FOR_PRIVATE_QA_IMPORT","total":len(master),
            "ready":len(result),"review":[],"rows":[x["branch"] for x in result]}


def stage_approved_master_qa(dsn, validated):
    if validated.get("status") != "READY_FOR_PRIVATE_QA_IMPORT":
        raise ValueError("REVIEW_REQUIRED_NO_DATABASE_WRITE")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn,row_factory=dict_row,connect_timeout=6) as conn:
        name = conn.execute("SELECT current_database() AS db").fetchone()["db"]
        if name != "invoice_qa":
            raise ValueError("REFUSE_NON_ISOLATED_QA_DATABASE")
        for row in validated["rows"]:
            # Existing branch records must never be silently overwritten.
            existing = conn.execute(
                """SELECT branch_key,sol_id,client_name,gstin
                   FROM sbi_invoice_gst.verified_branches WHERE branch_key=%s""",
                (row["branch_key"],),
            ).fetchone()
            if existing:
                if (existing["sol_id"],existing["client_name"],existing["gstin"]) != (
                    row["sol_id"],row["client_name"],row["gstin"]
                ):
                    raise ValueError("PREEXISTING_BRANCH_MASTER_CONFLICT")
                continue
            conn.execute(
                """INSERT INTO sbi_invoice_gst.verified_branches
                   (branch_key,client_name,invoice_branch,
                    invoice_generate_location,original_branch_name,
                    sol_id,client_class,gstin,recipient_title,customer_address,
                    state_code,verified,verified_by,verified_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'19',TRUE,%s,now())""",
                (row["branch_key"],row["client_name"],row["invoice_branch"],
                 row["invoice_generate_location"],row["original_branch_name"],
                 row["sol_id"],row["client_class"],row["gstin"],
                 row["recipient_title"],row["customer_address"],
                 row["verified_by"]),
            )
    return {"status":"APPROVED_PRIVATE_MASTER_LOADED_IN_ISOLATED_QA",
            "ready":validated["ready"],"production_write":False}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--master-csv",required=True)
    p.add_argument("--evidence-json",required=True)
    p.add_argument("--master-sha256",required=True)
    p.add_argument("--evidence-sha256",required=True)
    p.add_argument("--apply-to-isolated-qa",action="store_true")
    args=p.parse_args()
    result=verified_private_inputs(
        args.master_csv,args.evidence_json,
        master_sha=args.master_sha256,evidence_sha=args.evidence_sha256
    )
    print("MASTER_REVIEW_STATUS=",result["status"])
    print("TOTAL=",result["total"],"READY=",result["ready"],
          "REVIEW=",len(result["review"]))
    if args.apply_to_isolated_qa:
        dsn=os.environ.get("SBI_INVOICE_GST_TEST_DSN")
        if not dsn:
            raise SystemExit("QA_DSN_REQUIRED")
        print(stage_approved_master_qa(dsn,result)["status"])
