#!/usr/bin/env bash
# SBI Batch 15: resolve production/gateway app identity and login-session contract.
# Read-only: does not import app modules, deploy, mutate IAM or access invoice data.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

ROOT=Path("dashboard_source")
PROD=ROOT/"production_gateway.py"
BASE=ROOT/"gateway.py"
MODULE=ROOT/"sbi_credit_report_auth.py"
for f in (PROD,BASE,MODULE):
    if not f.is_file():
        raise SystemExit("BATCH15_RESULT="+json.dumps({"decision":"BLOCKED_MISSING_SOURCE","file":str(f),
            "main_dashboard_changed":False,"financial_execution":"RESTRICTED"}))

def parse(p):
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

try:
    prod=parse(PROD)
    base=parse(BASE)
except (OSError,UnicodeError,SyntaxError) as err:
    raise SystemExit("BATCH15_RESULT="+json.dumps({"decision":"BLOCKED_SOURCE_PARSE",
        "error_type":type(err).__name__,"main_dashboard_changed":False}))

def flat_expr(node):
    if isinstance(node,ast.Name): return node.id
    if isinstance(node,ast.Attribute):
        return flat_expr(node.value)+"."+node.attr
    return ""

def app_symbols(tree):
    imports=[]; objects=[]; rebinds=[]
    for node in tree.body:
        if isinstance(node,ast.ImportFrom):
            imports.append({"module":node.module or "",
                "names":[{"name":a.name,"as":a.asname or a.name} for a in node.names]})
        if isinstance(node,ast.Import):
            imports.extend({"module":a.name,"names":[{"name":"*","as":a.asname or a.name}]} for a in node.names)
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            rhs=node.value
            for target in targets:
                if isinstance(target,ast.Name) and target.id=="app":
                    callee=flat_expr(rhs.func) if isinstance(rhs,ast.Call) else ""
                    if callee.split(".")[-1]=="Flask": objects.append("local_flask")
                    elif isinstance(rhs,ast.Name):rebinds.append(rhs.id)
                    elif isinstance(rhs,ast.Attribute):rebinds.append(flat_expr(rhs))
                    else:objects.append(type(rhs).__name__)
    return imports,objects,rebinds

prod_imports,prod_apps,prod_aliases=app_symbols(prod)
base_imports,base_apps,base_aliases=app_symbols(base)
direct_shared=any(x["module"] in ("gateway","dashboard_source.gateway") and
                  any(n["name"]=="app" and n["as"]=="app" for n in x["names"])
                  for x in prod_imports)
import_gateway=any(x["module"] in ("gateway","dashboard_source.gateway") for x in prod_imports)
prod_app_assign=bool(prod_apps or prod_aliases)
if direct_shared and not prod_app_assign:
    app_identity="SHARED_GATEWAY_APP_STATIC"
elif "local_flask" in prod_apps:
    app_identity="PRODUCTION_GATEWAY_SEPARATE_FLASK"
elif import_gateway or prod_aliases:
    app_identity="INDIRECT_APP_REFERENCE_REVIEW"
else:
    app_identity="APP_OBJECT_OR_IMPORT_NOT_RESOLVED"

def const_str(node):
    return node.value if isinstance(node,ast.Constant) and isinstance(node.value,str) else None

def routes_for(tree,file):
    out=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco,ast.Call) or not isinstance(deco.func,ast.Attribute):
                continue
            if deco.func.attr not in ("route","get","post","put","delete"):
                continue
            if flat_expr(deco.func.value).split(".")[-1] not in ("app","bp","blueprint","router"):
                continue
            path=const_str(deco.args[0]) if deco.args else None
            if path is None:continue
            methods=[const_str(a) for k in deco.keywords if k.arg=="methods"
                for a in (k.value.elts if isinstance(k.value,(ast.List,ast.Tuple)) else [])]
            out.append({"file":str(file),"function":node.name,"route":path[:100],
                        "methods":[x for x in methods if x]})
    return out

def session_access(tree,file):
    out=[]
    for fn in ast.walk(tree):
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        keys_read=set(); keys_written=set(); methods=set()
        for node in ast.walk(fn):
            if isinstance(node,ast.Subscript) and flat_expr(node.value) in ("session","flask.session"):
                key=const_str(node.slice)
                if key:
                    (keys_written if isinstance(node.ctx,ast.Store) else keys_read).add(key)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and flat_expr(node.func.value) in ("session","flask.session"):
                method=node.func.attr
                if method in ("get","pop","setdefault") and node.args:
                    key=const_str(node.args[0])
                    if key:
                        keys_read.add(key)
                        if method in ("pop","setdefault"):keys_written.add(key)
                if method in ("clear","update","pop","setdefault"):
                    methods.add(method)
                if method=="update" and node.args and isinstance(node.args[0],ast.Dict):
                    for key in node.args[0].keys:
                        label=const_str(key)
                        if label:keys_written.add(label)
        if keys_read or keys_written or methods:
            out.append({"file":str(file),"function":fn.name,
                        "reads":sorted(keys_read)[:15],
                        "writes":sorted(keys_written)[:15],
                        "mutates_via":sorted(methods)})
    return out

routes=routes_for(prod,PROD)+routes_for(base,BASE)
sessions=session_access(prod,PROD)+session_access(base,BASE)
# Find only route names and session write keys in other dashboard Python modules.
other_sources=[]
for p in sorted(ROOT.rglob("*.py")):
    if p in (PROD,BASE,MODULE) or len(p.relative_to(ROOT).parts)>4:continue
    try:t=parse(p)
    except (SyntaxError,UnicodeError,OSError):continue
    r=routes_for(t,p)
    s=session_access(t,p)
    if r or s:
        other_sources.append({"file":str(p),"routes":r[:30],"session":s[:25]})
    routes.extend(r)
    sessions.extend(s)
login_routes=[r for r in routes if "login" in r["route"].lower() or "signin" in r["route"].lower()
              or "login" in r["function"].lower()]
logout_routes=[r for r in routes if "logout" in r["route"].lower() or "signout" in r["route"].lower()]
auth_readers=[s for s in sessions if "authenticated" in s["reads"]]
auth_writers=[s for s in sessions if "authenticated" in s["writes"]]
guards=[]
for source,tree in ((BASE,base),(PROD,prod)):
    for fn in ast.walk(tree):
        if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):
            if any(isinstance(d,ast.Attribute) and flat_expr(d) in ("app.before_request","bp.before_request")
                   for d in fn.decorator_list):
                guards.append({"file":str(source),"function":fn.name})
snapshot= {
    "utc":datetime.now(timezone.utc).isoformat(),
    "app_identity":app_identity,
    "prod_imports":[x for x in prod_imports if x["module"] in ("gateway","dashboard_source.gateway")],
    "prod_local_app_objects":prod_apps,
    "prod_app_aliases":prod_aliases,
    "gateway_local_app_objects":base_apps,
    "login_routes":login_routes[:12],
    "logout_routes":logout_routes[:12],
    "authenticated_readers":auth_readers[:12],
    "authenticated_writers":auth_writers[:12],
    "before_request_guards":guards[:10],
    "other_source_file_count":len(other_sources),
    "live_main_dashboard_modified":False,
    "report_routes_attached":False,
    "financial_execution":"RESTRICTED"
}
# Explicitly do not infer report-reading permission from an ordinary logged-in session.
if app_identity=="SHARED_GATEWAY_APP_STATIC" and auth_writers and auth_readers:
    decision="VERIFY_REPORT_ROLE_PERMISSION_BEFORE_ATTACHING"
elif app_identity=="PRODUCTION_GATEWAY_SEPARATE_FLASK":
    decision="PRODUCTION_AUTH_GUARD_SEPARATE_REVIEW"
else:
    decision="AUTHENTICATION_SOURCE_REVIEW_REQUIRED"
snapshot["decision"]=decision
out=Path("reports/credit_note/batch15_gateway_identity.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
out.chmod(0o600)
summary={
    "decision":decision,
    "app_identity":app_identity,
    "session_authenticated_readers":auth_readers[:4],
    "session_authenticated_writers":auth_writers[:4],
    "login_routes":login_routes[:5],
    "logout_routes":logout_routes[:5],
    "before_request_guards":guards[:5],
    "report_permission_verified":False,
    "main_dashboard_changed":False,
    "financial_execution":"RESTRICTED"
}
print("BATCH15_RESULT="+json.dumps(summary,ensure_ascii=False,separators=(",",":")))
PY
