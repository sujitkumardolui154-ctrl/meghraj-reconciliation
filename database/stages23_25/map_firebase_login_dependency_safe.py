"""SBI Stage 24 - read-only authentication service dependency map.

No credential contents, private paths, environment values, cookies,
account identifiers, tokens or source statements are printed.
Does not import the application or call Firebase authentication.
"""
import ast
import os
from pathlib import Path

ROOT=Path("/app")
PRIMARY=("cloud_auth.py","dashboard_sessions.py","app.py","sbi_report_access.py")
NEEDLES=(
  "authentication service unavailable",
  "GOOGLE_APPLICATION_CREDENTIALS",
  "firebase_admin",
  "google.auth",
  "verify_id_token",
  "verify_firebase_token",
  "identitytoolkit",
  "securetoken",
)
def func_name(expr):
    if isinstance(expr,ast.Name):return expr.id
    if isinstance(expr,ast.Attribute):
        return func_name(expr.value)+"."+expr.attr
    return type(expr).__name__

def inspect_function(tree,source,label):
    for fn in ast.walk(tree):
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        token=fn.name.lower()
        relevant=any(t in token for t in ("firebase","auth","login","session","token","identity","credential"))
        raw=ast.get_source_segment(source,fn) or ""
        if not relevant and not any(t in raw.lower() for t in ("google_application_credentials","verify_id_token","firebase_admin")):continue
        calls=sorted({func_name(n.func) for n in ast.walk(fn) if isinstance(n,ast.Call)})
        print("AUTH_FUNC_MODULE="+label+" NAME="+fn.name+" LINE="+str(fn.lineno))
        print("AUTH_FUNC_CALL_NAMES="+label+"."+fn.name+" CALLS="+",".join(calls[:32]))

for name in PRIMARY:
    p=ROOT/name
    if not p.is_file():
        print("AUTH_SOURCE="+name+" STATUS=MISSING")
        continue
    print("AUTH_SOURCE="+name+" STATUS=PRESENT")
    try:
        text=p.read_text(encoding="utf-8",errors="replace")
        tree=ast.parse(text)
    except Exception as exc:
        print("AUTH_SOURCE="+name+" STATUS=PARSE_"+type(exc).__name__)
        continue
    imports=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imports.update(a.name for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module:imports.add(n.module)
    print("AUTH_DEP_IMPORTS="+name+" MODULES="+",".join(sorted(i for i in imports if any(k in i for k in ("firebase","google","auth","requests","urllib")))[:32]))
    inspect_function(tree,text,name)
    for line,raw in enumerate(text.splitlines(),1):
        if "authentication service unavailable" in raw.lower():
            print("AUTH_UNAVAILABLE_TEXT_SOURCE="+name+" LINE="+str(line))
        if "GOOGLE_APPLICATION_CREDENTIALS" in raw:
            print("AUTH_CREDENTIAL_VARIABLE_REFERENCE="+name+" LINE="+str(line))

# Find client-side source of the exact message, without dumping JS or HTML.
scan=0
for p in ROOT.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".js",".mjs",".html",".jinja2",".py"):continue
    if any(part in ("node_modules",".git","__pycache__","site-packages",".venv") for part in p.parts):continue
    scan+=1
    if scan>1400:break
    if p.name in PRIMARY:continue
    try:
        if p.stat().st_size>600000:continue
        code=p.read_text(encoding="utf-8",errors="replace")
    except Exception:continue
    for lineno,line in enumerate(code.splitlines(),1):
        if "authentication service unavailable" in line.lower():
            print("AUTH_UNAVAILABLE_TEXT_SOURCE="+str(p.relative_to(ROOT))+" LINE="+str(lineno))
print("AUTH_CLIENT_FILES_SCANNED="+str(scan))

key=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
print("GOOGLE_APPLICATION_CREDENTIALS_DEFINED="+str(bool(key)))
if key:
    f=Path(key)
    print("GOOGLE_APPLICATION_CREDENTIALS_FILE_EXISTS="+str(f.is_file()))
    print("GOOGLE_APPLICATION_CREDENTIALS_FILE_READABLE="+str(f.is_file() and os.access(str(f),os.R_OK)))
else:
    print("GOOGLE_APPLICATION_CREDENTIALS_FILE_EXISTS=NOT_CONFIGURED")
    print("GOOGLE_APPLICATION_CREDENTIALS_FILE_READABLE=NOT_CONFIGURED")

print("AUTH_DEPENDENCY_MAPPING=COMPLETE")
