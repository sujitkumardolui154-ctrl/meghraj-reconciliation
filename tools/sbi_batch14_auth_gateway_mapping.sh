#!/usr/bin/env bash
# Batch 14: pinpoint the active SBI Dashboard Flask gateway and its session contract.
# READ-ONLY: no deployment, no IAM changes, no network report download, no Firestore.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, json, re, subprocess
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

root=Path("dashboard_source")
names=("gateway.py","production_gateway.py")
files=[root/name for name in names]
result={
  "stage":"BATCH14_ACTIVE_GATEWAY_MAPPING",
  "time_utc":datetime.now(timezone.utc).isoformat(),
  "decision":"DO_NOT_ATTACH_YET",
  "report_module_present":(root/"sbi_credit_report_auth.py").is_file(),
  "sources":[],
  "deployment_entrypoint_hints":[],
  "live_revision":"UNVERIFIED",
  "cloud_run_traffic":"UNVERIFIED",
  "logout_route_found":False,
  "auth_callback_verified":False,
  "main_dashboard_changed":False,
  "financial_execution":"RESTRICTED",
}
def is_session(x):
    return (isinstance(x,ast.Name) and x.id=="session") or (
      isinstance(x,ast.Attribute) and x.attr=="session" and
      isinstance(x.value,ast.Name) and x.value.id=="flask")
def key_of(x):
    if isinstance(x,ast.Subscript) and is_session(x.value):
        val=x.slice
        if isinstance(val,ast.Constant) and isinstance(val.value,str):
            return val.value
    return None
def session_info(node):
    read=set(); write=set();clear=False; permanent=False
    for child in ast.walk(node):
        k=key_of(child)
        if k:
            if isinstance(child.ctx,ast.Store):write.add(k)
            else:read.add(k)
        if isinstance(child,ast.Call) and is_session(child.func.value) if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute) else False:
            f=child.func.attr
            if f in ("get","pop","setdefault") and child.args and isinstance(child.args[0],ast.Constant) and isinstance(child.args[0].value,str):
                read.add(child.args[0].value)
                if f in ("pop","setdefault"):write.add(child.args[0].value)
            if f=="clear": clear=True
        if isinstance(child,ast.Attribute) and is_session(child.value) and child.attr=="permanent":
            permanent=True
    return {"reads":sorted(read)[:15],"writes":sorted(write)[:15],
            "clear":clear,"permanent_setting":permanent}
def route_info(fn):
    found=[]
    for deco in fn.decorator_list:
        if isinstance(deco,ast.Call) and isinstance(deco.func,ast.Attribute):
            base=deco.func.value
            if (isinstance(base,ast.Name) and base.id in ("app","router","bp")
                and deco.func.attr in ("route","get","post","before_request")):
                route=deco.args[0].value if deco.args and isinstance(deco.args[0],ast.Constant) and isinstance(deco.args[0].value,str) else ""
                found.append((deco.func.attr,route))
    return found
for file in files:
    if not file.is_file():
        result["sources"].append({"file":str(file),"found":False})
        continue
    try:
        code=file.read_text(encoding="utf-8")
        tree=ast.parse(code,filename=str(file))
    except (UnicodeError,OSError,SyntaxError) as e:
        result["sources"].append({"file":str(file),"found":True,"parse_error":type(e).__name__})
        continue
    routes=[]; functions=[]
    indicators={k:(k.lower() in code.lower()) for k in (
        "SESSION_COOKIE_SECURE","SESSION_COOKIE_HTTPONLY","SESSION_COOKIE_SAMESITE",
        "PERMANENT_SESSION_LIFETIME","flask_login","current_user",
        "check_password_hash","compare_digest","before_request","secret_key")}
    for fn in (n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))):
        refs=session_info(fn)
        for kind,route in route_info(fn):
            if kind=="before_request" or route in ("/","/login","/logout","/dashboard") or route.startswith(("/report","/auth","/api")):
                routes.append({"route":route or "before_request","verb":kind,"handler":fn.name,
                               "session":refs})
                if route=="/logout":result["logout_route_found"]=True
        if any(refs[x] for x in ("reads","writes")) or refs["clear"]:
            functions.append({"function":fn.name,"session":refs})
    result["sources"].append({
        "file":str(file),"found":True,"routes":routes[:22],
        "session_functions":functions[:18],"security_config_present":indicators})
# Inspect only module entrypoint names, never print startup contents or secrets.
for directory in (Path("."),root):
    for name in ("Dockerfile","Procfile","start.sh","entrypoint.sh","cloudbuild.yaml"):
        p=directory/name
        if not p.is_file():continue
        try:s=p.read_text(encoding="utf-8")
        except (OSError,UnicodeError):continue
        matched=[n for n in ("production_gateway","gateway") if re.search(r"(?<![A-Za-z0-9_])"+n+r"(?![A-Za-z0-9_])",s)]
        if matched:
            result["deployment_entrypoint_hints"].append({"file":str(p),"module_names":matched})
# Only a high-level non-secret Cloud Run revision and traffic indicator.
try:
    cmd=["gcloud","run","services","describe","sbi-dashboard","--region=asia-south1",
         "--project=meghraj-reconciliation","--format=json"]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
    if proc.returncode==0:
        service=json.loads(proc.stdout)
        status=service.get("status",{})
        result["live_revision"]=status.get("latestReadyRevisionName","UNVERIFIED")
        traffic=status.get("traffic",[])
        result["cloud_run_traffic"]=[{
            "revision":t.get("revisionName",""),
            "percentage":t.get("percent",0),
            "tag":t.get("tag","")
        } for t in traffic][:8]
        containers=service.get("spec",{}).get("template",{}).get("spec",{}).get("containers",[])
        entry=' '.join(' '.join(map(str,c.get(k,[]))) for c in containers for k in ("command","args"))
        detected=[n for n in ("production_gateway","gateway") if re.search(r"(?<![A-Za-z0-9_])"+n+r"(?![A-Za-z0-9_])",entry)]
        if detected:result["deployment_entrypoint_hints"].append({"file":"Cloud Run command/args","module_names":detected})
except Exception as e:
    result["cloud_run_discovery_error"]=type(e).__name__
sourced={src.get("file","").split("/")[-1]:src for src in result["sources"]}
hints=set(n for h in result["deployment_entrypoint_hints"] for n in h["module_names"])
if hints=={"production_gateway"}:
    result["entrypoint_decision"]="PRODUCTION_GATEWAY_HINT_ONLY"
elif hints=={"gateway"}:
    result["entrypoint_decision"]="GATEWAY_HINT_ONLY"
else:
    result["entrypoint_decision"]="ENTRYPOINT_NOT_UNIQUELY_CONFIRMED"
for src in result["sources"]:
    if not src.get("found"):continue
    for route in src.get("routes",[]):
        if route["route"] in ("/login","before_request") and route["session"]["writes"]:
            result.setdefault("session_write_candidates",[]).append({
                "source":src["file"],"handler":route["handler"],
                "keys":route["session"]["writes"]})
        if route["route"]=="before_request":
            result.setdefault("before_request_guards",[]).append({
                "source":src["file"],"handler":route["handler"],
                "keys_read":route["session"]["reads"]})
if not result["report_module_present"]:
    result["decision"]="BLOCKED_CREDIT_MODULE_MISSING"
elif result["entrypoint_decision"]=="ENTRYPOINT_NOT_UNIQUELY_CONFIRMED":
    result["decision"]="ENTRYPOINT_REVIEW_REQUIRED"
elif not result.get("session_write_candidates"):
    result["decision"]="LOGIN_SESSION_CONTRACT_REVIEW_REQUIRED"
else:
    result["decision"]="VERIFY_LOGIN_ROLE_GUARD_AND_LOGOUT_BEFORE_ATTACH"
out=Path("reports/credit_note/batch14_active_gateway_contract.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out.chmod(0o600)
small={
 "decision":result["decision"],
 "entrypoint":result["entrypoint_decision"],
 "session_write_candidates":result.get("session_write_candidates",[])[:5],
 "before_request_guards":result.get("before_request_guards",[])[:4],
 "login_routes":[{"source":src["file"],"handler":rt["handler"],
    "reads":rt["session"]["reads"],"writes":rt["session"]["writes"]}
    for src in result["sources"] for rt in src.get("routes",[])
    if rt["route"]=="/login"][:6],
 "logout_found":result["logout_route_found"],
 "live_revision":result["live_revision"],
 "main_dashboard_changed":False,
 "financial_execution":"RESTRICTED"
}
print("BATCH14_RESULT="+json.dumps(small,separators=(",",":"),ensure_ascii=False))
PY
