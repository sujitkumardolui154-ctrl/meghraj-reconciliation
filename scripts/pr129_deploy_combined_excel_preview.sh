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
test "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true

for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  test -s "dashboard_source/$f" || { echo "SOURCE_MISSING=$f"; exit 1; }
done
python3 -m py_compile dashboard_source/bulk_reports.py dashboard_source/bulk_report_excel.py dashboard_source/test_bulk_report_combined_excel.py

BACKUP="$(mktemp -d "$BASE/pr129-combined-backup.XXXXXXXX")"
chmod 700 "$BACKUP"
CHANGING=0
rollback() {
  if [ "$CHANGING" -eq 1 ]; then
    echo 'COMBINED_PREVIEW_ROLLBACK=STARTED'
    for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
      if [ -f "$BACKUP/$f" ]; then
        sudo docker cp "$BACKUP/$f" "$C:/app/$f" || true
        sudo docker exec -u 0 "$C" chmod 0644 "/app/$f" || true
      elif [ -f "$BACKUP/$f.absent" ]; then
        sudo docker exec -u 0 "$C" rm -f "/app/$f" || true
      fi
    done
    sudo docker restart "$C" >/dev/null || true
    echo 'COMBINED_PREVIEW_ROLLBACK=ATTEMPTED'
  fi
}
trap rollback ERR

for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  if sudo docker exec "$C" test -f "/app/$f"; then
    sudo docker cp "$C:/app/$f" "$BACKUP/$f"
    sudo chown "$(id -u):$(id -g)" "$BACKUP/$f"
    chmod 0644 "$BACKUP/$f"   # Docker cp can restore readable files even when stopped
  else
    : > "$BACKUP/$f.absent"
  fi
done

CHANGING=1
for f in bulk_reports.py bulk_report_excel.py test_bulk_report_combined_excel.py index.html; do
  sudo docker cp "dashboard_source/$f" "$C:/app/$f"
  # Required to avoid earlier 502 caused by unreadable source file.
  sudo docker exec -u 0 "$C" chmod 0644 "/app/$f"
done
echo '=== ONE SYNTHETIC SIX-SHEET TEST ==='
sudo docker exec -w /app -e PYTHONPATH=/app "$C" python -m unittest -v test_bulk_report_combined_excel

sudo docker restart "$C" >/dev/null
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
