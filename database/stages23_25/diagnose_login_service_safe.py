"""Read-only, no-credential diagnostic of SBI private Flask/Firebase login availability.

Prints only source paths/line numbers, selected environment variable names and
presence, Flask route patterns with dynamic route arguments redacted, and
network status codes/error types. No config values or credentials are printed.
Never sends a username, password, cookie or Firebase API key.
"""
from pathlib import Path
import ast
import os
import re
import socket
import sys
import urllib.error
import urllib.request

ROOT=Path("/app")
KEY_PREDICATE=re.compile(r"(FIREBASE|GOOGLE|CLOUD|AUTH|SESSION|CREDENTIAL|PROJECT|API_KEY|ORIGIN|SECRET|FLASK)",re.I)
SKIP={"node_modules","__pycache__",".git",".venv","site-packages"}
PHRASES=("authentication service unavailable","login setup is not complete","untrusted request origin")
FILES_SCANNED=0
matches=[]
for p in ROOT.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".py",".html",".js",".jinja2",".mjs"):
        continue
    if any(k in p.parts for k in SKIP):
        continue
    FILES_SCANNED+=1
    if FILES_SCANNED>1400: break
    try:
        if p.stat().st_size>600000: continue
        s=p.read_text(encoding="utf-8",errors="replace")
    except OSError: continue
    for line,txt in enumerate(s.splitlines(),1):
        if any(phrase in txt.lower() for phrase in PHRASES):
            matches.append((str(p.relative_to(ROOT)),line))
    if p.suffix==".py" and p.name in ("cloud_auth.py","dashboard_sessions.py","app.py","sbi_report_access.py"):
        try: tree=ast.parse(s)
        except SyntaxError: continue
        functions=[]
        for n in ast.walk(tree):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(
                token in n.name.lower() for token in ("login","firebase","auth","session","identity","origin")
            ):
                functions.append(n.name)
        print("AUTH_SOURCE_MODULE="+p.name+" PRESENT=YES")
        print("AUTH_RELATED_FUNCTIONS="+p.name+" NAMES="+",".join(sorted(set(functions))[:25]))

print("SOURCE_FILES_SCANNED="+str(FILES_SCANNED))
print("AUTH_ERROR_MESSAGE_SOURCE_LOCATIONS="+str(len(matches)))
for path,line in matches[:25]:
    print("AUTH_ERROR_MESSAGE_SOURCE="+path+" LINE="+str(line))

# Absence/presence only, no environment values.
for key in sorted(k for k in os.environ if KEY_PREDICATE.search(k))[:75]:
    print("AUTH_ENV_NAME="+key+" PRESENT="+("YES" if os.environ.get(key) else "NO"))

for key in ("FIREBASE_WEB_API_KEY","GOOGLE_APPLICATION_CREDENTIALS",
            "FIREBASE_PROJECT_ID","FIREBASE_AUTH_DOMAIN",
            "FLASK_SECRET_KEY","SECRET_KEY"):
    if key not in os.environ:
        print("AUTH_ENV_NAME="+key+" PRESENT=NO")

try:
    from app import app
    routes=sorted({re.sub(r"<[^>]*>","<parameter>",str(rule.rule)) for rule in app.url_map.iter_rules()
                   if any(k in rule.rule.lower() for k in ("login","auth","session","firebase"))})
    print("AUTH_FLASK_ROUTE_COUNT="+str(len(routes)))
    for path in routes[:35]:
        print("AUTH_FLASK_ROUTE="+path)
except Exception as exc:
    print("AUTH_FLASK_ROUTE_INSPECTION=ERROR_"+type(exc).__name__)

# Public provider DNS + TLS, without secrets, auth POSTs, or credential attempts.
# A reachable HTTP 400/403/404 also confirms TLS+network transport succeeded.
for host in ("identitytoolkit.googleapis.com","securetoken.googleapis.com"):
    try:
        socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        print("AUTH_DNS_HOST="+host+" STATUS=RESOLVED")
    except Exception as exc:
        print("AUTH_DNS_HOST="+host+" STATUS=ERROR_"+type(exc).__name__)
        continue
    try:
        req=urllib.request.Request("https://"+host+"/",method="HEAD")
        with urllib.request.urlopen(req,timeout=5) as response:
            print("AUTH_TLS_HOST="+host+" STATUS=HTTP_"+str(response.status))
    except urllib.error.HTTPError as exc:
        print("AUTH_TLS_HOST="+host+" STATUS=HTTP_"+str(exc.code))
    except Exception as exc:
        print("AUTH_TLS_HOST="+host+" STATUS=ERROR_"+type(exc).__name__)

print("AUTH_DIAGNOSTIC_IN_CONTAINER=COMPLETE")
