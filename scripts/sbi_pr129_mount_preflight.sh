#!/usr/bin/env bash
# Read-only mount inventory before promoting a private PR129 report image.
# No mount/credential contents or host-source paths are printed.
# Does not create containers, edit Caddy, restart services, or access invoices.
set -Eeuo pipefail
PREVIEW=sbi-bulk-report-pr129-https-preview
MAIN=aws_lightsail-sbi-preview-1
CADDY=aws_lightsail-caddy-1

echo '=== SBI REPORTS PREVIEW MOUNT REPLICATION PREFLIGHT ==='
for c in "$PREVIEW" "$MAIN" "$CADDY"; do
  test "$(sudo docker inspect "$c" --format '{{.State.Running}}')" = true || {
    echo "STOP_REQUIRED_CONTAINER_NOT_RUNNING=$c"; exit 1;
  }
done
echo '=== PR129 PREVIEW MOUNTS: NO HOST SOURCE PATHS ==='
sudo docker inspect "$PREVIEW" --format '{{range .Mounts}}{{printf "MOUNT_TYPE=%s DESTINATION=%s READ_WRITE=%t\n" .Type .Destination .RW}}{{end}}'
echo '=== MAIN ORIGINAL MOUNT COUNTS ==='
sudo docker inspect "$MAIN" --format '{{len .Mounts}}' | awk '{print "MAIN_MOUNT_COUNT="$1}'
sudo docker inspect "$PREVIEW" --format '{{len .Mounts}}' | awk '{print "PREVIEW_MOUNT_COUNT="$1}'

echo '=== CREDENTIAL BINDINGS (NO SECRET VALUES OR PATHS) ==='
sudo docker exec -i "$PREVIEW" python -B - <<'PY'
import os
from pathlib import Path
import google.auth
from google.auth.transport.requests import AuthorizedSession
from firebase_admin import auth
from dashboard_sessions import firebase_app
try:
    creds,project=google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    print("PREVIEW_GCP_ADC="+("AVAILABLE" if creds else "UNAVAILABLE"))
    print("PREVIEW_GCP_PROJECT_MATCH="+str(project in (None,"meghraj-reconciliation")).upper())
except Exception as exc:
    print("PREVIEW_GCP_ADC_ERROR="+type(exc).__name__)
    raise SystemExit(2)
key=os.getenv("GOOGLE_APPLICATION_CREDENTIALS","")
print("PREVIEW_CREDENTIAL_ENV_CONFIGURED="+str(bool(key)).upper())
if key:
    p=Path(key)
    print("PREVIEW_CREDENTIAL_FILE_PRESENT="+str(p.is_file()).upper())
    print("PREVIEW_CREDENTIAL_FILE_READABLE="+str(os.access(key,os.R_OK)).upper())
try:
    firebase_app()
    print("PREVIEW_FIREBASE_ADMIN_INITIALIZATION=PASS")
except Exception as exc:
    print("PREVIEW_FIREBASE_ADMIN_INITIALIZATION_ERROR="+type(exc).__name__)
    raise SystemExit(3)
PY

echo '=== SAFE VOLUME-FROM BLOCKERS ==='
sudo docker inspect "$PREVIEW" --format '{{range .Mounts}}{{println .Destination}}{{end}}' |
  while IFS= read -r dest; do
    [ -n "$dest" ] || continue
    case "$dest" in
      /app|/app/*|/tmp|/tmp/*|/var/run/docker.sock|/run/docker.sock|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*)
        echo "BLOCKED_MOUNT_DESTINATION=$dest"
        ;;
    esac
  done
echo 'HOST_SOURCE_PATHS_PRINTED=NONE'
echo 'CREDENTIAL_CONTENT_PRINTED=NONE'
echo 'CONTAINERS_CHANGED=NONE'
echo 'PUBLIC_GATEWAY_CHANGED=NONE'
echo 'FIRESTORE_INVOICE_ROWS_READ=NONE'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'SBI_PR129_MOUNT_PREFLIGHT=COMPLETE'
