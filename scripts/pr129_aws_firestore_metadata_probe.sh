#!/usr/bin/env bash
# PR129: AWS-only Firestore snapshot metadata verification, no new GCP deploy.
# Only one read-only document GET; never fetches invoice rows or logs secrets.
# Requires verified master viewer entitlement; does not change IAM, source,
# Firestore documents, Firebase claims, Caddy, or production.
set -Eeuo pipefail

C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
[ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ] || {
    echo 'STOP: PREVIEW_NOT_RUNNING'; exit 1;
}
[ "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" ] || {
    echo 'STOP: UNEXPECTED_PREVIEW_NETWORK'; exit 1;
}

echo '=== PR129 EXISTING FIRESTORE SNAPSHOT METADATA PROBE ==='
sudo docker exec -i -w /app "$C" python -B - <<'PY'
from firebase_admin import auth
from dashboard_sessions import MASTER_UID, MASTER_EMAIL, firebase_app, is_master
from sbi_report_access import can_view_report
from urllib.parse import quote

try:
    user = auth.get_user(MASTER_UID, app=firebase_app())
    permitted = (
        user.uid == MASTER_UID
        and (user.email or "").casefold() == MASTER_EMAIL.casefold()
        and is_master(user)
        and can_view_report(user, {"uid": user.uid})
    )
    if not permitted:
        raise PermissionError("Verified master report viewer is required")
except Exception as exc:
    print("MASTER_REPORT_VIEWER_VERIFIED=NO")
    print("AUTH_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(2)
print("MASTER_REPORT_VIEWER_VERIFIED=YES")

# Exact dataset ID is from backend_source/report_api.py (v1.3.0).
source_sha="433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"
dataset=source_sha+"-report-v1"
project="meghraj-reconciliation"

try:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, credential_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/datastore"]
    )
except Exception as exc:
    print("AWS_FIRESTORE_ADC=UNAVAILABLE")
    print("AUTH_ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(3)

# Never print an access token, private credential or raw response.
print("AWS_FIRESTORE_ADC=AVAILABLE")
print("CREDENTIAL_PROJECT_MATCH=" +
      str(credential_project in (None, project)).upper())

url=("https://firestore.googleapis.com/v1/projects/"+project+
     "/databases/(default)/documents/dashboard_report_datasets/"+
     quote(dataset, safe=""))
try:
    session=AuthorizedSession(credentials)
    response=session.get(url,timeout=(5, 25),allow_redirects=False,stream=True)
    print("FIRESTORE_METADATA_HTTP="+str(response.status_code))
    if response.status_code != 200:
        print("FIRESTORE_READ_ACCESS=NOT_CONFIRMED")
        raise SystemExit(4)
    if "application/json" not in response.headers.get("Content-Type",""):
        raise ValueError("Unexpected Firestore metadata response content type")
    raw=response.raw.read(262145,decode_content=True)
    if len(raw)>262144:
        raise ValueError("Firestore metadata document exceeds expected size")
    from json import loads
    data=loads(raw.decode("utf-8"))
    fields=data.get("fields",{})
    def string(name):
        item=fields.get(name,{})
        return item.get("stringValue") if isinstance(item,dict) else None
    def number(name):
        item=fields.get(name,{})
        rawval=item.get("integerValue") if isinstance(item,dict) else None
        try:
            return int(rawval)
        except (ValueError,TypeError):
            return None
    print("SOURCE_SHA256_MATCH="+str(string("source_sha256")==source_sha).upper())
    print("SNAPSHOT_STATE="+str(string("state") or "UNKNOWN"))
    print("SNAPSHOT_ROWS="+str(number("rows")))
    print("ORIGINAL_COLUMNS_STATE="+str(string("original_columns_state") or "UNKNOWN"))
    print("ORIGINAL_COLUMN_COUNT="+str(number("original_column_count")))
    print("ORIGINAL_COLUMNS_ROW_COUNT="+str(number("original_columns_row_count")))
    h=fields.get("original_headers",{}).get("arrayValue",{}).get("values",[])
    print("ORIGINAL_HEADERS_53_PRESENT="+str(len(h)==53).upper())
    consistent=(string("source_sha256")==source_sha
                and string("state")=="READY"
                and number("rows")==14374
                and string("original_columns_state")=="READY"
                and number("original_column_count")==53
                and number("original_columns_row_count")==14374
                and len(h)==53)
    print("AWS_EXISTING_SNAPSHOT_METADATA="+("PASS" if consistent else "NEEDS_REVIEW"))
except SystemExit:
    raise
except Exception as exc:
    print("FIRESTORE_METADATA_VALIDATION=FAILED")
    print("ERROR_TYPE="+type(exc).__name__)
    raise SystemExit(5)
finally:
    try:
        response.close()
    except NameError:
        pass

print("FIRESTORE_INVOICE_ROWS_READ=NONE")
print("FIRESTORE_DOCUMENT_WRITES=NONE")
print("FIREBASE_CLAIMS_UPDATED=NO")
print("GOOGLE_CLOUD_DEPLOYMENT=NONE")
print("AWS_PUBLIC_APPLICATION=UNCHANGED")
print("PR129_AWS_FIRESTORE_METADATA_PROBE=COMPLETE")
PY
