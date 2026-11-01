#!/usr/bin/env bash
# SBI Batch 19 — fast-track from Batch18 to an isolated reporting release candidate.
# If Batch18 was not run, run it once. No production deploy or traffic mutation.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
RECEIPT="reports/consolidated_reporting_next_gate.json"
if [ ! -s "$RECEIPT" ]; then
  echo "BATCH 18 RECEIPT: MISSING — RUNNING APPROVED PREREQUISITE"
  PREREQ="$(mktemp)"
  trap 'rm -f "$PREREQ"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/c883ac2467a94dd54e34eb875639ee0d31c01ee1/tools/sbi_batch18_release_candidate_gate.sh" -o "$PREREQ"
  bash "$PREREQ"
fi

python3 - <<'PY'
import ast, hashlib, json, os, re, shutil, sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("dashboard_source")
SOURCE=ROOT/"production_gateway.py"
APP=Path("reports/credit_note/batch17_candidate/production_gateway_candidate.py")
BRIDGE=Path("reports/credit_note/batch17_candidate/sbi_credit_report_auth_bridge.py")
FEATURE=ROOT/"sbi_credit_report_auth.py"
SESSION=ROOT/"dashboard_sessions.py"
B18=Path("reports/consolidated_reporting_next_gate.json")
DEST=Path("staging_candidates/sbi_credit_report_batch19")
RESULT=Path("reports/credit_note/batch19_release_candidate.json")
res={
  "batch":"19",
  "checked_at_utc":datetime.now(timezone.utc).isoformat(),
  "prior_passed_reporting_checks":"REUSED",
  "import_completeness":"NOT_CERTIFIED",
  "auth_synthetic":"NOT_VERIFIED",
  "isolated_app_candidate":"NOT_BUILT",
  "login_cookie_mapping":"NOT_VERIFIED",
  "e2e_authenticated_user":"NOT_RUN",
  "reporting_release":"BLOCKED",
  "financial_release":"BLOCKED_SEPARATE_FINANCIAL_QA",
  "cloud_run_deployed":False,
  "active_traffic_changed":False,
  "source_dashboard_modified":False,
  "blockers":[]
}
def blocker(name):
    if name not in res["blockers"]:res["blockers"].append(name)
try:
    prev=json.loads(B18.read_text(encoding="utf-8"))
    res["import_completeness"]=prev.get("import_completeness","NOT_CERTIFIED")
    res["auth_synthetic"]=prev.get("local_http_auth_tests","NOT_VERIFIED")
    if res["import_completeness"]!="V140_NO_APPLIED_IMPORTS_EVIDENCE_PASS":
        blocker("IMPORT_COMPLETENESS_NOT_CERTIFIED")
    if res["auth_synthetic"]!="PASS_SYNTHETIC":
        blocker("BATCH18_AUTH_TESTS_NOT_PASSED")
except (OSError,ValueError,TypeError):
    blocker("BATCH18_RESULT_UNREADABLE")
files=(SOURCE,APP,BRIDGE,FEATURE,SESSION)
if not all(f.is_file() for f in files):
    blocker("STAGING_CANDIDATE_SOURCE_MISSING")
else:
    try:
        src=SOURCE.read_text(encoding="utf-8")
        candidate=APP.read_text(encoding="utf-8")
        bridge=BRIDGE.read_text(encoding="utf-8")
        feat=FEATURE.read_text(encoding="utf-8")
        session=SESSION.read_text(encoding="utf-8")
        expected_prefix=src.rstrip()
        if not candidate.startswith(expected_prefix):
            raise ValueError("Candidate drift from current production source")
        tail=candidate[len(expected_prefix):]
        if ("SBI_CREDIT_AUTH_ONLY_ZERO_TRAFFIC_CANDIDATE_V1" not in tail or
            tail.count("app.register_blueprint(create_credit_note_blueprint(may_view_credit_note))")!=1):
            raise ValueError("Unrecognized candidate route attachment")
        if "SBI_AUTHORIZED_CREDIT_REPORT_V1" not in feat:
            raise ValueError("Unexpected report blueprint")
        if "SBI_CREDIT_FIREBASE_ROLE_BRIDGE_V1" not in bridge:
            raise ValueError("Unexpected report identity bridge")
        if 'claims.get("sbi_credit_report_viewer") is True' not in bridge or (
                'claims.get("admin") is True' in bridge):
            raise ValueError("Report permission not explicit and strict")
        if 'verify_session_cookie(cookie,check_revoked=True)' not in bridge:
            raise ValueError("Session revocation verification missing")
        if not ("auth.verify_id_token" in session and
                "auth.verify_session_cookie" in session and
                "auth.revoke_refresh_tokens" in session):
            raise ValueError("Firebase session contract changed")
        tree=ast.parse(candidate,filename=str(APP))
        ast.parse(bridge,filename=str(BRIDGE))
        ast.parse(feat,filename=str(FEATURE))
        ast.parse(session,filename=str(SESSION))
        # Make a private isolated bundle. Only copy bounded application source;
        # skip secrets, keys, environment files and internal work artifacts.
        if DEST.exists():
            existing_app=DEST/"production_gateway.py"
            existing_bridge=DEST/"sbi_credit_report_auth_bridge.py"
            if (not existing_app.is_file() or not existing_bridge.is_file()
                or existing_app.read_text(encoding="utf-8")!=candidate
                or existing_bridge.read_text(encoding="utf-8")!=bridge):
                raise ValueError("Existing candidate differs; no overwrite")
            res["isolated_app_candidate"]="PREPARED_AUTH_ROUTE_MOUNTED_OFFLINE"
        else:
            ignore_patterns=shutil.ignore_patterns(
                "__pycache__","*.pyc",".git",".env",".env.*",
                "*.pem","*.p12","*.pfx","*.key","credentials*","service-account*",
                "*secret*","*private_key*","*.sqlite","*.db","*.log","*.xlsx",
                "*.csv","*.zip","*.tar","*.json")
            DEST.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            shutil.copytree(ROOT,DEST,ignore=ignore_patterns)
            (DEST/"production_gateway.py").write_text(candidate,encoding="utf-8")
            (DEST/"sbi_credit_report_auth_bridge.py").write_text(bridge,encoding="utf-8")
            (DEST/"sbi_credit_report_auth.py").write_text(feat,encoding="utf-8")
            for f in DEST.rglob("*"):
                if f.is_file(): f.chmod(0o600)
                elif f.is_dir():f.chmod(0o700)
            DEST.chmod(0o700)
        # Ensure candidate entrypoint syntax, runtime wiring and report scope.
        ast.parse((DEST/"production_gateway.py").read_text(encoding="utf-8"))
        res["isolated_app_candidate"]="PREPARED_AUTH_ROUTE_MOUNTED_OFFLINE"
        res["candidate_source_sha256"]=hashlib.sha256(candidate.encode()).hexdigest()
        res["candidate_directory"]=str(DEST)
        # Do not falsely claim that production's cookie name is known.
        cookie_source=re.findall(
            r'(?:SESSION_COOKIE|COOKIE_NAME|SESSION_COOKIE_NAME)\s*=\s*["\x27]([A-Za-z0-9_-]+)["\x27]',
            session)
        cookie_source=list(dict.fromkeys(cookie_source))
        if len(cookie_source)==1:
            res["login_cookie_mapping"]="STATIC_CANDIDATE_REVIEW_REQUIRED"
        else:
            res["login_cookie_mapping"]="NEEDS_EXACT_SESSION_COOKIE_MAPPING"
        blocker("VERIFY_PRODUCTION_COOKIE_NAME_AND_ROLE_CLAIM")
    except Exception as e:
        res["isolated_app_candidate"]="BLOCKED"
        res["candidate_error"]=type(e).__name__ + ": " + str(e)[:160]
        blocker("ISOLATED_PRODUCTION_CANDIDATE_NOT_VERIFIED")
# In addition to synthetic tests, production needs E2E checks of missing cookie,
# revoked cookie, expired cookie, and signed-in role-allowed/denied user sessions.
blocker("REAL_SIGNED_IN_AND_ANONYMOUS_HTTP_E2E_REQUIRED")
blocker("ZERO_TRAFFIC_CANDIDATE_DEPLOY_AND_ROLLBACK_TEST_REQUIRED")
# An isolated app candidate is not a production deployment.
if res["isolated_app_candidate"]=="PREPARED_AUTH_ROUTE_MOUNTED_OFFLINE":
    res["reporting_release"]="CANDIDATE_PREPARED_NOT_DEPLOYED"
RESULT.parent.mkdir(parents=True,exist_ok=True)
RESULT.write_text(json.dumps(res,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
RESULT.chmod(0o600)
print("===== BATCH 19 NEXT-RELEASE CANDIDATE =====")
print("IMPORT EVIDENCE:",res["import_completeness"])
print("BATCH 18 LOCAL AUTH QA:",res["auth_synthetic"])
print("ISOLATED PRODUCTION GATEWAY:",res["isolated_app_candidate"])
print("LOGIN COOKIE:",res["login_cookie_mapping"])
print("BLOCKERS:",",".join(res["blockers"]))
print("RELEASE CANDIDATE FILE:",RESULT)
print("BATCH19_RESULT="+json.dumps({
  k:res[k] for k in ("import_completeness","auth_synthetic",
                     "isolated_app_candidate","login_cookie_mapping",
                     "reporting_release","blockers")},separators=(",",":")))
print("LIVE SERVICE / CLOUD RUN TRAFFIC: UNCHANGED")
print("FINANCIAL ENGINE: RESTRICTED")
print("BATCH 19 COMPLETE")
PY
