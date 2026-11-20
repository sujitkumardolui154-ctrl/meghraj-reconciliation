#!/usr/bin/env bash
# Safely remove temporary PR129 HTTPS preview and restore original Caddyfile.
set -Eeuo pipefail
CADDY='aws_lightsail-caddy-1'
NET='sbi_pr129_preview_net'
PREVIEW='sbi-bulk-report-pr129-https-preview'
BACKUP='/home/ubuntu/sbi-bulk-report-integration/Caddyfile.pre-pr129.backup'
HOST='pr129.13-232-241-221.sslip.io'
MOUNTS=$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{printf "%s|%s|%s\n" .Destination .Type .Source}}{{end}}')
FILE=$(printf '%s\n' "$MOUNTS" | awk -F'|' '$1=="/etc/caddy/Caddyfile" && $2=="bind" {print $3}')
DIR=$(printf '%s\n' "$MOUNTS" | awk -F'|' '$1=="/etc/caddy" && $2=="bind" {print $3}')
if [ -z "$FILE" ] && [ -n "$DIR" ]; then FILE="$DIR/Caddyfile"; fi
if [ -z "$FILE" ] || [ ! -f "$FILE" ] || [ ! -f "$BACKUP" ]; then
  echo 'STOP: Missing gateway bind mount or original backup; no config changes'; exit 1
fi
if ! sudo grep -Fq "$HOST" "$FILE"; then
  echo 'STOP: Expected preview hostname not in Caddyfile; no restoration'; exit 1
fi
sudo cp "$BACKUP" "$FILE"
sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null
sudo docker rm -f "$PREVIEW" >/dev/null 2>&1 || true
sudo docker network disconnect "$NET" "$CADDY" >/dev/null 2>&1 || true
sudo docker network rm "$NET" >/dev/null 2>&1 || true
echo 'PR129_PREVIEW_REMOVED=YES'
echo 'PUBLIC_SITE_CADDYFILE=RESTORED_FROM_BACKUP'
echo "BACKUP_RETAINED=$BACKUP"
