"""Safe Firebase/login configuration audit for PR129.

Reads selected deployment source files. Never imports app modules or logs
secret values, cookies, keys, tokens, identities or entire environment.
Only reports configuration-key presence and login-message code locations.
"""
import ast, os, re
from pathlib import Path

FILES = [
    Path("/app/cloud_auth.py"), Path("/app/dashboard_sessions.py"),
    Path("/app/app.py"), Path("/app/login.html"),
    Path("/app/templates/login.html"), Path("/app/templates/auth/login.html"),
    Path("/app/production_gateway.py"),
]
AUTH_MARKERS=("FIREBASE", "AUTH", "SESSION", "GOOGLE", "LOGIN", "COOKIE", "CSRF")
RELEVANT_KEYS={
    "FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_PROJECT_ID",
    "FIREBASE_APP_ID", "FIREBASE_WEB_API_KEY", "FIREBASE_WEB_AUTH_DOMAIN",
    "FIREBASE_WEB_PROJECT_ID", "FIREBASE_WEB_APP_ID",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT_ID",
    "SESSION_COOKIE_SECURE", "SECRET_KEY", "FLASK_SECRET_KEY"
}
expected=set()
def keystr(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value,str) else None

for path in FILES:
    if not path.is_file():
        print("SOURCE_FILE="+path.name+" STATUS=MISSING")
        continue
    print("SOURCE_FILE="+path.name+" STATUS=PRESENT")
    try:
        source=path.read_text(errors="replace")
    except Exception:
        print("SOURCE_READ="+path.name+" STATUS=ERROR")
        continue
    phrase="Login setup is not complete"
    if phrase.lower() in source.lower():
        print("LOGIN_SETUP_MESSAGE_LOCATION="+path.name)
    if path.suffix!=".py":
        # HTML/JS may access public Firebase web config from template
        # instead of the server's own environment; never print its content.
        print("LOGIN_SOURCE_HAS_FIREBASE_REFERENCE="+str("firebase" in source.lower()))
        continue
    try:
        tree=ast.parse(source,filename=str(path))
    except SyntaxError:
        print("SOURCE_AST="+path.name+" STATUS=PARSE_ERROR")
        continue
    for n in ast.walk(tree):
        key=None
        if isinstance(n,ast.Call) and n.args:
            f=n.func
            if isinstance(f,ast.Attribute) and f.attr in ("get", "getenv"):
                if isinstance(f.value,ast.Name) and f.value.id=="os" and f.attr=="getenv":
                    key=keystr(n.args[0])
                elif (isinstance(f.value,ast.Attribute) and f.value.attr=="environ"
                    and isinstance(f.value.value,ast.Name) and f.value.value.id=="os"):
                    key=keystr(n.args[0])
        elif isinstance(n,ast.Subscript):
            f=n.value
            if (isinstance(f,ast.Attribute) and f.attr=="environ"
                and isinstance(f.value,ast.Name) and f.value.id=="os"):
                key=keystr(n.slice)
        if key and (any(t in key.upper() for t in AUTH_MARKERS)):
            expected.add(key)

# Restrict additional key discovery to authentication-specific names and do
# not print arbitrary environment names from the host.
for key in sorted(expected | RELEVANT_KEYS):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,100}",key):
        continue
    state="PRESENT" if os.environ.get(key) else "ABSENT"
    print("AUTH_ENV_KEY="+key+" STATE="+state)
print("AUTH_EXPECTED_KEY_COUNT="+str(len(expected)))
print("AUTH_CONFIG_INVENTORY=COMPLETE")
