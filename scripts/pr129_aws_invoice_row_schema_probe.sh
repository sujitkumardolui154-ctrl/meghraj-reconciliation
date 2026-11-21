#!/usr/bin/env bash
# PR129: One-row schema preflight using existing AWS Firestore credentials.
# Reads 1 verified baseline invoice row plus one imported-row sample at most.
# Never prints an invoice number, customer name, financial value, document ID,
# bearer token, key, record data or any response body.
# No IAM changes, no Cloud Run deployment, no Firestore writes.
set -Eeuo pipefail
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
[ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ] || { echo 'STOP: PREVIEW_NOT_RUNNING'; exit 1; }
[ "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" ] || { echo 'STOP: WRONG_PREVIEW_NETWORK'; exit 1; }
echo '=== PR129 AWS INVOICE ROW SHAPE AND SCOPED ACCESS ==='
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from firebase_admin import auth
from dashboard_sessions import MASTER_UID, MASTER_EMAIL, firebase_app, is_master
from sbi_report_access import can_view_report
from google.auth.transport.requests import AuthorizedSession
import google.auth
from invoice_source_schema import HEADERS_53
import json

user=auth.get_user(MASTER_UID,app=firebase_app())
assert user.uid == MASTER_UID
assert (user.email or "").casefold() == MASTER_EMAIL.casefold()
assert is_master(user) and can_view_report(user, {"uid":user.uid})
print("MASTER_REPORT_VIEWER=VERIFIED")

project="meghraj-reconciliation"
sha="433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"
dataset=sha+"-report-v1"
base="https://firestore.googleapis.com/v1/projects/"+project+"/databases/(default)/documents"
creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
session=AuthorizedSession(creds)
def parse_value(v):
    if not isinstance(v,dict):return None
    if "stringValue" in v:return v["stringValue"]
    if "integerValue" in v:return int(v["integerValue"])
    if "booleanValue" in v:return v["booleanValue"]
    if "arrayValue" in v:return [parse_value(i) for i in v["arrayValue"].get("values",[])]
    return None

def sample(parent,collection):
    query={"structuredQuery":{"from":[{"collectionId":collection}],"limit":1}}
    r=session.post(base+parent+":runQuery",json=query,timeout=(5,35),
                   allow_redirects=False)
    print("QUERY_"+collection.upper()+"_HTTP="+str(r.status_code))
    if r.status_code != 200:raise RuntimeError("FIRESTORE_SCOPED_READ_DENIED")
    records=r.json()
    if not isinstance(records,list):raise RuntimeError("INVALID_FIRESTORE_QUERY_RESPONSE")
    docs=[x["document"] for x in records if isinstance(x,dict) and "document" in x]
    if len(docs)>1:raise RuntimeError("UNEXPECTED_SAMPLE_COUNT")
    return {k:parse_value(v) for k,v in docs[0].get("fields",{}).items()} if docs else None

try:
    row=sample("/dashboard_report_datasets/"+dataset,"rows")
    if row is None:raise RuntimeError("BASELINE_ROWS_EMPTY")
    vals=row.get("original_values")
    types=row.get("original_cell_types")
    print("BASELINE_SAMPLE_PRESENT=YES")
    print("BASELINE_SHA_MATCH="+str(row.get("source_sha256")==sha).upper())
    print("BASELINE_COLUMNS_53="+str(isinstance(vals,list) and len(vals)==53).upper())
    print("BASELINE_INVOICE_FIELD_MATCH="+str(
        isinstance(vals,list) and len(vals)==53
        and isinstance(row.get("invoice_no"),str)
        and vals[12]==row.get("invoice_no")).upper())
    print("BASELINE_CELL_TYPES_53="+str(isinstance(types,list) and len(types)==53).upper())
    print("BASELINE_SOURCE_ROW_VALID="+str(type(row.get("source_row")) is int
         and 2<=row["source_row"]<=14375).upper())
    print("BASELINE_BALANCE_VALID_BOOLEAN="+str(type(row.get("balance_valid")) is bool).upper())
    print("BASELINE_SOURCE_VALUES_SHA_MATCH="+str(
        row.get("original_columns_source_sha256")==sha).upper())
    print("REPORT_HEADERS_53_CONTRACT="+str(len(HEADERS_53)==53).upper())

    imported=sample("", "dashboard_invoice_rows_v140")
    if imported is None:
        print("IMPORTED_ROW_SAMPLE=NONE_FOUND_NOT_PROOF_OF_EMPTY_COLLECTION")
    else:
        print("IMPORTED_ROW_SAMPLE=PRESENT")
        print("IMPORTED_RECEIPT_REFERENCE_PRESENT="+str(
            isinstance(imported.get("import_receipt"),str)
            and len(imported["import_receipt"])==32).upper())
        print("IMPORTED_ORIGINAL_VALUE_WIDTH="+str(
            len(imported.get("original_values",[]))
            if isinstance(imported.get("original_values"),list)
            else "INVALID"))
    print("QUERY_RESULT_INVOICE_DATA_PRINTED=NONE")
    print("FIRESTORE_ROWS_SAMPLED=AT_MOST_2")
    print("FIRESTORE_WRITES=NONE")
    print("CLOUD_RUN_DEPLOYMENTS=NONE")
    print("AWS_PUBLIC_APPLICATION=UNCHANGED")
    print("PR129_AWS_INVOICE_ROW_SCHEMA_PROBE=COMPLETE")
finally:
    session.close()
PY
