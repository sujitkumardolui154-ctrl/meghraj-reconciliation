"""PR129 trusted-origin diagnosis, source-only & without private values.

Use inside live and staging containers, executed as Python source from stdin.
Never imports app modules, emits tokens/config values, or writes any file.
"""
from pathlib import Path
import ast
import os
import re

ROOT=Path("/app")
PHRASES=("untrusted request origin","untrusted origin","trusted origin","allowed origin","origin not allowed","origin is not trusted")
KEY_PATTERN=re.compile(r"(ORIGIN|HOST|CORS|CSRF|FIREBASE_AUTH_DOMAIN|FIREBASE_WEB_AUTH_DOMAIN|PUBLIC_URL|BASE_URL|SESSION_COOKIE)",re.I)
ENV_VALUE_PATTERN=re.compile(r"(SECRET|TOKEN|PASS|PRIVATE|CREDENTIAL|KEY)",re.I)
MAX_FILES=1500
count=0
exact=[]
related=[]

def fullname(n):
    if isinstance(n,ast.Name):return n.id
    if isinstance(n,ast.Attribute):return fullname(n.value)+"."+n.attr
    return type(n).__name__

def envkey(n):
    if not isinstance(n,ast.Call) or not n.args:
        return None
    call=fullname(n.func)
    if call in ("os.getenv","os.environ.get","environ.get") and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str):
        return n.args[0].value
    return None

for p in ROOT.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in (".py",".html",".js",".jinja2",".mjs"):
        continue
    if len(p.parts)>9 or any(x in p.parts for x in ("node_modules",".git",".venv","site-packages","__pycache__")):
        continue
    count+=1
    if count>MAX_FILES:break
    try:
        if p.stat().st_size>700000:continue
        src=p.read_text(errors="replace")
    except (OSError, UnicodeError):continue
    hits=[(n,s.strip()) for n,s in enumerate(src.splitlines(),1) if any(t in s.lower() for t in PHRASES)]
    if not hits and not (p.suffix==".py" and KEY_PATTERN.search(src)):continue
    rel=str(p.relative_to(ROOT))
    for num,line in hits[:6]:
        if "untrusted request origin" in line.lower() or "untrusted origin" in line.lower():
            exact.append((rel,num))
        else:related.append((rel,num))
    if p.suffix!=".py":continue
    try:tree=ast.parse(src)
    except SyntaxError:continue
    funcs=[]
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            if any(isinstance(x,ast.Constant) and isinstance(x.value,str) and any(t in x.value.lower() for t in PHRASES) for x in ast.walk(n)):
                funcs.append(n.name)
    if funcs:
        print("ORIGIN_POLICY_FUNCTIONS file="+rel+" names="+",".join(sorted(set(funcs))[:12]))
    keys=sorted({key for n in ast.walk(tree) if (key:=envkey(n)) and KEY_PATTERN.search(key)})
    if keys:
        print("SOURCE_ORIGIN_ENV_NAMES file="+rel+" keys="+",".join(keys[:40]))

print("SOURCE_FILES_SCANNED="+str(count))
print("EXACT_ORIGIN_ERROR_LOCATIONS="+str(len(exact)))
for file,num in exact[:15]:print("EXACT_ORIGIN_ERROR_SOURCE="+file+" line="+str(num))
for file,num in related[:15]:print("RELATED_ORIGIN_SOURCE="+file+" line="+str(num))

# The staging request is an HTTP tunnel. Presence below never prints values.
interesting=sorted(k for k in os.environ if KEY_PATTERN.search(k))
for key in interesting[:75]:
    value=os.environ.get(key) or ""
    if ENV_VALUE_PATTERN.search(key):
        print("ORIGIN_ENV_NAME="+key+" PRESENT="+str(bool(value)))
    else:
        print(
            "ORIGIN_ENV_NAME="+key+
            " PRESENT="+str(bool(value))+
            " HAS_TUNNEL_HTTP_ORIGIN="+str("http://127.0.0.1:18080" in value)+
            " HAS_LOCALHOST="+str("localhost" in value.lower())
        )
print("ORIGIN_SOURCE_INVENTORY=COMPLETE")
