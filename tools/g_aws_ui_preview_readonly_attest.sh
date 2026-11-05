#!/usr/bin/env bash
# G — UI preview read-only live attestation.
# Run only against an OWNER-APPROVED isolated staging URL.
# Requires: curl, python3; PREVIEW_USERNAME and PREVIEW_PASSWORD in environment.
# Example:
#   PREVIEW_USERNAME=... PREVIEW_PASSWORD=... \
#   EXPECTED_SHA=<40-character-commit-sha> \
#   STAGING_URL=https://approved-staging.example \
#   bash tools/g_aws_ui_preview_readonly_attest.sh
set -Eeuo pipefail
export LC_ALL=C

: "${STAGING_URL:?Set the owner-approved isolated STAGING_URL}"
: "${EXPECTED_SHA:?Set expected full 40-character source SHA}"
: "${PREVIEW_USERNAME:?Set the authorized staging username}"
: "${PREVIEW_PASSWORD:?Set the authorized staging password}"

if [[ ! "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ATTEST=FAIL REASON=EXPECTED_SHA_INVALID"; exit 2
fi
if [[ "${STAGING_URL}" != https://* ]] || [[ "${STAGING_URL}" == *'@'* ]] || [[ "${STAGING_URL}" == *'?'* ]] || [[ "${STAGING_URL}" == *'#'* ]]; then
  echo "ATTEST=FAIL REASON=STAGING_URL_MUST_BE_HTTPS"; exit 2
fi

# Do not allow accidental attestation/deployment assumption on the public preview host.
case "${STAGING_URL}" in
  https://sbi-preview.13-232-241-221.sslip.io|https://sbi-preview.13-232-241-221.sslip.io/)
    echo "ATTEST=BLOCKED REASON=PUBLIC_PREVIEW_NOT_ISOLATED_STAGING"; exit 2;;
esac

STAGING_URL="${STAGING_URL%/}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
CURL=(curl --silent --show-error --max-time 15 --connect-timeout 5 --proto '=https' --max-redirs 0)
status() {
  "${CURL[@]}" --output /dev/null --write-out '%{http_code}' "$1"
}
check_code() {
  local label="$1" url="$2" expected="$3" got
  got="$(status "$url")"
  if [[ "$got" != "$expected" ]]; then
    echo "FAIL ${label}: HTTP_${got}_EXPECTED_${expected}"; exit 1
  fi
  echo "PASS ${label}: HTTP_${expected}"
}
check_code "ANONYMOUS_UI_DENIED" "${STAGING_URL}/ui-preview" 401
check_code "ANONYMOUS_CSS_DENIED" "${STAGING_URL}/ui-preview.css" 401
check_code "ANONYMOUS_VERSION_DENIED" "${STAGING_URL}/api/pipeline/version" 401

# Curl config is passed through stdin so passwords are not displayed in process arguments.
# Never enable curl verbose/trace logging or shell xtrace when using these credentials.
auth_curl() {
  "${CURL[@]}" --config - "$@" <<EOF
user = "${PREVIEW_USERNAME}:${PREVIEW_PASSWORD}"
basic
EOF
}
# Quotes/backslashes/newlines in the credential would break curl's config grammar.
if [[ "${PREVIEW_USERNAME}${PREVIEW_PASSWORD}" == *[\"\\$'\n'$'\r']* ]]; then
  echo "ATTEST=BLOCKED REASON=UNSUPPORTED_CREDENTIAL_CHARACTERS"; exit 2
fi
auth_check() {
  local label="$1" path="$2" expected="$3" got
  got="$(auth_curl --output /dev/null --write-out '%{http_code}' "${STAGING_URL}${path}")"
  if [[ "$got" != "$expected" ]]; then
    echo "FAIL ${label}: HTTP_${got}_EXPECTED_${expected}"; exit 1
  fi
  echo "PASS ${label}: HTTP_${expected}"
}
auth_check "AUTHORIZED_UI" "/ui-preview" 200
auth_check "AUTHORIZED_CSS" "/ui-preview.css" 200
auth_check "AUTHORIZED_PIPELINE" "/pipeline" 200

auth_curl --fail --output "${TMP}/ui.html" "${STAGING_URL}/ui-preview"
auth_curl --fail --output "${TMP}/version.json" "${STAGING_URL}/api/pipeline/version"
"${CURL[@]}" --fail --output "${TMP}/health.json" "${STAGING_URL}/healthz"

python3 - "${TMP}" "${EXPECTED_SHA}" <<'PY'
import json, pathlib, sys
folder, expected_sha = pathlib.Path(sys.argv[1]), sys.argv[2]
html = (folder / "ui.html").read_text(encoding="utf-8")
version = json.loads((folder / "version.json").read_text(encoding="utf-8"))
health = json.loads((folder / "health.json").read_text(encoding="utf-8"))
assert 'Engineering workspace' in html, "UI_PREVIEW_MARKER_MISSING"
assert 'href="/ui-preview.css"' in html, "UI_PREVIEW_STYLESHEET_MISSING"
assert version.get("source_sha") == expected_sha, "SOURCE_SHA_MISMATCH"
assert version.get("channel") == "aws-staging", "NOT_ISOLATED_STAGING_CHANNEL"
assert version.get("financial_api_connected") is False, "FINANCIAL_API_NOT_DENIED"
assert health.get("financial_data_connected") is False, "FINANCIAL_DATABASE_NOT_DENIED"
print("PASS UI_ASSETS_PRESENT")
print("PASS DEPLOYED_SOURCE_SHA_MATCH")
print("PASS ISOLATED_AWS_STAGING_CHANNEL")
print("PASS FINANCIAL_API_CONNECTED_FALSE")
print("PASS FINANCIAL_DATA_CONNECTED_FALSE")
print("G_AWS_UI_STAGING_ATTESTATION=PASS")
PY
