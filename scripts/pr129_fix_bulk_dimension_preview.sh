#!/usr/bin/env bash
# Update only the temporary HTTPS PR129 Bulk Report preview backend.
# Protect public routing and preserve a rollback copy of the old code.
set -Eeuo pipefail

REPO="/home/ubuntu/sbi-bulk-report-integration/repo"
CONTAINER="sbi-bulk-report-pr129-https-preview"
NETWORK="sbi_pr129_preview_net"
HOST="pr129.13-232-241-221.sslip.io"
SRC="$REPO/dashboard_source/bulk_reports.py"
OLD="/app/bulk_reports.py"
BACKUP_BASE="/home/ubuntu/sbi-bulk-report-integration"
BACKUP_DIR="$(mktemp -d "$BACKUP_BASE/pr129-bulk-backup.XXXXXXXX")"
chmod 700 "$BACKUP_DIR"

echo '=== PR129 BULK REPORT DIMENSION FIX — TEMPORARY PREVIEW ONLY ==='
test -f "$SRC"
test "$(git -C "$REPO" branch --show-current)" = "ui/bulk-report-reports-tab-20261121"
test -z "$(git -C "$REPO" diff --name-only)"
sudo docker container inspect "$CONTAINER" >/dev/null
test "$(sudo docker inspect "$CONTAINER" --format '{{.State.Running}}')" = "true"
test "$(sudo docker inspect "$CONTAINER" --format '{{.HostConfig.NetworkMode}}')" = "$NETWORK"
python3 -m py_compile "$SRC"
sudo docker exec "$CONTAINER" test -f "$OLD"
sudo docker cp "$CONTAINER:$OLD" "$BACKUP_DIR/bulk_reports.py"
sudo chown "$(id -u):$(id -g)" "$BACKUP_DIR/bulk_reports.py"
chmod 600 "$BACKUP_DIR/bulk_reports.py"

UPDATED=0
rollback() {
  if [ "$UPDATED" -eq 1 ]; then
    echo "PREVIEW_BACKEND=ROLLBACK_STARTED"
    sudo docker cp "$BACKUP_DIR/bulk_reports.py" "$CONTAINER:$OLD" || true
    sudo docker restart "$CONTAINER" >/dev/null || true
    echo "PREVIEW_BACKEND=ROLLBACK_ATTEMPTED"
  fi
}
trap rollback ERR

sudo docker cp "$SRC" "$CONTAINER:$OLD"
UPDATED=1
sudo docker exec "$CONTAINER" python -m py_compile "$OLD"
LOCAL_HASH="$(sha256sum "$SRC" | awk '{print $1}')"
REMOTE_HASH="$(sudo docker exec "$CONTAINER" sha256sum "$OLD" | awk '{print $1}')"
test "$LOCAL_HASH" = "$REMOTE_HASH"
sudo docker restart "$CONTAINER" >/dev/null

HTTP="000"
for i in 1 2 3 4 5 6 7 8; do
  HTTP="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    --max-time 8 -sS -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)"
  [ "$HTTP" = "200" ] && break
  sleep 2
done
test "$HTTP" = "200"

ANON="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
  --max-time 8 -sS -o /dev/null -w '%{http_code}' \
  "https://$HOST/api/bulk-report/status" 2>/dev/null || true)"
case "$ANON" in 401|403) ;; *) echo "UNEXPECTED_ANONYMOUS_STATUS=$ANON"; false;; esac
UPDATED=0
trap - ERR
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "PREVIEW_ANONYMOUS_BULK_HTTP=$ANON"
echo "PREVIEW_BACKEND_DIMENSION_FIX=PASS"
echo "ROLLBACK_BACKUP=$BACKUP_DIR/bulk_reports.py"
echo "PUBLIC_CADDY=UNCHANGED"
echo "FINANCIAL_WRITES=NONE"
