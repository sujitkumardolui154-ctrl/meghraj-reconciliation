#!/usr/bin/env bash
# PR129 combined Excel private-preview deployment. Never touch public Caddy or DB.
set -Eeuo pipefail
REPO='/home/ubuntu/sbi-bulk-report-integration/repo'
BASE='/home/ubuntu/sbi-bulk-report-integration'
C='sbi-bulk-report-pr129-https-preview'
NET='sbi_pr129_preview_net'
HOST='pr129.13-232-241-221.sslip.io'
cd "$REPO"
echo '=== COMBINED XLSX PREVIEW DEPLOYMENT ==='
test "$(git branch --show-current)" = 'ui/bulk-report-reports-tab-20261121'
test -z "$(git diff --name-only)"
test "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET"
# A failed previous update may have stopped Gunicorn; allow recovery from stopped.

for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  test -s "dashboard_source/$f" || { echo "SOURCE_MISSING=$f"; exit 1; }
done
python3 -m py_compile dashboard_source/bulk_reports.py dashboard_source/bulk_report_excel.py dashboard_source/test_bulk_report_combined_excel.py

BACKUP="$(mktemp -d "$BASE/pr129-combined-backup.XXXXXXXX")"
STAGED="$(mktemp -d "$BASE/pr129-combined-staged.XXXXXXXX")"
chmod 700 "$BACKUP" "$STAGED"
trap 'rm -rf "$STAGED"' EXIT
CHANGING=0
rollback() {
  if [ "$CHANGING" -eq 1 ]; then
    echo 'COMBINED_PREVIEW_ROLLBACK=STARTED'
    for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
      if [ -f "$BACKUP/$f" ]; then
        sudo docker cp "$BACKUP/$f" "$C:/app/$f" || true
        # Host backup is 0644; docker cp preserves it without in-container chmod.
      elif [ -f "$BACKUP/$f.absent" ]; then
        sudo docker exec -u 0 "$C" rm -f "/app/$f" || true
      fi
    done
    if [ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]; then
      sudo docker restart "$C" >/dev/null || true
    else
      sudo docker start "$C" >/dev/null || true
    fi
    echo 'COMBINED_PREVIEW_ROLLBACK=ATTEMPTED'
  fi
}
trap rollback ERR

for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  if sudo docker cp "$C:/app/$f" "$BACKUP/$f" >/dev/null 2>&1; then
    sudo chown "$(id -u):$(id -g)" "$BACKUP/$f"
    chmod 0644 "$BACKUP/$f"   # Docker cp can restore readable files even when stopped
  else
    : > "$BACKUP/$f.absent"
  fi
done

CHANGING=1
for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  # Mode must be set on the host: this container has dropped CAP_FOWNER.
  install -m 0644 "dashboard_source/$f" "$STAGED/$f"
  sudo docker cp "$STAGED/$f" "$C:/app/$f"
done

# Restart/start ONLY the isolated preview container, never the public services.
if [ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ]; then
  sudo docker restart "$C" >/dev/null
else
  sudo docker start "$C" >/dev/null
fi

# The installed modules must be readable by the container's normal user.
sudo docker exec "$C" python -c '
from pathlib import Path
files = ("bulk_reports.py", "bulk_report_excel.py",
         "test_bulk_report_combined_excel.py", "index.html")
for file in files:
    p = Path("/app") / file
    with p.open("rb") as h:
        h.read(1)
print("PREVIEW_FILES_READABLE=PASS")
'
echo '=== ONE SYNTHETIC SIX-SHEET TEST ==='
sudo docker exec -w /app -e PYTHONPATH=/app "$C" python -m unittest -v test_bulk_report_combined_excel
HTTP='000'
for i in 1 2 3 4 5 6 7 8; do
  HTTP="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" -sS --max-time 10 -o /dev/null -w '%{http_code}' "https://$HOST/login" 2>/dev/null || true)"
  [ "$HTTP" = 200 ] && break
  sleep 2
done
test "$HTTP" = 200
ANON="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" -sS --max-time 10 -o /dev/null -w '%{http_code}' "https://$HOST/api/bulk-report/status" 2>/dev/null || true)"
case "$ANON" in 401|403) ;; *) echo "ANONYMOUS_REPORT_STATUS_UNEXPECTED=$ANON"; false ;; esac
CHANGING=0
trap - ERR
echo 'COMBINED_EXCEL_QA=PASS'
echo 'PREVIEW_DEPLOYMENT=PASS'
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "ANONYMOUS_REPORT_STATUS_HTTP=$ANON"
echo "ROLLBACK_BACKUP=$BACKUP"
echo 'PUBLIC_APPLICATION=UNCHANGED'
echo 'FINANCIAL_WRITES=NONE'
