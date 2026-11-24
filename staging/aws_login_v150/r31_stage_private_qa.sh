#!/usr/bin/env bash
# DB-R31.6: PRIVATE STAGING ONLY. No Caddy writes or production DB access.
# Usage: sudo bash r31_stage_private_qa.sh FULL_REVIEWED_GIT_SHA
set -Eeuo pipefail
umask 077
[[ $# -eq 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || { echo 'STOP=FULL_SHA_REQUIRED';exit 2; }
SHA="$1"
[[ "$(id -u)" == 0 ]] || { echo 'STOP=SUDO_REQUIRED';exit 2; }
ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || {
 echo 'STOP=UNPINNED_GIT_TREE';exit 2;
}
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || {
 echo 'STOP=GIT_WORKTREE_NOT_CLEAN';exit 2;
}
git -C "$ROOT" show "$SHA:staging/aws_login_v150/r31_stage_private_qa.sh" |
 cmp -s - "$0" || { echo 'STOP=DEPLOY_SCRIPT_NOT_PINNED';exit 2; }
exec 9>/run/lock/sbi-r31-private-qa.lock
flock -n 9 || { echo 'STOP=QA_STAGE_ALREADY_RUNNING';exit 2; }
PG='sbi-synthetic-postgres-38-31'
QA_DB='sbi_r31_owner_qa_20261125'
QANET='sbi-synthetic-isolated-38-31'
APP='sbi-pr129-modern-release-final'
PROXY='aws_lightsail-caddy-1'
STAGE='sbi-r31-auth-private-qa'
IMAGE="sbi-r31-auth-qa:$SHA"
FIREBASE='/etc/sbi-aws-login-v150/firebase-service-account.json'
LOGINENV='/etc/sbi-aws-login-v150/login.env'
RAW_CREDS='/home/ubuntu/sbi-db-management/db-r31-ownerqa'
STORE='/var/lib/sbi-r31-auth-qa'
EVIDENCE="$STORE/evidence"
SECRETS="$STORE/secrets"

for c in "$PG" "$APP" "$PROXY";do
 docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -Fxq true || {
  echo "STOP=RUNTIME_CONTAINER_MISSING_OR_STOPPED:$c";exit 2;
 }
done
[[ "$(docker network inspect -f '{{.Internal}}' "$QANET")" == true ]] || {
 echo 'STOP=QA_NETWORK_NOT_INTERNAL';exit 2;
}
PG_DBS="$(docker exec "$PG" psql -X -qAt -U postgres -d postgres -c \
 "SELECT string_agg(datname,',' ORDER BY datname) FROM pg_database
  WHERE datname IN ('sbi_reconciliation_main','$QA_DB')")"
[[ "$PG_DBS" == "$QA_DB" ]] || {
 echo 'STOP=QA_DATABASE_IDENTITY_OR_PRODUCTION_EXPOSURE';exit 2;
}
UNIQUE_STATE="$(docker exec "$PG" psql -X -qAt -U postgres -d "$QA_DB" -c \
 "SELECT (SELECT count(*) FROM pg_indexes WHERE schemaname='sbi'
    AND indexname IN ('ux_r31_qa_owned_source_sha','ux_r31_qa_legacy_source_sha'))
    ||'|'||(SELECT count(*) FROM pg_constraint WHERE
    conrelid='sbi.import_batches'::regclass AND contype='u'
    AND pg_get_constraintdef(oid) LIKE
    'UNIQUE (source_system, source_kind, source_sha256)%')")"
[[ "$UNIQUE_STATE" == '2|0' ]] || {
 echo 'STOP=OWNER_QA_DATABASE_NOT_APPROVED';exit 2;
}
echo 'DB_R31_ISOLATED_OWNER_QA_DATABASE=PASS'

[[ -f "$LOGINENV" && ! -L "$LOGINENV" &&
   "$(stat -c '%u:%a' "$LOGINENV")" == '0:600' ]] || {
 echo 'STOP=PRIVATE_FIREBASE_ENV';exit 2;
}
[[ -f "$FIREBASE" && ! -L "$FIREBASE" &&
   "$(stat -c '%u:%g:%a' "$FIREBASE")" == '0:10001:440' ]] || {
 echo 'STOP=PRIVATE_FIREBASE_ADMIN';exit 2;
}
for kind in ingest report;do
 path="$RAW_CREDS/$kind.env"
 [[ -f "$path" && ! -L "$path" && "$(stat -c '%a' "$path")" == '600' ]] || {
  echo 'STOP=PRIVATE_QA_ROLE_CREDENTIAL_MISSING';exit 2;
 }
done
# Reuse a non-internal Docker network already owned by Caddy, but NEVER
# add any Caddy route, host port or public DNS entry for this QA container.
NETWORK=''
for n in $(docker inspect -f \
 '{{range $name,$value := .NetworkSettings.Networks}}{{$name}} {{end}}' "$PROXY");do
 case "$n" in bridge|host|none|"$QANET")continue;;esac
 if [[ "$(docker network inspect -f '{{.Internal}}' "$n")" == false ]];then
  NETWORK="$n";break
 fi
done
[[ -n "$NETWORK" ]] || { echo 'STOP=SAFE_DOCKER_NETWORK_UNAVAILABLE';exit 2; }

if docker inspect "$STAGE" >/dev/null 2>&1;then
 [[ "$(docker inspect -f '{{.State.Running}}' "$STAGE")" == true ]] || {
  echo 'STOP=OLD_STAGE_CONTAINER_STOPPED';exit 2;
 }
 [[ "$(docker inspect -f '{{.Config.Image}}' "$STAGE")" == "$IMAGE" ]] || {
  echo 'STOP=OLD_STAGE_IMAGE_DIFFERENT';exit 2;
 }
 echo 'DB_R31_EXISTING_PRIVATE_STAGE=VERIFIED'
else
 [[ ! -L "$STORE" && ! -L "$EVIDENCE" && ! -L "$SECRETS" ]] || {
  echo 'STOP=PRIVATE_STAGE_SYMLINK';exit 2;
 }
 install -d -o 10001 -g 10001 -m 700 "$STORE" "$EVIDENCE" "$SECRETS"
 for kind in ingest report;do
  install -o 10001 -g 10001 -m 600 \
   "$RAW_CREDS/$kind.env" "$SECRETS/$kind.env"
 done
 docker build -f "$ROOT/staging/aws_login_v150/Dockerfile.r31_private_staging" \
   --build-arg SBI_SOURCE_SHA="$SHA" -t "$IMAGE" "$ROOT"
 [[ "$(docker image inspect -f \
  '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")" == "$SHA" ]] || {
  echo 'STOP=STAGING_IMAGE_SHA';exit 2;
 }
 docker run -d --name "$STAGE" --network "$NETWORK" \
   --user 10001:10001 --read-only --restart no \
   --tmpfs /tmp:rw,noexec,nosuid,size=16m \
   --cap-drop ALL --security-opt no-new-privileges \
   --pids-limit 128 --memory 384m \
   --env-file "$LOGINENV" \
   -e SBI_R31_PRIVATE_STAGING_ENABLED=isolated-ownerqa-firebase-csrf-v1 \
   -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-service-account.json \
   -e SBI_PAYMENT_EVIDENCE_DIR=/evidence \
   --mount "type=bind,src=$FIREBASE,dst=/run/secrets/firebase-service-account.json,readonly" \
   --mount "type=bind,src=$EVIDENCE,dst=/evidence" \
   --mount "type=bind,src=$SECRETS/ingest.env,dst=/run/secrets/r31-ingest.env,readonly" \
   --mount "type=bind,src=$SECRETS/report.env,dst=/run/secrets/r31-report.env,readonly" \
   "$IMAGE" >/dev/null
 docker network connect "$QANET" "$STAGE"
 echo 'DB_R31_PRIVATE_STAGE_CONTAINER_CREATED=PASS'
fi
PORT_BINDINGS="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$STAGE")"
[[ "$PORT_BINDINGS" == 'null' || "$PORT_BINDINGS" == '{}' ]] || {
 echo 'STOP=STAGING_CONTAINER_PUBLISHED_PORT';exit 2;
}
# Give the single non-root Gunicorn server time to become healthy.
READY=0
for attempt in $(seq 1 20);do
 if docker exec "$STAGE" python3 -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)" \
  >/dev/null 2>&1;then
  READY=1;break
 fi
 sleep 1
done
[[ "$READY" == 1 ]] || { echo 'STOP=PRIVATE_STAGE_HEALTHCHECK';exit 2; }

docker exec -i "$STAGE" python3 - <<'PY'
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
opener=build_opener(NoRedirect())
def check(path):
    try:return opener.open(Request('http://127.0.0.1:8080'+path),timeout=5).status
    except HTTPError as error:return error.code
for path,expect in (
 ('/healthz',200),('/login',200),
 ('/api/r31-private-qa/status',401),
 ('/api/r31-private-qa/sol-report',401),
 ('/api/r31-private-qa/payment-details.csv',401),
 ('/api/r31-private-qa/receipts/'+'a'*32+'/sync',401),
):
    actual=check(path)
    if actual!=expect:raise RuntimeError('QA_PRIVATE_AUTH_GUARD:'+path+':'+str(actual))
print('DB_R31_FIREBASE_SESSION_ANONYMOUS_GUARD=PASS')
PY
echo 'DB_R31_CADDY_PUBLIC_ROUTING=UNCHANGED'
echo 'DB_R31_REAL_FIREBASE_USER_AND_CSRF=NOT_YET_TESTED'
echo 'DB_R31_PRODUCTION_FINANCIAL_WRITES=NONE_BY_DEPLOYMENT'
echo 'DB_R31_RELEASE_STATUS=PRIVATE_QA_STAGED_NOT_PUBLIC'
echo '=== DB_R31 PRIVATE STAGING DEPLOYMENT COMPLETE ==='
