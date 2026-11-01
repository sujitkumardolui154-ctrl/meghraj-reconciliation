#!/usr/bin/env bash
# Batch 12 / Stage 1: compact read-only dashboard authentication and route audit.
# No deploy, no Firestore queries, no secrets, and no traffic changes.
set -euo pipefail
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, json, re, subprocess
from pathlib import Path
from collections import Counter
root=Path("dashboard_source")
print("===== BATCH 12 DASHBOARD AUTH CONTRACT =====")
print("DASHBOARD SOURCE FOUND:",root.is_dir())
if not root.is_dir():
    raise SystemExit("STOP: dashboard_source missing; no modifications")
files=sorted(x for x in root.rglob("*.py") if len(x.relative_to(root).parts)<=4)
print("PYTHON SOURCE FILES:",len(files))
webfiles=sorted(x for x in root.rglob("*") if x.is_file() and x.suffix.lower() in (".html",".js",".css") and len(x.relative_to(root).parts)<=4)
print("HTML/JS/CSS FILES:",len(webfiles))
for p in webfiles[:20]:
    print("UI FILE:",p.relative_to(root))
routes=[]
markers=["login_required","before_request","session","logout","PERMANENT_SESSION_LIFETIME","SESSION_COOKIE_SECURE","SESSION_COOKIE_HTTPONLY","SESSION_COOKIE_SAMESITE","csrf","authorize","auth_required","jwt","OIDC","verify_id_token"]
counts=Counter()
parse_errors=0
for p in files[:100]:
    try:
        source=p.read_text(encoding="utf-8")
    except (UnicodeError,OSError):
        print("UNREADABLE SOURCE FILE:",p.relative_to(root));continue
    for marker in markers:
        if re.search(re.escape(marker),source,re.I):
            counts[marker]+=1
    try:
        tree=ast.parse(source)
    except SyntaxError:
        parse_errors+=1;print("PYTHON SYNTAX NOT VERIFIED:",p.relative_to(root));continue
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco,ast.Call) or not isinstance(deco.func,ast.Attribute):
                continue
            if deco.func.attr not in ("route","get","post","put","delete") or not deco.args:
                continue
            arg=deco.args[0]
            if isinstance(arg,ast.Constant) and isinstance(arg.value,str):
                route=arg.value
                if len(route)>160:continue
                decorators=[]
                for other in node.decorator_list:
                    if isinstance(other,ast.Name):decorators.append(other.id)
                    elif isinstance(other,ast.Call) and isinstance(other.func,ast.Name):decorators.append(other.func.id)
                routes.append((str(p.relative_to(root)),node.name,route,deco.func.attr,",".join(decorators[:4])))
print("PYTHON PARSE ERRORS:",parse_errors)
print("DISCOVERED WEB ROUTES:",len(routes))
for item in routes[:70]:
    print("ROUTE:",json.dumps(item,ensure_ascii=False))
for marker in markers:
    print("SECURITY INDICATOR:",marker,"FILE COUNT",counts[marker])
print("SECURITY INDICATORS ARE NOT PROOF OF ENFORCEMENT")
for service in ("sbi-dashboard","sbi-supervisor-backend","sbi-chat-report-stage-v1"):
    args=["gcloud","run","services","describe",service,"--region=asia-south1","--project=meghraj-reconciliation","--format=json"]
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=35)
        if p.returncode!=0:
            print("CLOUD RUN:",service,"STATUS UNVERIFIED")
            continue
        d=json.loads(p.stdout)
        metadata=d.get("metadata",{})
        spec=d.get("spec",{})
        status=d.get("status",{})
        traffic=status.get("traffic",[])
        print("CLOUD RUN:",service,
              "READY_REVISION:",status.get("latestReadyRevisionName","UNKNOWN"),
              "TRAFFIC:",json.dumps([{k:t.get(k) for k in ("revisionName","tag","percent") if k in t} for t in traffic]),
              "INGRESS:",metadata.get("annotations",{}).get("run.googleapis.com/ingress","UNSPECIFIED"))
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:
        print("CLOUD RUN:",service,"STATUS UNVERIFIED",type(e).__name__)
print("AUTHENTICATION STATUS: NOT YET VERIFIED")
print("FINANCIAL EXECUTION: RESTRICTED")
print("NO DEPLOYMENT OR DATABASE CHANGES")
print("BATCH 12 SOURCE AUDIT COMPLETE")
PY
