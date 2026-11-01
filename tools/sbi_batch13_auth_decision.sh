#!/usr/bin/env bash
# Batch 13: safely prepare main dashboard auth binding candidate.
# Never attach to active dashboard, deploy Cloud Run, or read/write Firestore.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, json, sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

root = Path("dashboard_source")
feature = root / "sbi_credit_report_auth.py"
receipt_file = Path("reports/credit_note/batch12_integration_prepared.json")
if not feature.is_file():
    raise SystemExit('BATCH13_RESULT={"decision":"STOP","reason":"Batch12 module missing","main_dashboard_changed":false}')
if not receipt_file.is_file():
    raise SystemExit('BATCH13_RESULT={"decision":"STOP","reason":"Batch12 receipt missing","main_dashboard_changed":false}')
feature_source = feature.read_text(encoding="utf-8")
if "SBI_AUTHORIZED_CREDIT_REPORT_V1" not in feature_source:
    raise SystemExit('BATCH13_RESULT={"decision":"STOP","reason":"Unknown feature module","main_dashboard_changed":false}')
receipt=json.loads(receipt_file.read_text(encoding="utf-8"))
main_apps=[]
routes=[]
security=Counter()
auth_functions=[]
for p in sorted(root.rglob("*.py")):
    if p==feature or len(p.relative_to(root).parts)>4:
        continue
    try:
        code=p.read_text(encoding="utf-8")
        tree=ast.parse(code,filename=str(p))
    except (OSError,UnicodeError,SyntaxError):
        continue
    file_name=str(p)
    for n in ast.walk(tree):
        if isinstance(n,(ast.Assign,ast.AnnAssign)):
            val=n.value
            if isinstance(val,ast.Call):
                call=val.func
                is_flask=isinstance(call,ast.Name) and call.id=="Flask"
                is_flask=is_flask or (isinstance(call,ast.Attribute) and call.attr=="Flask")
                if is_flask:
                    targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                    for target in targets:
                        if isinstance(target,ast.Name):
                            main_apps.append({"file":file_name,"variable":target.id})
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            if n.name in ("can_view_credit_reports","sbi_credit_report_authorize",
                          "authorize_credit_note_report","can_read_reports"):
                auth_functions.append({"file":file_name,"name":n.name,
                                       "line":n.lineno})
            for deco in n.decorator_list:
                if isinstance(deco,ast.Name) and deco.id in ("login_required","auth_required","admin_required"):
                    security[deco.id]+=1
                if not (isinstance(deco,ast.Call) and isinstance(deco.func,ast.Attribute)
                        and deco.args and isinstance(deco.args[0],ast.Constant)
                        and isinstance(deco.args[0].value,str)):
                    continue
                if deco.func.attr in ("route","get","post"):
                    route=deco.args[0].value
                    if route in ("/","/login","/logout","/dashboard") or route.startswith("/reports"):
                        routes.append({"route":route,"file":file_name,"handler":n.name})
    for term in ("flask_login","current_user","session","SESSION_COOKIE_SECURE",
                 "SESSION_COOKIE_HTTPONLY","SESSION_COOKIE_SAMESITE",
                 "PERMANENT_SESSION_LIFETIME"):
        if term.lower() in code.lower():
            security[term]+=1
main_apps=list({(item["file"],item["variable"]):item for item in main_apps}.values())
main_apps.sort(key=lambda i:(i["file"],i["variable"]))
routes.sort(key=lambda i:(i["route"],i["file"]))
contract = {
  "timestamp_utc":datetime.now(timezone.utc).isoformat(),
  "main_app_candidates":main_apps[:15],
  "routes":routes[:30],
  "security_indicators":dict(security),
  "potential_auth_callback_names":auth_functions[:20],
  "batch12_receipt_available":True,
  "snapshot_verified_in_prior_batch":True,
  "main_auth_verified":False,
  "app_source_modified":False,
  "cloud_run_modified":False,
  "financial_execution":"RESTRICTED",
}
if len(main_apps)!=1:
    contract["decision"]="BLOCKED_SOURCE_APP_AMBIGUOUS"
elif not auth_functions:
    contract["decision"]="BLOCKED_EXPLICIT_AUTH_CALLBACK_NOT_IDENTIFIED"
else:
    contract["decision"]="AUTH_CALLBACK_CANDIDATE_REQUIRES_PERMISSION_VERIFICATION"
path=Path("reports/credit_note/batch13_auth_binding_decision.json")
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(contract,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
path.chmod(0o600)
print("AUTH CONTRACT CANDIDATES:",len(main_apps))
print("POSSIBLE ROLE-AUTH FUNCTIONS:",len(auth_functions))
print("RELEVANT EXISTING ROUTES:",len(routes))
print("DECISION FILE:",path)
print("BATCH13_RESULT="+json.dumps({
    "decision":contract["decision"],
    "main_apps":main_apps[:2],
    "auth_candidates":auth_functions[:3],
    "login_route":any(x["route"]=="/login" for x in routes),
    "logout_route":any(x["route"]=="/logout" for x in routes),
    "security_indicators":dict(security),
    "main_dashboard_changed":False,
    "financial_execution":"RESTRICTED",
},separators=(",",":"),ensure_ascii=False))
PY
