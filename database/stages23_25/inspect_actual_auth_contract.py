"""Inspect actual PR129 report-policy signature and session g assignments.

Prints no identity values, cookie names/values, passwords, claims or source lines.
Never executes the installed application.
"""
from pathlib import Path
import ast

root=Path("/app")
for fname in ("dashboard_sessions.py","sbi_report_access.py"):
    if not (root/fname).is_file():
        raise SystemExit("SOURCE_MISSING="+fname)
sessions=ast.parse((root/"dashboard_sessions.py").read_text())
access=ast.parse((root/"sbi_report_access.py").read_text())

def function(tree,name):
    found=[x for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==name]
    if len(found)!=1: raise SystemExit("FUNCTION_NOT_UNIQUE="+name)
    return found[0]

policy=function(access,"can_view_report")
names=[a.arg for a in policy.args.posonlyargs+policy.args.args]
names.extend(a.arg for a in policy.args.kwonlyargs)
print("ACTUAL_POLICY_PARAMETERS="+",".join(names))
supported=names in (["user","identity"],["user","identity","change_report"])
print("STAGE23_KNOWN_POLICY_SIGNATURE="+("PASS" if supported else "REVIEW_REQUIRED"))

guard=function(sessions,"protect_dashboard")
decorators=[]
for d in guard.decorator_list:
    f=d.func if isinstance(d,ast.Call) else d
    if isinstance(f,ast.Attribute):decorators.append(f.attr)
    elif isinstance(f,ast.Name):decorators.append(f.id)
print("GLOBAL_BEFORE_REQUEST="+str("before_request" in decorators))

targets=set()
for n in ast.walk(guard):
    if isinstance(n,(ast.Assign,ast.AnnAssign,ast.NamedExpr)):
        elems=n.targets if isinstance(n,ast.Assign) else [n.target]
        for t in elems:
            if isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=="g":
                targets.add(t.attr)
    if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="setattr":
        if len(n.args)>=2 and isinstance(n.args[0],ast.Name) and n.args[0].id=="g" and isinstance(n.args[1],ast.Constant) and isinstance(n.args[1].value,str):
            targets.add(n.args[1].value)
print("SESSION_G_USER_DIRECT_ASSIGN="+str("user" in targets))
print("SESSION_G_IDENTITY_DIRECT_ASSIGN="+str("identity" in targets))
print("SESSION_G_ATTRIBUTES_FOUND="+",".join(sorted(targets)))
compatible=supported and "before_request" in decorators and {"user","identity"}.issubset(targets)
print("STAGE23_AUTOWIRING_CONTEXT="+("STATIC_COMPATIBLE_NOT_E2E_VERIFIED" if compatible else "REQUIRES_REAL_SESSION_MAPPING"))
print("SOURCE_AUTH_CONTRACT_AUDIT=COMPLETE")
