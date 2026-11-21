#!/usr/bin/env bash
# PR #129: temporary, authenticated HTTPS preview ONLY.
# Adds a distinct vhost; never changes the public SITE_DOMAIN route.
set -Eeuo pipefail

HOST="pr129.13-232-241-221.sslip.io"
EXPECTED_IP="13.232.241.221"
CADDY="aws_lightsail-caddy-1"
OLD="sbi-bulk-report-pr129-preview"
PREVIEW="sbi-bulk-report-pr129-https-preview"
NETWORK="sbi_pr129_preview_net"
IMAGE="sbi-bulk-report-pr129-https:local"
BASE="/home/ubuntu/sbi-bulk-report-integration"
BACKUP="$BASE/Caddyfile.pre-pr129.backup"
REPO="$BASE/repo"
TMP=$(mktemp -d /tmp/sbi-pr129-https.XXXXXXXX)
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT

echo "=== PR129 TEMPORARY HTTPS PREVIEW ==="
if [ ! -f "$REPO/dashboard_source/dashboard_sessions.py" ]; then
  echo "STOP: GitHub checkout missing"; exit 1
fi
MOUNTS=$(sudo docker inspect "$CADDY" --format '{{range .Mounts}}{{printf "%s|%s|%s\n" .Destination .Type .Source}}{{end}}')
CADDY_FILE=$(printf '%s\n' "$MOUNTS" | awk -F'|' '$1=="/etc/caddy/Caddyfile" && $2=="bind" {print $3}')
CADDY_DIR=$(printf '%s\n' "$MOUNTS" | awk -F'|' '$1=="/etc/caddy" && $2=="bind" {print $3}')
if [ -z "$CADDY_FILE" ] && [ -n "$CADDY_DIR" ]; then
  CADDY_FILE="$CADDY_DIR/Caddyfile"
fi
if [ -z "$CADDY_FILE" ] || [ ! -f "$CADDY_FILE" ]; then
  echo "STOP: Caddyfile has no known host bind mount; active gateway untouched"
  exit 1
fi
if [ -e "$BACKUP" ] || sudo grep -Fq "$HOST" "$CADDY_FILE"; then
  echo "STOP: preview or preserved backup already exists; no duplicate edit"
  exit 1
fi
if sudo docker container inspect "$PREVIEW" >/dev/null 2>&1; then
  echo "STOP: HTTPS preview container already exists"; exit 1
fi
if sudo docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "STOP: isolated preview network already exists"; exit 1
fi
if ! getent ahostsv4 "$HOST" | awk '{print $1}' | grep -qx "$EXPECTED_IP"; then
  echo "STOP: preview hostname does not resolve to expected AWS IP"; exit 1
fi

# Preserve the Firebase web key as runtime env only; never echo its value.
sudo docker exec "$OLD" python -c 'import os,sys; k=os.getenv("FIREBASE_WEB_API_KEY",""); sys.exit(1) if not k else print("FIREBASE_WEB_API_KEY="+k)' > "$TMP/firebase.env"
chmod 600 "$TMP/firebase.env"
mkdir -p "$TMP/build"
python3 - "$REPO/dashboard_source/dashboard_sessions.py" "$TMP/build/dashboard_sessions.py" "$HOST" <<'PY'
from pathlib import Path
import sys
src,dst,host=sys.argv[1:]
s=Path(src).read_text()
needle='    "https://sbi-preview.13-232-241-221.sslip.io",'
if s.count(needle)!=1 or ('https://'+host) in s:
    raise SystemExit("STOP: unexpected CSRF origin source")
Path(dst).write_text(s.replace(needle,needle+'\n    "https://'+host+'",'))
PY
printf 'FROM sbi-bulk-report-pr129-preview:local\nCOPY dashboard_sessions.py /app/dashboard_sessions.py\n' > "$TMP/build/Dockerfile"
sudo docker build --pull=false --network=none -q -t "$IMAGE" "$TMP/build" >/dev/null

# The preview network contains only Caddy and this unprivileged preview.
# No database volume, published preview port, or financial environment is attached.
sudo docker network create --driver bridge "$NETWORK" >/dev/null
sudo docker run -d --restart=no --name "$PREVIEW" --network "$NETWORK" \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --env-file "$TMP/firebase.env" "$IMAGE" >/dev/null
sudo docker network connect "$NETWORK" "$CADDY"

sudo cp "$CADDY_FILE" "$BACKUP"
sudo chmod 600 "$BACKUP"
sudo cp "$CADDY_FILE" "$TMP/proposed.Caddyfile"
sudo chown "$(id -u):$(id -g)" "$TMP/proposed.Caddyfile"
cat >> "$TMP/proposed.Caddyfile" <<EOF

# PR129 TEMPORARY HTTPS PREVIEW — remove after sign-off
$HOST {
    encode gzip
    reverse_proxy $PREVIEW:8080
    header X-Content-Type-Options nosniff
    header Referrer-Policy no-referrer
}
EOF
sudo docker cp "$TMP/proposed.Caddyfile" "$CADDY:/tmp/pr129-proposed.Caddyfile"
if ! sudo docker exec "$CADDY" caddy validate --config /tmp/pr129-proposed.Caddyfile >/dev/null; then
  echo "PREVIEW_GATEWAY_VALIDATION=FAIL (current Caddy configuration unchanged)"
  exit 1
fi

rollback() {
  sudo cp "$BACKUP" "$CADDY_FILE"
  sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null || true
  echo "CADDY_ROLLBACK=RESTORED"
}
sudo tee "$CADDY_FILE" < "$TMP/proposed.Caddyfile" >/dev/null
if ! sudo docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile >/dev/null; then
  rollback; exit 1
fi

HTTP="000"
for i in 1 2 3 4 5 6; do
  HTTP=$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    --max-time 15 -sS -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)
  [ "$HTTP" = "200" ] && break
  sleep 5
done
if [ "$HTTP" != "200" ]; then
  echo "PREVIEW_HTTPS=FAIL HTTP=$HTTP"
  rollback; exit 1
fi
echo "PREVIEW_HTTPS=PASS"
echo "PREVIEW_URL=https://$HOST/login"
echo "PUBLIC_EXISTING_ROUTE=UNCHANGED"
echo "FINANCIAL_WRITES=NOT_REQUESTED"
echo "ROLLBACK_BACKUP=$BACKUP"
