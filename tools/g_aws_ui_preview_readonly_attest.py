"""Read-only G AWS UI preview attestation for owner-approved isolated staging.

Environment: STAGING_URL, EXPECTED_SHA, PREVIEW_USERNAME, PREVIEW_PASSWORD.
No deployment, financial write, or log of credentials.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

def check(condition, label):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        raise SystemExit(1)

def main():
    url = os.environ.get("STAGING_URL", "").rstrip("/")
    expected = os.environ.get("EXPECTED_SHA", "")
    user = os.environ.get("PREVIEW_USERNAME", "")
    password = os.environ.get("PREVIEW_PASSWORD", "")
    parsed = urllib.parse.urlsplit(url)
    check(bool(re.fullmatch(r"[0-9a-f]{40}", expected)), "EXPECTED_SHA_FORMAT")
    check(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment
        and parsed.path in ("", "/"),
        "ISOLATED_HTTPS_URL_FORMAT",
    )
    check(parsed.hostname.lower() != "sbi-preview.13-232-241-221.sslip.io",
          "PUBLIC_AWS_PREVIEW_EXCLUDED")
    check(bool(user and password), "CREDENTIALS_PRESENT")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    token = base64.b64encode((user + ":" + password).encode()).decode("ascii")
    def fetch(path, authenticated=False):
        headers = {"Authorization": "Basic " + token} if authenticated else {}
        request = urllib.request.Request(url + path, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=15) as resp:
                return resp.status, resp.read(1_000_000)
        except urllib.error.HTTPError as exc:
            return exc.code, b""

    for path in ("/ui-preview", "/ui-preview.css", "/api/pipeline/version"):
        status, _ = fetch(path)
        check(status == 401, "ANONYMOUS_401_" + path)

    for path in ("/ui-preview", "/ui-preview.css", "/pipeline"):
        status, data = fetch(path, True)
        check(status == 200, "AUTHORIZED_200_" + path)
        if path == "/ui-preview":
            html = data.decode("utf-8")
            check("Engineering workspace" in html and 'href="/ui-preview.css"' in html,
                  "UI_HTML_AND_ASSET_LINK")

    status, data = fetch("/api/pipeline/version", True)
    check(status == 200, "AUTHORIZED_VERSION")
    version = json.loads(data)
    check(version.get("source_sha") == expected, "DEPLOYED_SOURCE_SHA")
    check(version.get("channel") == "aws-staging", "STAGING_CHANNEL")
    check(version.get("financial_api_connected") is False, "FINANCIAL_API_ISOLATION")
    status, data = fetch("/healthz")
    check(status == 200, "HEALTH_200")
    health = json.loads(data)
    check(health.get("financial_data_connected") is False, "FINANCIAL_DATA_ISOLATION")
    print("G_AWS_UI_STAGING_ATTESTATION=PASS")

if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, ValueError, KeyError, UnicodeError) as exc:
        print("ATTESTATION=FAIL", type(exc).__name__)
        sys.exit(1)
