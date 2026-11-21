#!/usr/bin/env bash
# Preview-only step: install missing auth modules WITHOUT enabling DB lookup.
# No Caddy edits, no public routes, no credentials printed or requested.
set -Eeuo pipefail
REPO=/home/ubuntu/sbi-bulk-report-integration/repo
C=sbi-bulk-report-pr129-https-preview
NET=sbi_pr129_preview_net
FILES="sbi_report_access.py cloud_auth.py"
cd "$REPO"

echo '=== PR129 PREVIEW AUTH HELPER INSTALL ==='
[ "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121 ] || {
  echo WRONG_GIT_BRANCH; exit 1;
}
[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo TRACKED_REPOSITORY_CHANGES_PRESENT; exit 1;
}
[ "$(sudo docker inspect "$C" --format '{{.State.Running}}')" = true ] || {
  echo PREVIEW_CONTAINER_NOT_RUNNING; exit 1;
}
[ "$(sudo docker inspect "$C" --format '{{.HostConfig.NetworkMode}}')" = "$NET" ] || {
  echo UNEXPECTED_PREVIEW_NETWORK; exit 1;
}
sudo docker exec -i "$C" python -B - <<'PY'
import os
if os.environ.get("INVOICE_LOOKUP_BACKEND"):
    raise SystemExit("STOP: LOOKUP_BACKEND_ALREADY_CONFIGURED")
print("VERIFIED_LOOKUP_BACKEND=DISCONNECTED")
PY

TMP="$(mktemp -d /home/ubuntu/sbi-bulk-report-integration/pr129-helpers.XXXXXXXX)"
chmod 0700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
for f in $FILES; do
  src="dashboard_source/$f"
  test -s "$src" || { echo "MISSING_SOURCE=$src"; exit 1; }
  python3 -B -m py_compile "$src"
  install -m 0644 "$src" "$TMP/$f"
  expected="$(sha256sum "$TMP/$f" | awk '{print $1}')"
  sudo docker cp "$TMP/$f" "$C:/app/$f"
  actual="$(sudo docker exec "$C" sha256sum "/app/$f" | awk '{print $1}')"
  [ "$expected" = "$actual" ] || { echo "FILE_SHA_MISMATCH=$f"; exit 1; }
  echo "$f=HASH_VERIFIED"
done

# Probe only loaded source and explicit role guards. No Firebase or GCP
# credential calls, no network, no Firestore read, no app reload required.
sudo docker exec -i -w /app "$C" python -B - <<'PY'
import os
import cloud_auth
import sbi_report_access
from types import SimpleNamespace
from app import app

routes = {str(rule): set(rule.methods) for rule in app.url_map.iter_rules()}
url = "/api/bulk-report/select-invoices-excel"
assert "POST" in routes.get(url, set()), "Selected report API missing"
assert callable(cloud_auth.get_backend_token)
assert callable(sbi_report_access.can_view_report)
assert not sbi_report_access.can_view_report(None, None)

user = SimpleNamespace(
    uid="synthetic-only",
    disabled=False,
    custom_claims={"dil_dashboard": True, "sbi_report_viewer": False},
)
identity = {"uid": "synthetic-only"}
assert not sbi_report_access.can_view_report(user, identity)
user.custom_claims["sbi_report_viewer"] = True
assert sbi_report_access.can_view_report(user, identity)
user.disabled = True
assert not sbi_report_access.can_view_report(user, identity)

assert not os.environ.get("INVOICE_LOOKUP_BACKEND"), "Backend must remain disconnected"
print("REPORT_VIEWER_ACCESS_HELPER_PRESENT=YES")
print("GCP_IDENTITY_TOKEN_HELPER_PRESENT=YES")
print("EXPLICIT_ROLE_GUARD_SYNTHETIC_QA=PASS")
print("SELECTED_UPLOAD_ROUTE=PASS")
print("VERIFIED_LOOKUP_BACKEND=DISCONNECTED")
PY

echo 'PR129_AUTH_HELPER_PREVIEW=PASS'
echo 'PRIVATE_BACKEND_DEPLOYMENT=NOT_PERFORMED'
echo 'PUBLIC_APPLICATION=UNCHANGED'
echo 'FINANCIAL_WRITES=NONE'
