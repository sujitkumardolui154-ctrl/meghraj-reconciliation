#!/usr/bin/env bash
# SBI Batch 12 — prepare a fail-closed CREDIT NOTE module for the main dashboard.
# No deployment, IAM grants, database changes, or production traffic changes.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
PROJECT="meghraj-reconciliation"
REGION="asia-south1"
BUCKET="meghraj-sbi-reports-private-109590290120"
if [[ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]]; then
  echo 'STOP: Unexpected Google Cloud project'; exit 2
fi
if [[ ! -f dashboard_source/sbi_credit_report_auth.py && ! -d dashboard_source ]]; then
  echo 'STOP: dashboard_source is not available'; exit 2
fi
ROOT="dashboard_source"
MOD="$ROOT/sbi_credit_report_auth.py"
if [[ -f "$MOD" ]]; then
  if grep -q 'SBI_AUTHORIZED_CREDIT_REPORT_V1' "$MOD"; then
    echo 'MAIN REPORT MODULE: ALREADY PREPARED'
  else
    echo 'STOP: Existing dashboard report module is unfamiliar; unchanged'; exit 2
  fi
else
  cat > "$MOD" <<'PY'
"""SBI_AUTHORIZED_CREDIT_REPORT_V1.

Inert until the main app explicitly calls create_credit_note_blueprint(authorize).
The authorize callback must return literal True for the current request.
Do not attach without verified application authentication and permission tests.
"""
import csv
import hashlib
import io
import json
import os
import re
from html import escape
from urllib.parse import urlparse
from flask import Blueprint, Response, abort, jsonify

_ALLOWED_BUCKET = "meghraj-sbi-reports-private-109590290120"
_EXPECTED_HEADER_COUNT = 18


def _read_snapshot():
    from google.cloud import storage
    uri = os.environ.get("SBI_CREDIT_GCS_PREFIX", "")
    parts = urlparse(uri)
    key = parts.path.strip("/")
    if parts.scheme != "gs" or parts.netloc != _ALLOWED_BUCKET:
        raise ValueError("Private report bucket mismatch")
    if not re.fullmatch(r"credit-note/snapshot-\d{8}T\d{6}Z", key):
        raise ValueError("Unapproved report snapshot path")
    client = storage.Client(project="meghraj-reconciliation")
    bucket = client.bucket(parts.netloc)
    man = json.loads(bucket.blob(key + "/manifest.json").download_as_bytes(timeout=30))
    raw = bucket.blob(key + "/report.csv").download_as_bytes(timeout=60)
    conflicts = bucket.blob(key + "/conflicts.csv").download_as_bytes(timeout=30)
    if hashlib.sha256(raw).hexdigest() != man.get("report_sha256"):
        raise ValueError("CREDIT NOTE snapshot hash mismatch")
    if man.get("release_status") != "REVIEW_REQUIRED":
        raise ValueError("Unexpected release classification")
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = next(rows, [])
    if len(header) != _EXPECTED_HEADER_COUNT:
        raise ValueError("Invalid report column width")
    if header[16].strip().lower().startswith("payment received") is False:
        raise ValueError("Column U position not verified")
    if header[17] != "Credi note":
        raise ValueError("Column R header mismatch")
    count = 0
    for line in rows:
        if len(line) != _EXPECTED_HEADER_COUNT:
            raise ValueError("Report row has unexpected column width")
        count += 1
    if count != man.get("all_invoice_rows"):
        raise ValueError("Manifest row count mismatch")
    if not (isinstance(man.get("credit_note_unique_invoices"), int)
            and isinstance(man.get("credit_note_confirmed_unique_invoices"), int)
            and isinstance(man.get("conflicting_duplicate_invoice_numbers"), int)):
        raise ValueError("Missing verified report counts")
    if man["credit_note_confirmed_unique_invoices"] > man["credit_note_unique_invoices"]:
        raise ValueError("Conflicting report totals")
    return man, raw, conflicts


def create_credit_note_blueprint(authorize):
    """Return a Blueprint; never assume an authenticated session."""
    if not callable(authorize):
        raise ValueError("Explicit application authorization callback required")
    bp = Blueprint("sbi_credit_note_auth", __name__)

    @bp.before_request
    def _enforce_authorization():
        try:
            allowed = authorize()
        except Exception:
            abort(403)
        if allowed is not True:
            abort(403)

    @bp.get("/reports/credit-note/summary")
    def summary():
        try:
            meta, _, _ = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        fields = ("all_invoice_rows", "credit_note_unique_invoices",
                  "credit_note_confirmed_unique_invoices",
                  "conflicting_duplicate_invoice_numbers",
                  "completed_import_rows", "report_sha256")
        result = {f: meta.get(f) for f in fields}
        result.update(release_status="REVIEW_REQUIRED", snapshot_only=True,
                      import_completeness="NOT_CERTIFIED",
                      financial_execution="RESTRICTED")
        response = jsonify(result)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.get("/reports/credit-note.csv")
    @bp.get("/reports/credit-note/conflicts.csv")
    def csv_report():
        from flask import request
        try:
            _, report, review = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        conflict_request = request.path.endswith("/conflicts.csv")
        raw = review if conflict_request else report
        name = "SBI_CREDIT_NOTE_CONFLICT_REVIEW.csv" if conflict_request else "SBI_CREDIT_NOTE_ALL_INVOICES.csv"
        return Response(raw, mimetype="text/csv", headers={
            "Content-Disposition": 'attachment; filename="' + name + '"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-SBI-Report-Status": "REVIEW_REQUIRED"})

    @bp.get("/reports/credit-note/ui")
    def ui():
        try:
            meta, _, _ = _read_snapshot()
        except Exception:
            return jsonify(error="Verified report unavailable"), 503
        numbers = (meta["all_invoice_rows"], meta["credit_note_unique_invoices"],
                   meta["credit_note_confirmed_unique_invoices"],
                   meta["conflicting_duplicate_invoice_numbers"])
        vals = [escape(str(number)) for number in numbers]
        html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>SBI CREDIT NOTE — Read-only review</title>'
                '<main><h2>CREDIT NOTE Report — Verified Snapshot</h2>'
                '<p>All invoice rows: ' + vals[0] + '</p>'
                '<p>Observed CREDIT NOTE invoices: ' + vals[1] + '</p>'
                '<p>Unambiguous CREDIT NOTE invoices: ' + vals[2] + '</p>'
                '<p>Conflicting invoice numbers: ' + vals[3] + '</p>'
                '<p><a href="/reports/credit-note.csv">Download report CSV</a></p>'
                '<p><a href="/reports/credit-note/conflicts.csv">Download conflict review</a></p>'
                '<p>REVIEW_REQUIRED. Imports not certified. Financial execution restricted.</p>'
                '</main></html>')
        return Response(html, mimetype="text/html", headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'",
            "X-Frame-Options": "DENY"})

    return bp
PY
  echo 'MAIN REPORT MODULE: CREATED (NOT ATTACHED)'
fi

python3 -m py_compile "$MOD"
PYTHONPATH="$ROOT" python3 - <<'PY'
from flask import Flask
import sbi_credit_report_auth as feature
from unittest.mock import patch

paths = ["/reports/credit-note/summary",
         "/reports/credit-note.csv",
         "/reports/credit-note/conflicts.csv",
         "/reports/credit-note/ui"]
denied = Flask("auth_denied")
denied.register_blueprint(feature.create_credit_note_blueprint(lambda: False))
with denied.test_client() as c:
    for p in paths:
        assert c.get(p).status_code == 403, p
exceptions = Flask("auth_exception")
def broken_auth():
    raise ValueError("missing session")
exceptions.register_blueprint(feature.create_credit_note_blueprint(broken_auth))
with exceptions.test_client() as c:
    for p in paths:
        assert c.get(p).status_code == 403, p
allowed = Flask("auth_approved")
allowed.register_blueprint(feature.create_credit_note_blueprint(lambda: True))
sample = {"all_invoice_rows":14374, "credit_note_unique_invoices":1009,
          "credit_note_confirmed_unique_invoices":1004,
          "conflicting_duplicate_invoice_numbers":5,
          "completed_import_rows":0, "release_status":"REVIEW_REQUIRED",
          "report_sha256":"synthetic-checksum"}
with patch.object(feature, "_read_snapshot", return_value=(
        sample,b"Invoice No,Credi note\r\nsynthetic,CREDIT NOTE\r\n",
        b"Invoice No,Status\r\nsynthetic,REVIEW_REQUIRED\r\n")):
    with allowed.test_client() as c:
        for p in paths:
            r=c.get(p)
            assert r.status_code == 200, (p,r.status_code)
            assert "no-store" in r.headers.get("Cache-Control","")
        assert c.get(paths[0]).json["credit_note_unique_invoices"]==1009
print("SYNTHETIC AUTH GATE — ANONYMOUS DENIED: PASS")
print("SYNTHETIC AUTH GATE — BROKEN SESSION DENIED: PASS")
print("SYNTHETIC AUTH GATE — APPROVED CALLBACK: PASS")
print("SYNTHETIC REPORT ROUTES: PASS")
PY

# Only inspect; do not modify identity, permissions, or active traffic.
gcloud storage buckets describe "gs://$BUCKET" --raw --format=json |
python3 -c 'import json,sys; obj=json.load(sys.stdin); i=obj.get("iamConfiguration",{}); assert i.get("publicAccessPrevention")=="enforced"; assert i.get("uniformBucketLevelAccess",{}).get("enabled") is True; print("PRIVATE BUCKET ACCESS: PASS")'

python3 - <<'PY'
from pathlib import Path
import ast,json
from collections import Counter
from datetime import datetime,timezone
files=sorted(Path("dashboard_source").rglob("*.py"))
auth_names=("login_required","auth_required","before_request","session","logout",
 "SESSION_COOKIE_SECURE","SESSION_COOKIE_HTTPONLY","SESSION_COOKIE_SAMESITE",
 "PERMANENT_SESSION_LIFETIME")
counts=Counter()
found=[]
for file in files:
    if len(file.relative_to("dashboard_source").parts)>4: continue
    if file.name=="sbi_credit_report_auth.py":continue
    try: text=file.read_text(encoding="utf-8")
    except Exception:continue
    for term in auth_names:
        if term.lower() in text.lower():counts[term]+=1
    try: tree=ast.parse(text)
    except SyntaxError:continue
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                if (isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute)
                    and dec.func.attr in ("route","get","post") and dec.args
                    and isinstance(dec.args[0],ast.Constant)
                    and isinstance(dec.args[0].value,str)):
                    route=dec.args[0].value
                    if route in ("/","/login","/logout","/dashboard") or route.startswith("/reports"):
                        found.append({"file":str(file),"route":route,"handler":n.name})
receipt={"updated_utc":datetime.now(timezone.utc).isoformat(),
 "auth_indicators_file_counts":dict(counts),"relevant_routes":found[:30],
 "feature_module":"dashboard_source/sbi_credit_report_auth.py",
 "main_app_integration":"NOT_ATTACHED",
 "application_authentication":"REQUIRES_VERIFIED_CALLBACK",
 "main_dashboard_deployed":False,
 "financial_execution":"RESTRICTED"}
path=Path("reports/credit_note/batch12_integration_prepared.json")
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
path.chmod(0o600)
print("MAIN DASHBOARD AUTH INDICATORS:",json.dumps(dict(counts),sort_keys=True))
print("RELEVANT MAIN DASHBOARD ROUTES:",len(found))
print("INTEGRATION RECEIPT:",path)
PY

echo "===== BATCH 12 FINAL RESULT ====="
echo "AUTH-REQUIRED REPORT MODULE: PREPARED"
echo "ANONYMOUS / MISSING SESSION: DENIED IN SYNTHETIC TEST"
echo "MAIN APP ROUTE ATTACHMENT: PENDING AUTH CALLBACK VERIFICATION"
echo "MAIN DASHBOARD / PRODUCTION TRAFFIC: UNCHANGED"
echo "FINANCIAL EXECUTION: RESTRICTED"
echo "BATCH 12 MODULE PREPARATION COMPLETE"
