#!/usr/bin/env bash
# PR129: existing private backend /reports metadata probe (AWS-side).
# Calls an ALREADY-RUNNING Cloud Run service. Does not deploy anything.
# Does not download CSVs, print invoice rows, change IAM or write financial data.
set -Eeuo pipefail
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net

test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true || {
 echo 'STOP: AWS_PREVIEW_NOT_RUNNING'; exit 1;
}
test "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" || {
 echo 'STOP: UNEXPECTED_AWS_PREVIEW_NETWORK'; exit 1;
}

echo '=== PR129 EXISTING VERIFIED BACKEND REPORT CATALOG ==='
sudo docker exec -i -w /app "$C" python -B - <<'PY'
import requests
from cloud_auth import get_backend_token
from urllib.parse import urlparse

backend = "https://sbi-supervisor-backend-109590290120.asia-south1.run.app"
parsed = urlparse(backend)
assert parsed.scheme == "https" and parsed.hostname.endswith(".run.app")
assert not parsed.username and not parsed.password and not parsed.query
print("BACKEND=EXISTING_SBI_SUPERVISOR")
print("REQUEST_PATH=/reports")
print("REQUEST_METHOD=GET")
print("INVOICE_NUMBERS_SENT=NONE")
print("NEW_SERVICE_DEPLOYMENT=NONE")

try:
    token = get_backend_token(backend)
    resp = requests.get(
        backend + "/reports",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json"},
        timeout=(5, 45),
        allow_redirects=False,
        stream=True,
    )
    print("EXISTING_BACKEND_REPORT_CATALOG_HTTP=" + str(resp.status_code))
    ctype=resp.headers.get("Content-Type", "").lower()
    if resp.status_code != 200:
        print("EXISTING_BACKEND_REPORT_SOURCE=UNAVAILABLE_OR_UNAUTHORIZED")
    elif "application/json" not in ctype:
        print("EXISTING_BACKEND_REPORT_SOURCE=UNEXPECTED_CONTENT_TYPE")
    else:
        raw = resp.raw.read(524289, decode_content=True)
        if len(raw) > 524288:
            print("EXISTING_BACKEND_REPORT_SOURCE=METADATA_TOO_LARGE")
        else:
            try:
                data = requests.models.complexjson.loads(raw)
            except ValueError:
                data = {}
            reports=data.get("reports") if isinstance(data,dict) else None
            if not isinstance(reports,dict):
                print("EXISTING_BACKEND_REPORT_SOURCE=UNEXPECTED_SCHEMA")
            else:
                print("EXISTING_BACKEND_REPORT_SOURCE=AVAILABLE")
                print("SOURCE_VERSION=" + str(data.get("version", "UNKNOWN"))[:30])
                total=data.get("total_invoice_rows")
                print("VERIFIED_INVOICE_ROWS=" +
                      (str(total) if isinstance(total,int) and total >= 0
                       else "UNKNOWN"))
                for name in ("unpaid","ok","error-value","balance-review"):
                    record=reports.get(name)
                    count=(record.get("rows") if isinstance(record,dict) else None)
                    print("REPORT=" + name + " ROWS=" +
                          (str(count) if isinstance(count,int) and count>=0
                           else "NOT_AVAILABLE"))
    resp.close()
except requests.RequestException as exc:
    print("BACKEND_REPORT_REQUEST=NETWORK_ERROR")
    print("ERROR_TYPE=" + type(exc).__name__)
except Exception as exc:
    print("BACKEND_REPORT_REQUEST=UNAVAILABLE")
    print("ERROR_TYPE=" + type(exc).__name__)
print("CSV_CONTENT_DOWNLOADED=NO")
print("INVOICE_ROWS_PRINTED=NO")
print("FINANCIAL_RECORDS_MODIFIED=NONE")
print("AWS_PUBLIC_APPLICATION=UNCHANGED")
print("PR129_EXISTING_BACKEND_CATALOG_PROBE=COMPLETE")
PY
