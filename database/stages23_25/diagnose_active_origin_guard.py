"""Read-only inspection of the *active* PR129 Flask origin guard.

Run in a transient, networkless container from the derived private-only
candidate image. No request credentials, no environment values, no
authentication bypass, no filesystem changes, no public deployment.
"""
from flask import request
import hashlib
import inspect
from pathlib import Path

ORIGIN="http://127.0.0.1:18080"
FOREIGN="https://untrusted.example.invalid"
SOURCE=Path("/app/dashboard_sessions.py")
print("=== PRIVATE STAGING ACTIVE ORIGIN-GUARD DIAGNOSTIC ===")
print("SOURCE_PATCH_MARKER_PRESENT="+str("SBI_PRIVATE_TUNNEL_ORIGIN_18080_ONLY" in SOURCE.read_text()))
print("SOURCE_EXACT_ORIGIN_LITERAL_PRESENT="+str(ORIGIN in SOURCE.read_text()))
print("SOURCE_SHA256="+hashlib.sha256(SOURCE.read_bytes()).hexdigest())

try:
    from app import app
except Exception as exc:
    print("FLASK_APP_IMPORT=FAIL_"+type(exc).__name__)
    raise

matching=[]
for bp,functions in app.before_request_funcs.items():
    for fn in functions:
        if getattr(fn,"__name__",None)=="protect_dashboard":
            matching.append((bp,fn))
print("REGISTERED_PROTECT_DASHBOARD_HOOKS="+str(len(matching)))
if not matching:
    raise RuntimeError("No registered PR129 origin guard")

for bp,fn in matching:
    scope=inspect.getclosurevars(fn)
    print("GUARD_BLUEPRINT_SCOPE="+("GLOBAL" if bp is None else "OTHER"))
    print("GUARD_MODULE="+str(fn.__module__))
    print("GUARD_CODE_FILE_BASENAME="+Path(fn.__code__.co_filename).name)
    print("GUARD_HAS_ORIGIN_FREEVAR="+str("ORIGINS" in fn.__code__.co_freevars))
    print("GUARD_HAS_ORIGIN_GLOBAL_NAME="+str("ORIGINS" in fn.__code__.co_names))
    sources=(
        ("NONLOCAL",scope.nonlocals),
        ("GLOBAL",scope.globals),
        ("BUILTIN",scope.builtins),
    )
    found=False
    for name,values in sources:
        if "ORIGINS" in values:
            found=True
            origins=values["ORIGINS"]
            print("ACTIVE_ALLOWLIST_SCOPE="+name)
            print("ACTIVE_ALLOWLIST_TYPE="+type(origins).__name__)
            try:
                print("ACTIVE_ALLOWLIST_HAS_EXACT_TUNNEL_ORIGIN="+str(ORIGIN in origins))
                print("ACTIVE_ALLOWLIST_HAS_FOREIGN_ORIGIN="+str(FOREIGN in origins))
            except (TypeError,ValueError):
                print("ACTIVE_ALLOWLIST_MEMBERSHIP_CHECK=ERROR")
    if not found: print("ACTIVE_ALLOWLIST_BINDING=UNRESOLVED")
    if "ORIGINS" in scope.unbound:
        print("GUARD_ORIGIN_VARIABLE=UNBOUND")

seen=[]
def capture_request_metadata():
    seen.append((
        request.method,
        request.headers.get("Origin"),
        request.host,
        request.path,
    ))
# Temporary instrumentation is inserted ONLY into this process. It does
# not replace, disable, or alter the original guard's authorization decision.
app.before_request_funcs.setdefault(None,[]).insert(0,capture_request_metadata)
client=app.test_client()
for label,origin in (
    ("EXACT_TUNNEL",ORIGIN),
    ("FOREIGN_ORIGIN",FOREIGN),
    ("NO_ORIGIN",None),
):
    headers={"Origin":origin} if origin is not None else {}
    r=client.post("/__origin_diagnostic_no_real_route__",headers=headers)
    observed=seen[-1] if seen else (None,None,None,None)
    text=r.get_data(as_text=True).lower()
    print("PROBE_"+label+"_HTTP="+str(r.status_code))
    print("PROBE_"+label+"_REQUEST_METHOD_MATCH="+str(observed[0]=="POST"))
    print("PROBE_"+label+"_ORIGIN_HEADER_MATCH="+str(observed[1]==origin))
    print("PROBE_"+label+"_HOST_IS_DEFAULT_TEST_HOST="+str(observed[2]=="localhost"))
    print("PROBE_"+label+"_UNTRUSTED_MESSAGE="+str("untrusted request origin" in text))
print("ACTIVE_ORIGIN_DIAGNOSTIC=COMPLETE")
print("CANDIDATE_ONLY=TRUE")
print("LIVE_PR129_UNCHANGED=TRUE")
