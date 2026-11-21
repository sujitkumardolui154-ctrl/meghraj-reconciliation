#!/usr/bin/env bash
# Read-only readiness check for invoice-number lookup on the AWS private preview.
# Does not fetch ID tokens, print credential contents, read financial rows, or deploy.
set -Eeuo pipefail
C=sbi-bulk-report-pr129-https-preview
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
echo '=== SELECTED INVOICE READ-ONLY CONNECTION PREFLIGHT ==='

test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true
sudo docker exec -i "$C" python - <<'PY'
import importlib.util
import os
from pathlib import Path
from app import app

def module_present(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False

routes={str(r):set(r.methods) for r in app.url_map.iter_rules()}
checks={
  "SELECTED_UPLOAD_POST_REGISTERED":
     "POST" in routes.get("/api/bulk-report/select-invoices-excel",set()),
  "INVOICE_PARSER_PRESENT":Path("/app/invoice_number_selection.py").is_file(),
  "REPORT_VIEWER_ACCESS_HELPER_PRESENT":
     module_present("sbi_report_access"),
  "GCP_IDENTITY_TOKEN_HELPER_PRESENT":
     module_present("cloud_auth"),
  "GCP_AUTH_LIBRARY_PRESENT":
     module_present("google.auth"),
  "LOOKUP_BACKEND_CONFIGURED":
     os.getenv("INVOICE_LOOKUP_BACKEND","").startswith("https://"),
  "ADC_CONFIG_REFERENCE_PRESENT":
     bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
  "ADC_CONFIG_FILE_MOUNTED":
     bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")) and
     Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).is_file(),
}
for key,value in checks.items():
    print(key+"="+("YES" if value else "NO"))
print("SENSITIVE_CREDENTIAL_CONTENT=NOT_READ")
PY

echo '=== PRIVATE BACKEND SOURCE READINESS ==='
cd "$REPO"
for f in backend_source/invoice_selection_report.py backend_source/main.py backend_source/report_api.py; do
  if [ -f "$f" ]; then echo "$f=AVAILABLE"; else echo "$f=MISSING"; fi
done
if grep -q '"/reports/invoice-selection"' backend_source/main.py; then
  echo 'PRIVATE_BACKEND_ROUTE_IN_GITHUB=YES'
else
  echo 'PRIVATE_BACKEND_ROUTE_IN_GITHUB=NO'
fi

if command -v gcloud >/dev/null 2>&1; then
  if gcloud run services describe sbi-supervisor-backend \
       --region asia-south1 --project meghraj-reconciliation \
       --format='value(status.url)' >/dev/null 2>&1; then
    echo 'GCP_CLOUD_RUN_SERVICE_DESCRIBE=SUCCESS'
  else
    echo 'GCP_CLOUD_RUN_SERVICE_DESCRIBE=UNAVAILABLE_OR_UNAUTHORIZED'
  fi
else
  echo 'GCLOUD_CLI=NOT_INSTALLED_ON_AWS'
fi

echo 'LIVE_BACKEND_LOOKUP_DEPLOYMENT=NOT_VERIFIED'
echo 'DATABASE_ROW_LOOKUP=NOT_PERFORMED'
echo 'PUBLIC_DEPLOYMENT=UNCHANGED'
echo 'FINANCIAL_WRITES=NONE'
echo 'INVOICE_LOOKUP_CONNECTION_PREFLIGHT=COMPLETE'
