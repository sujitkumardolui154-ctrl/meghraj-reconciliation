#!/usr/bin/env bash
# Emergency read-only SBI report-only gateway rollback.
# Use the exact backup directory shown by the deployment.
set -Eeuo pipefail
if [ "$#" -ne 1 ]; then
  echo 'USAGE: bash scripts/sbi_bulk_report_live_rollback.sh <rollback-directory>'; exit 2
fi
BACKUP="$1"
CADDY=aws_lightsail-caddy-1
MAIN=aws_lightsail-sbi-preview-1
case "$BACKUP" in
  /home/ubuntu/sbi-bulk-report-integration/releases/rollback-before-*) ;;
  *) echo 'STOP_UNEXPECTED_ROLLBACK_LOCATION'; exit 2 ;;
esac
[ -f "$BACKUP/Caddyfile" ] && [ -f "$BACKUP/Caddyfile.deployed" ] || {
  echo 'STOP_BOTH_CADDY_BACKUPS_REQUIRED'; exit 1;
}
[ "$(sudo docker inspect "$MAIN" --format '{{.State.Running}}')" = true ] || {
  echo 'STOP_OLD_MAIN_NOT_RUNNING'; exit 1;
}
CADDY_SOURCE="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
if [ -z "$CADDY_SOURCE" ]; then
  CADDY_DIR="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"
  [ -n "$CADDY_DIR" ] && CADDY_SOURCE="$CADDY_DIR/Caddyfile"
fi
[ -f "$CADDY_SOURCE" ] || { echo 'STOP_ACTIVE_CADDY_CONFIG_UNAVAILABLE'; exit 1; }
deployed="$(sudo sha256sum "$BACKUP/Caddyfile.deployed" | awk '{print $1}')"
current="$(sudo sha256sum "$CADDY_SOURCE" | awk '{print $1}')"
[ "$deployed" = "$current" ] || {
  echo 'STOP_GATEWAY_HAS_CHANGED_SINCE_RELEASE_DO_NOT_OVERWRITE'; exit 1;
}
sudo docker cp "$BACKUP/Caddyfile" "$CADDY:/tmp/sbi-bulk-report-rollback-check.Caddyfile"
sudo docker exec "$CADDY" caddy validate --config /tmp/sbi-bulk-report-rollback-check.Caddyfile >/dev/null
sudo cp "$BACKUP/Caddyfile" "$CADDY_SOURCE"
sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null
echo 'SBI_BULK_REPORT_LIVE_CADDY_ROLLBACK=PASS'
echo 'ORIGINAL_MAIN_CONTAINER=STILL_RUNNING'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
