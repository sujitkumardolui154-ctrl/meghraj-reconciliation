"""Stage 19–22 combined authorization integration map.

Read-only AST discovery in deployed PR129. Never executes application source,
does not print source statements, constant strings, cookies, passwords,
claim values or personal data. Requires verified server-side can_view_report.
"""
from pathlib import Path
import ast

ROOT=Path("/app")
FILES=[
    "app.py",
    "dashboard_sessions.py",
    "sbi_report_access.py",
    "readonly_reports_gateway.py",
    "bulk_reports.py",
    "cloud_auth.py",
]
trees={}
def simple(node):
    if isinstance(node,ast.Name):
        return node.id
    if isinstance(node,ast.Attribute):
        prefix=simple(node.value)
        return (prefix+"." if prefix else "")+node.attr
    if isinstance(node,ast.Call):
        return simple(node.func)+"(...)"
    if isinstance(node,ast.Subscript):
        return simple(node.value)+"[...]"
    if isinstance(node,ast.Constant):
        return "REDACTED_LITERAL"
    return type(node).__name__

def decorators(n):
    return [simple(d.func if isinstance(d,ast.Call) else d) for d in n.decorator_list]

def fmtargs(n):
    args=n.args
    a=[x.arg for x in args.posonlyargs + args.args]
    if args.vararg: a.append("*"+args.vararg.arg)
    a.extend(x.arg for x in args.kwonlyargs)
    if args.kwarg: a.append("**"+args.kwarg.arg)
    return ",".join(a)

for f in FILES:
    p=ROOT/f
    if not p.is_file():
        print("FILE=",f,"STATUS=MISSING")
        continue
    try:
        trees[f]=ast.parse(p.read_text(),filename=f)
        print("FILE=",f,"STATUS=PARSE_OK")
    except (UnicodeError,SyntaxError):
        print("FILE=",f,"STATUS=PARSE_ERROR")

necessary=["app.py","dashboard_sessions.py","sbi_report_access.py","readonly_reports_gateway.py"]
if any(x not in trees for x in necessary):
    raise SystemExit("AUTH_SOURCE_STRUCTURE=REQUIRES_REVIEW")

names={}
for f,tree in trees.items():
    names[f]={n.name:n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

print("=== REQUIRED EXISTING AUTH POLICY ===")
policy=names["sbi_report_access.py"].get("can_view_report")
if policy is None:
    raise SystemExit("CAN_VIEW_REPORT_POLICY=MISSING")
print("POLICY=can_view_report")
print("POLICY_PARAMETERS=",fmtargs(policy))
print("POLICY_CONDITIONAL_COUNT=",sum(isinstance(n,(ast.If,ast.IfExp)) for n in ast.walk(policy)))
print("POLICY_RETURN_COUNT=",sum(isinstance(n,ast.Return) for n in ast.walk(policy)))
print("POLICY_CALL_NAMES=",",".join(sorted({simple(n.func) for n in ast.walk(policy) if isinstance(n,ast.Call)})))

print("=== AUTH POLICY CALLS ACROSS PR129 MODULES ===")
callsites=0
for f,tree in trees.items():
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and simple(n.func).split(".")[-1]=="can_view_report":
            callsites+=1
            print("CALLSITE_FILE=",f,"LINE=",n.lineno,"FUNC=",simple(n.func))
            print("CALLSITE_POSITIONAL=",",".join(simple(a) for a in n.args))
            print("CALLSITE_KEYWORDS=",",".join(x.arg or "DYNAMIC" for x in n.keywords))
print("EXISTING_POLICY_CALLSITE_COUNT=",callsites)

print("=== FLASK SESSION AND REPORTING GATEWAY ===")
install=names["dashboard_sessions.py"].get("install_sessions")
guard=names["dashboard_sessions.py"].get("protect_dashboard")
if install is None or guard is None:
    raise SystemExit("SESSION_HOOK=REQUIRES_REVIEW")
print("SESSION_INSTALL_PARAMETERS=",fmtargs(install))
print("SESSION_GUARD_DECORATORS=",",".join(decorators(guard)))
print("SESSION_GUARD_CALL_NAMES=",",".join(sorted({simple(x.func) for x in ast.walk(guard) if isinstance(x,ast.Call)})))
for x in ast.walk(guard):
    if isinstance(x,ast.Assign):
        lhs=[simple(t) for t in x.targets]
        if any(k in a.lower() for a in lhs for k in ("identity","user","claims","g.")):
            print("SESSION_ASSIGNMENT_TARGETS=",",".join(lhs),"LINE=",x.lineno)
for fn in ("report_catalog","source_report_csv"):
    node=names["readonly_reports_gateway.py"].get(fn)
    if node is None:
        raise SystemExit("REPORT_HANDLER_NOT_FOUND="+fn)
    print("REPORT_HANDLER=",fn,"PARAMETERS=",fmtargs(node))
    print("REPORT_HANDLER_DECORATORS=",",".join(decorators(node)))
    print("REPORT_HANDLER_CALL_NAMES=",",".join(sorted({simple(x.func) for x in ast.walk(node) if isinstance(x,ast.Call)})))

apps=trees["app.py"]
installed=[n.lineno for n in ast.walk(apps) if isinstance(n,ast.Call) and simple(n.func)=="install_sessions"]
registered=[(simple(n.args[0]),n.lineno) for n in ast.walk(apps) if isinstance(n,ast.Call) and simple(n.func).endswith(".register_blueprint") and n.args]
print("INSTALL_SESSIONS_LINES=",",".join(map(str,installed)))
print("BLUEPRINT_REGISTRATIONS=",",".join(x+":"+str(y) for x,y in registered))
if len(installed)!=1 or not registered or min(y for _,y in registered)<=installed[0]:
    raise SystemExit("SESSION_INSTALL_ORDER=REQUIRES_REVIEW")
if "readonly_reports" not in {x for x,_ in registered}:
    raise SystemExit("READONLY_REPORT_BLUEPRINT=REQUIRES_REVIEW")
print("SESSION_INSTALL_ORDER=PASS")

print("=== AUTH INTEGRATION GATES ===")
print("EXISTING_AUTH_POLICY_IDENTIFIED=PASS")
print("AUTH_SOURCE_MAPPING=COMPLETE")
print("NEW_PG_AUTH_CALLBACK=NOT_WIRED")
print("AUTHENTICATED_USER_ENDPOINT_QA=NOT_EXECUTED")
print("LIVE_PR129_RELEASE_GATE=BLOCKED")
