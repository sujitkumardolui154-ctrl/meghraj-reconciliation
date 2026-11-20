#!/usr/bin/env bash
# Give ONLY the PR129 HTTPS preview read-only Firebase Admin credentials.
# No financial mounts, no Caddyfile edits and no public application switch.
set -Eeuo pipefail

STAGE="sbi-bulk-reports-v1-stage"
PREVIEW="sbi-bulk-report-pr129-https-preview"
BACKUP="sbi-bulk-report-pr129-before-adc"
NETWORK="sbi_pr129_preview_net"
CADDY="aws_lightsail-caddy-1"
IMAGE="sbi-bulk-report-pr129-https:local"
TMP=$(mktemp -d /tmp/sbi-pr129-adc.XXXXXXXX)
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT

echo '=== PR129 PREVIEW FIREBASE ADMIN FIX ==='
for c in "$STAGE" "$PREVIEW" "$CADDY"; do
  sudo docker container inspect "$c" >/dev/null
done
sudo docker image inspect "$IMAGE" >/dev/null
sudo docker network inspect "$NETWORK" >/dev/null
if sudo docker container inspect "$BACKUP" >/dev/null 2>&1; then
  echo 'STOP: Existing rollback container requires review'; exit 1
fi
if [ "$(sudo docker inspect "$PREVIEW" --format '{{.Config.Image}}')" != "$IMAGE" ]; then
  echo 'STOP: Unexpected preview image'; exit 1
fi
if [ "$(sudo docker inspect "$PREVIEW" --format '{{.HostConfig.NetworkMode}}')" != "$NETWORK" ]; then
  echo 'STOP: Unexpected preview Docker network'; exit 1
fi
if [ "$(sudo docker inspect "$PREVIEW" --format '{{json .Mounts}}')" != '[]' ]; then
  echo 'STOP: Preview mounts changed unexpectedly'; exit 1
fi

# Identify ADC file via Docker's mount metadata, not via copying secrets.
ADC="$(sudo docker inspect "$STAGE" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^GOOGLE_APPLICATION_CREDENTIALS=//p' | head -1)"
if [ -z "$ADC" ] || ! sudo docker exec "$STAGE" test -f "$ADC"; then
  echo 'STOP: Staging ADC file not configured'; exit 1
fi

HOST_FILE="$(sudo docker inspect "$STAGE" --format '{{json .Mounts}}' | python3 -c '
import json,os,sys
target=os.environ.get("NOT_USED","")
# Credentials path is passed as a command-line argument, not printed.
target=sys.argv[1]
mounts=json.load(sys.stdin)
matches=[]
for m in mounts:
    if m.get("Type") not in ("bind","volume"): continue
    dst=os.path.normpath(m.get("Destination",""))
    src=os.path.normpath(m.get("Source",""))
    if not dst.startswith("/") or not src.startswith("/"): continue
    if target==dst or target.startswith(dst.rstrip("/")+"/"):
        relative=os.path.relpath(target,dst)
        candidate=src if relative=="." else os.path.join(src,relative)
        matches.append((len(dst),candidate))
if matches: print(max(matches)[1])
' "$ADC")"
if [ -z "$HOST_FILE" ] || ! sudo test -f "$HOST_FILE" || sudo test -L "$HOST_FILE"; then
  echo 'STOP: ADC is not directly available as one host file'; exit 1
fi

# Preserve only the Firebase web API configuration, in an ephemeral 0600 file.
sudo docker exec "$PREVIEW" python -c '
import os,sys
value=os.environ.get("FIREBASE_WEB_API_KEY","")
if not value: sys.exit(1)
print("FIREBASE_WEB_API_KEY="+value)
' > "$TMP/firebase.env"
chmod 600 "$TMP/firebase.env"

rollback() {
  echo 'PREVIEW_REPLACEMENT=FAILED; attempting rollback'
  sudo docker rm -f "$PREVIEW" >/dev/null 2>&1 || true
  if sudo docker container inspect "$BACKUP" >/dev/null 2>&1; then
    sudo docker rename "$BACKUP" "$PREVIEW" || true
    sudo docker start "$PREVIEW" >/dev/null || true
    echo 'PREVIEW_ROLLBACK=ATTEMPTED'
  fi
}
sudo docker rename "$PREVIEW" "$BACKUP"
sudo docker stop "$BACKUP" >/dev/null
trap 'rollback; rm -rf "$TMP"' ERR

sudo docker run -d --restart=no --name "$PREVIEW" \
  --network "$NETWORK" \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --env-file "$TMP/firebase.env" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/pr129-firebase-adc.json \
  --mount "type=bind,src=$HOST_FILE,dst=/run/secrets/pr129-firebase-adc.json,readonly" \
  "$IMAGE" >/dev/null

# This checks ADC loading only; it never prints credential data.
sudo docker exec "$PREVIEW" python -c '
from dashboard_sessions import firebase_app
app=firebase_app()
app.credential.get_credential()
print("FIREBASE_ADMIN_CREDENTIALS=AVAILABLE")
'
HTTP="000"
for i in 1 2 3 4 5 6; do
  HTTP="$(sudo docker exec "$PREVIEW" python -c '
import urllib.request
try:
 print(urllib.request.urlopen("http://127.0.0.1:8080/login",timeout=3).status)
except Exception:
 print("000")
' | tail -1)"
  [ "$HTTP" = 200 ] && break
  sleep 2
done
if [ "$HTTP" != 200 ]; then
  echo "PREVIEW_LOGIN_HTTP=$HTTP"; false
fi

# Confirm the existing preview hostname reaches this replacement via Caddy.
HOST='pr129.13-232-241-221.sslip.io'
HTTPS='000'
for i in 1 2 3 4 5 6; do
  HTTPS="$(curl --noproxy '*' --resolve "$HOST:443:127.0.0.1" \
    -sS --max-time 8 -o /dev/null -w '%{http_code}' \
    "https://$HOST/login" 2>/dev/null || true)"
  [ "$HTTPS" = 200 ] && break
  sleep 2
done
if [ "$HTTPS" != 200 ]; then
  echo "PREVIEW_HTTPS_LOGIN_HTTP=$HTTPS"; false
fi
trap 'rm -rf "$TMP"' EXIT
trap - ERR
echo "PREVIEW_LOGIN_HTTP=$HTTP"
echo "PREVIEW_HTTPS_LOGIN_HTTP=$HTTPS"
echo 'PREVIEW_FIREBASE_ADMIN_FIX=PASS'
echo "OLD_PREVIEW_ROLLBACK_CONTAINER=$BACKUP"
echo 'PUBLIC_CADDYFILE=UNCHANGED'
echo 'FINANCIAL_MOUNTS=NONE'
echo 'FINANCIAL_WRITES=NOT_REQUESTED'
