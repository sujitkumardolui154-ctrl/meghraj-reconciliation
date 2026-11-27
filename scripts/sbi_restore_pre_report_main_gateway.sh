#!/usr/bin/env bash
# Undo an approved PR129-to-main route promotion only if active Caddy exactly
# matches the archived post-deployment config. Never overwrite later changes.
set -Eeuo pipefail
BACKUP_PATH="$1"
CADDY=aws_lightsail-caddy-1
MAIN=aws_lightsail-sbi-preview-1
case "$BACKUP_PATH" in
  /home/ubuntu/sbi-bulk-report-integration/releases/pr129-main-backup-*) ;;
  *) echo 'STOP_UNEXPECTED_ROLLBACK_FOLDER'; exit 1 ;;
esac
test -f "$BACKUP_PATH/Caddyfile" || { echo 'STOP_ORIGINAL_GATEWAY_BACKUP_MISSING'; exit 1; }
test -f "$BACKUP_PATH/Caddyfile.deployed" || { echo 'STOP_DEPLOYED_GATEWAY_HASH_MISSING'; exit 1; }
test "$(sudo docker inspect "$MAIN" --format '{{.State.Running}}')" = true || {
  echo 'STOP_OLD_MAIN_APP_UNAVAILABLE'; exit 1;
}
CADDY_SOURCE="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
if [ -z "$CADDY_SOURCE" ]; then
  CADDY_DIR="$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"
  [ -n "$CADDY_DIR" ] && CADDY_SOURCE="$CADDY_DIR/Caddyfile"
fi
test -f "$CADDY_SOURCE" || { echo 'STOP_ACTIVE_CONFIG_BIND_MISSING'; exit 1; }
deployed="$(sudo sha256sum "$BACKUP_PATH/Caddyfile.deployed" | cut -d' ' -f1)"
current="$(sudo sha256sum "$CADDY_SOURCE" | cut -d' ' -f1)"
test "$deployed" = "$current" || {
  echo 'STOP_CADDY_MODIFIED_AFTER_PROMOTION_MANUAL_REVIEW_REQUIRED'; exit 1;
}
sudo docker cp "$BACKUP_PATH/Caddyfile" "$CADDY:/tmp/sbi-main-rollback-validated.Caddyfile"
sudo docker exec "$CADDY" caddy validate --config /tmp/sbi-main-rollback-validated.Caddyfile >/dev/null
sudo cp "$BACKUP_PATH/Caddyfile" "$CADDY_SOURCE"
sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null
echo 'SBI_MAIN_GATEWAY_ROLLBACK=PASS'
echo 'ORIGINAL_MAIN_CONTAINER=RUNNING'
echo 'DATABASE_CHANGES=NONE'
