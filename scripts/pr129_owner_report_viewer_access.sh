#!/usr/bin/env bash
# PR129: verify or explicitly authorize the existing master Firebase account
# for read-only invoice reports. Never change reconciliation / finance data.
# Run only on the trusted AWS Lightsail instance; require operator --grant.
set -Eeuo pipefail
CONTAINER=sbi-bulk-report-pr129-https-preview
NETWORK=sbi_pr129_preview_net
MODE=--inspect
if [ "$#" -gt 0 ]; then MODE="$1"; fi
case "$MODE" in
  --inspect|--grant-master-report-viewer) ;;
  *) echo "USAGE: bash scripts/pr129_owner_report_viewer_access.sh [--inspect|--grant-master-report-viewer]"; exit 2 ;;
esac

[ "$(sudo docker inspect "$CONTAINER" --format '{{.State.Running}}')" = true ] || {
  echo 'STOP: PREVIEW_NOT_RUNNING'; exit 1;
}
[ "$(sudo docker inspect "$CONTAINER" --format '{{.HostConfig.NetworkMode}}')" = "$NETWORK" ] || {
  echo 'STOP: UNEXPECTED_PREVIEW_NETWORK'; exit 1;
}
echo '=== PR129 OWNER REPORT VIEWER ENTITLEMENT ==='
sudo docker exec -i -w /app "$CONTAINER" python -B - "$MODE" <<'PY'
import sys
from firebase_admin import auth
from dashboard_sessions import MASTER_UID, MASTER_EMAIL, firebase_app, is_master
from sbi_report_access import can_view_report

mode = sys.argv[1]
if mode not in ("--inspect", "--grant-master-report-viewer"):
    raise SystemExit("STOP: INVALID_MODE")

try:
    app = firebase_app()
    user = auth.get_user(MASTER_UID, app=app)
except Exception as exc:
    print("FIREBASE_IDENTITY_LOOKUP=UNAVAILABLE")
    print("ERROR_TYPE=" + type(exc).__name__)
    raise SystemExit(3)

expected_email = (user.email or "").casefold() == MASTER_EMAIL.casefold()
master = expected_email and is_master(user)
claims = dict(user.custom_claims or {})
identity = {"uid": user.uid}

print("ACCOUNT_EMAIL_MATCH=" + str(expected_email).upper())
print("MASTER_DASHBOARD_ADMIN_VERIFIED=" + str(bool(master)).upper())
print("REPORT_VIEWER_CLAIM_PRESENT="
      + str(claims.get("sbi_report_viewer") is True).upper())
print("REPORT_VIEWER_ACCESS="
      + str(can_view_report(user, identity)).upper())
if not master:
    print("STOP: NOT_VERIFIED_MASTER_USER")
    raise SystemExit(4)

if mode == "--inspect":
    print("FIREBASE_CLAIMS_MUTATED=NO")
    print("NEXT_ACTION=" + ("NONE" if can_view_report(user, identity)
                           else "OPERATOR_MAY_GRANT_MASTER_REPORT_VIEWER"))
else:
    if claims.get("sbi_report_viewer") is not True:
        updated = dict(claims)
        updated["sbi_report_viewer"] = True
        # Only add one report-viewer entitlement. Never overwrite unrelated
        # admin, dashboard, credit-note or reconciliation-change claims.
        auth.set_custom_user_claims(user.uid, updated, app=app)
        print("FIREBASE_CLAIMS_MUTATED=MASTER_REPORT_VIEWER_ONLY")
    else:
        print("FIREBASE_CLAIMS_MUTATED=NO_ALREADY_AUTHORIZED")
    verified = auth.get_user(MASTER_UID, app=app)
    actual = dict(verified.custom_claims or {})
    if any(actual.get(k) != v for k, v in claims.items()):
        print("STOP: EXISTING_FIREBASE_CLAIMS_CHANGED_UNEXPECTEDLY")
        raise SystemExit(5)
    if not can_view_report(verified, {"uid": verified.uid}):
        print("STOP: REPORT_VIEWER_ACCESS_NOT_CONFIRMED")
        raise SystemExit(6)
    print("MASTER_REPORT_VIEWER_ACCESS=PASS")

print("INVOICE_LOOKUP_BACKEND=UNCHANGED")
print("PUBLIC_DEPLOYMENT=UNCHANGED")
print("FINANCIAL_DATABASE_WRITES=NONE")
PY
