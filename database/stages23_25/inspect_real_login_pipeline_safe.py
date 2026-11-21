"""SBI PR129 — targeted server-side Firebase auth pipeline analysis.

Static AST and already-loaded Flask routes only. Never sends credentials or
tokens, executes a login, prints secret/config values, or copies credentials.
Use inside both the original live PR129 and isolated staging container.
"""
from pathlib import Path
import ast
import hashlib
import importlib.util
import os

ROOT=Path("/app")
FILES=("app.py","dashboard_sessions.py","cloud_auth.py","sbi_report_access.py")
def symbol(expr):
    if isinstance(expr,ast.Name):return expr.id
    if isinstance(expr,ast.Attribute):return symbol(expr.value)+"."+expr.attr
    if isinstance(expr,ast.Call):return symbol(expr.func)+"(...)"
    return type(expr).__name__
def env_references(tree):
    names=set()
    for x in ast.walk(tree):
        if isinstance(x,ast.Call) and x.args:
            target=symbol(x.func)
            if target in ("os.getenv","os.environ.get","environ.get"):
                a=x.args[0]
                if isinstance(a,ast.Constant) and type(a.value)==str:names.add(a.value)
        if isinstance(x,ast.Subscript) and symbol(x.value)=="os.environ":
            a=x.slice
            if isinstance(a,ast.Constant) and type(a.value)==str:names.add(a.value)
    return names

print("=== AUTH PIPELINE SOURCE INVENTORY ===")
for name in FILES:
    path=ROOT/name
    if not path.is_file():
        print("SOURCE="+name+" STATUS=MISSING")
        continue
    raw=path.read_bytes()
    print("SOURCE="+name+" STATUS=PRESENT SHA256="+hashlib.sha256(raw).hexdigest())
    try:
        tree=ast.parse(raw.decode("utf-8"),filename=name)
    except (SyntaxError,UnicodeError):
        print("SOURCE="+name+" AST=ERROR")
        continue
    names=env_references(tree)
    for key in sorted(names):
        if any(t in key.upper() for t in ("FIREBASE","GOOGLE","AUTH","SESSION","SECRET","CRED","PROJECT")):
            print("ENV_REFERENCE_MODULE="+name+" KEY="+key+" PRESENT="+str(bool(os.getenv(key))))
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        if not any(k in node.name.lower() for k in ("auth","firebase","login","session","verify","token","credential","identity")):continue
        calls=sorted({symbol(x.func) for x in ast.walk(node) if isinstance(x,ast.Call)})
        returns=sorted({x.value for n in ast.walk(node) if isinstance(n,ast.Constant) and type(n.value)==int and 400<=n.value<=599 for x in (n,)})
        print("FUNCTION="+name+":"+node.name+" LINE="+str(node.lineno))
        print("FUNCTION_CALLS="+name+":"+node.name+" NAMES="+",".join(calls[:65]))
        print("FUNCTION_HTTP_STATUS_CONSTANTS="+name+":"+node.name+" VALUES="+",".join(map(str,returns)) if returns else
              "FUNCTION_HTTP_STATUS_CONSTANTS="+name+":"+node.name+" VALUES=NONE")
        errors=sorted({symbol(n.type) for n in ast.walk(node) if isinstance(n,ast.ExceptHandler) and n.type is not None})
        if errors:print("FUNCTION_EXCEPTION_HANDLERS="+name+":"+node.name+" TYPES="+",".join(errors))
        strings=tuple(x.value.lower() for x in ast.walk(node)
                      if isinstance(x,ast.Constant) and isinstance(x.value,str))
        for key,needle in (
            ("AUTH_UNAVAILABLE","authentication service unavailable"),
            ("FIREBASE_UNAVAILABLE","firebase"),
            ("CREDENTIAL_REFERENCE","google_application_credentials"),
            ("AUTH_NOT_CONFIGURED","not configured"),
        ):
            if any(needle in x for x in strings):
                print("FUNCTION_ERROR_MARKER="+name+":"+node.name+" MARKER="+key)

for module in ("firebase_admin","firebase_admin.auth","google.auth","google.oauth2","requests"):
    try:available=importlib.util.find_spec(module) is not None
    except (ImportError,ModuleNotFoundError,ValueError):available=False
    print("PYTHON_DEPENDENCY="+module+" AVAILABLE="+str(available))

cred=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
print("GOOGLE_CREDENTIAL_ENV_PRESENT="+str(bool(cred)))
if cred:
    path=Path(cred)
    print("GOOGLE_CREDENTIAL_FILE_EXISTS="+str(path.is_file()))
    print("GOOGLE_CREDENTIAL_FILE_READABLE="+str(path.is_file() and os.access(path,os.R_OK)))
else:
    print("GOOGLE_CREDENTIAL_FILE_EXISTS=NOT_CONFIGURED")
    print("GOOGLE_CREDENTIAL_FILE_READABLE=NOT_CONFIGURED")

try:
    from app import app
    for rule in app.url_map.iter_rules():
        if rule.rule in ("/auth/session","/login","/auth/me"):
            fn=app.view_functions.get(rule.endpoint)
            print("AUTH_ROUTE="+rule.rule+" METHODS="+",".join(sorted(rule.methods & {"GET","POST","PUT","DELETE"}))+
                  " HANDLER="+(fn.__name__ if fn else "MISSING")+
                  " MODULE="+(fn.__module__ if fn else "MISSING"))
except Exception as exc:
    print("AUTH_ROUTE_INSPECTION=ERROR_"+type(exc).__name__)

for name in ("login.js","templates/login.html","login.html"):
    file=ROOT/name
    if not file.is_file():continue
    try:
        src=file.read_text(encoding="utf-8",errors="replace").lower()
    except OSError:
        continue
    print("CLIENT_LOGIN_FILE="+name+" PRESENT=True")
    for feature,phrase in (
        ("FIREBASE_WEB_KEY","firebase_web_api_key"),
        ("FIREBASE_JS_SDK","firebase.auth"),
        ("EMAIL_PASSWORD_API","signInWithEmailAndPassword"),
        ("IDENTITY_TOOLKIT","identitytoolkit"),
        ("AUTH_SESSION_ROUTE","/auth/session"),
        ("UNAVAILABLE_MESSAGE","authentication service unavailable"),
        ("FETCH_CALL","fetch("),
    ):
        print("CLIENT_LOGIN_FEATURE="+name+":"+feature+" PRESENT="+str(phrase.lower() in src))

print("AUTH_LOGIN_PIPELINE_INSPECTION=COMPLETE")
