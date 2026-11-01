#!/usr/bin/env bash
# Batch 16: inspect actual production session/login integration without secrets.
# READ-ONLY. No app import, no source edits, no deployment, no GCP/Firestore writes.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"

python3 - <<'PY'
import ast, json
from pathlib import Path
from datetime import datetime,timezone

root=Path("dashboard_source")
target_files=[
 root/"production_gateway.py",
 root/"dashboard_sessions.py",
 root/"gateway.py",
 root/"dashboard_login_pages.py",
]
missing=[str(p) for p in target_files if not p.is_file()]
if missing:
    print("BATCH16_RESULT="+json.dumps({"decision":"BLOCKED_MISSING_FILES","files":missing,
        "main_dashboard_changed":False,"financial_execution":"RESTRICTED"},separators=(",",":")))
    raise SystemExit(2)

try:
    trees={str(p):ast.parse(p.read_text(encoding="utf-8"),filename=str(p)) for p in target_files}
except (SyntaxError,OSError,UnicodeError) as e:
    print("BATCH16_RESULT="+json.dumps({"decision":"BLOCKED_PARSE_ERROR","type":type(e).__name__,
        "main_dashboard_changed":False},separators=(",",":")))
    raise SystemExit(2)

def attr(x):
    if isinstance(x,ast.Name):return x.id
    if isinstance(x,ast.Attribute):return attr(x.value)+"."+x.attr
    return ""
def safe_const(x):
    return x.value if isinstance(x,ast.Constant) and isinstance(x.value,str) else None
def fn_decorators(fn):
    result=[]
    for d in fn.decorator_list:
        if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute):
            if d.func.attr not in ("route","get","post","before_request"):continue
            route=safe_const(d.args[0]) if d.args else None
            result.append({"type":d.func.attr,"route":route})
        elif isinstance(d,ast.Attribute) and d.attr=="before_request":
            result.append({"type":"before_request","route":None})
    return result

def safe_functions(tree):
    return [n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]

def session_refs(fn):
    reads=set();writes=set();mutators=set()
    for n in ast.walk(fn):
        if isinstance(n,ast.Subscript):
            target=attr(n.value)
            if target in ("session","flask.session","flask_session","client_session"):
                k=safe_const(n.slice)
                if k:
                    (writes if isinstance(n.ctx,ast.Store) else reads).add(k)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):
            target=attr(n.func.value)
            if target in ("session","flask.session","flask_session","client_session"):
                meth=n.func.attr
                if meth in ("get","pop","setdefault") and n.args:
                    k=safe_const(n.args[0])
                    if k:reads.add(k)
                    if k and meth in ("pop","setdefault"): writes.add(k)
                if meth in ("clear","update","pop","setdefault"):mutators.add(meth)
    return {"reads":sorted(reads)[:20],"writes":sorted(writes)[:20],"mutators":sorted(mutators)}

def call_names(fn):
    names=set()
    for n in ast.walk(fn):
        if isinstance(n,ast.Call):
            name=attr(n.func)
            if not name:continue
            tokens=name.lower()
            if any(x in tokens for x in ("verify","token","auth","session","cookie","login",
                                         "role","permission","access","clear","secure","sign","claims")):
                names.add(name)
    return sorted(names)[:45]

def imports(tree):
    found=[]
    for n in tree.body:
        if isinstance(n,ast.Import):
            found += [{"module":a.name,"as":a.asname or a.name} for a in n.names]
        elif isinstance(n,ast.ImportFrom):
            if n.module:
                found += [{"module":n.module,"as":a.asname or a.name,"name":a.name} for a in n.names]
    return found

s_tree=trees[str(root/"dashboard_sessions.py")]
p_tree=trees[str(root/"production_gateway.py")]
g_tree=trees[str(root/"gateway.py")]
sess_fns=safe_functions(s_tree)
login=[n for n in sess_fns if n.name=="session_login"]
logout=[n for n in sess_fns if n.name=="session_logout"]
session_info=[]
for n in login+logout:
    session_info.append({"handler":n.name,"routes":fn_decorators(n),
                         "session":session_refs(n),"security_calls":call_names(n)})
# Track relevant nearby helper names, but do not print source lines or literals.
related_helpers=[{"name":n.name,"session":session_refs(n),"security_calls":call_names(n)}
    for n in sess_fns if n not in login+logout
    and (any(s in n.name.lower() for s in ("session","login","logout","auth","role","permit","user","cookie"))
         or session_refs(n)["reads"] or session_refs(n)["writes"])]
prod_imports=[i for i in imports(p_tree)
    if "dashboard_sessions" in i["module"] or i["module"] in ("gateway","dashboard_source.gateway","flask")]
prod_functions=safe_functions(p_tree)
prod_auth_guards=[{"name":f.name,"routes":fn_decorators(f),"session":session_refs(f),"security_calls":call_names(f)}
    for f in prod_functions
    if any(d["type"]=="before_request" for d in fn_decorators(f))
    or any(s in f.name.lower() for s in ("auth","guard","restrict","session"))]
prod_calls=[]
for n in ast.walk(p_tree):
    if isinstance(n,ast.Call):
        name=attr(n.func)
        if any(x in name.lower() for x in ("register","session","auth","blueprint","login","before_request")):
            prod_calls.append(name)
prod_calls=sorted(set(prod_calls))[:60]
# Find actual WSGI launch entrypoint imports, not private credential values.
app_ctor=[]
for n in p_tree.body:
    if isinstance(n,(ast.Assign,ast.AnnAssign)):
        rhs=n.value
        if isinstance(rhs,ast.Call) and attr(rhs.func).split(".")[-1]=="Flask":
            app_ctor.append("Flask")
# Observe absence of authorization evidence; no automatic release on static names.
decision="EXPLICIT_MAIN_SESSION_AUTH_ADAPTER_REQUIRED"
if not login or not logout:
    decision="MISSING_AUTH_SESSION_ENDPOINT"
elif not prod_auth_guards:
    decision="MAIN_PRODUCTION_REQUEST_GUARD_NOT_PROVEN"
report={
    "time_utc":datetime.now(timezone.utc).isoformat(),
    "decision":decision,
    "app_is_separate":bool(app_ctor),
    "production_imports_relevant":prod_imports[:20],
    "session_routes":session_info,
    "session_helpers":related_helpers[:16],
    "prod_auth_guards":prod_auth_guards[:12],
    "production_registration_calls":prod_calls,
    "production_report_auth_proven":False,
    "report_routes_attached":False,
    "source_modified":False,
    "financial_execution":"RESTRICTED",
}
output=Path("reports/credit_note/batch16_production_session_auth.json")
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
output.chmod(0o600)
print("BATCH16_RESULT="+json.dumps({
 "decision":decision,
 "app_is_separate":report["app_is_separate"],
 "production_imports_relevant":prod_imports[:8],
 "session_routes":session_info[:3],
 "session_helpers":related_helpers[:6],
 "production_registration_calls":prod_calls[:20],
 "prod_auth_guards":prod_auth_guards[:4],
 "report_routes_attached":False,
 "main_dashboard_changed":False,
 "financial_execution":"RESTRICTED",
},separators=(",",":")))
PY
