"""Patch the existing PR129 trusted-origin allowlist for isolated testing only.

Adds exactly http://127.0.0.1:18080 to the ORIGINS expression referenced
by protect_dashboard. Does not change the guard, authentication, or CSRF.
Fails closed on unknown source topology or duplicated origin bindings.
NEVER run inside the live PR129 container: apply only in a derived Docker image.
"""
from pathlib import Path
import ast
import hashlib

SOURCE=Path("/app/dashboard_sessions.py")
ORIGIN="http://127.0.0.1:18080"
MARK="SBI_PRIVATE_TUNNEL_ORIGIN_18080_STR_V2"
src=SOURCE.read_text(encoding="utf-8")
if MARK in src:
    raise SystemExit("STAGE_ORIGIN_PATCH_ALREADY_APPLIED")

root=ast.parse(src,filename=str(SOURCE))
guards=[]
for n in ast.walk(root):
    if not isinstance(n,ast.Compare):continue
    if not (len(n.ops)==1 and isinstance(n.ops[0],ast.NotIn)
            and len(n.comparators)==1
            and isinstance(n.comparators[0],ast.Name)
            and n.comparators[0].id=="ORIGINS"):continue
    left=n.left
    if not isinstance(left,ast.Call) or not isinstance(left.func,ast.Attribute) or left.func.attr!="get":continue
    obj=left.func.value
    if not (isinstance(obj,ast.Attribute) and obj.attr=="headers"
            and isinstance(obj.value,ast.Name) and obj.value.id=="request"):continue
    if len(left.args)!=1 or not isinstance(left.args[0],ast.Constant) or left.args[0].value!="Origin":continue
    guards.append(n)
if len(guards)!=1:
    raise SystemExit("STAGE_ORIGIN_PATCH_GUARD_STRUCTURE=REVIEW_REQUIRED count="+str(len(guards)))

# Accept one conventional assignment, either module-local or inside the
# enclosing install_sessions closure. Reject control-flow assignments.
bindings=[]
for n in ast.walk(root):
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=="ORIGINS":
        bindings.append(n.value)
    elif isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=="ORIGINS" and n.value:
        bindings.append(n.value)
if len(bindings)!=1:
    raise SystemExit("STAGE_ORIGIN_PATCH_ALLOWLIST_BINDING=REVIEW_REQUIRED count="+str(len(bindings)))

value=bindings[0]
if not (isinstance(value,(ast.Set,ast.List,ast.Tuple,ast.Call,ast.BinOp,ast.SetComp,ast.ListComp))):
    raise SystemExit("STAGE_ORIGIN_PATCH_UNKNOWN_ALLOWLIST_TYPE="+type(value).__name__)

lines=src.splitlines(keepends=True)
start=sum(len(x.encode("utf-8")) for x in lines[:value.lineno-1])+value.col_offset
end=sum(len(x.encode("utf-8")) for x in lines[:value.end_lineno-1])+value.end_col_offset
raw=src.encode("utf-8")
segment=raw[start:end]
if not segment:
    raise SystemExit("STAGE_ORIGIN_PATCH_EMPTY_EXPRESSION")
# Flask request.headers.get("Origin") returns str, never bytes.
# Serialize the allowed origin as a Python *str* literal.
replacement=b"(set("+segment+b") | {"+repr(ORIGIN).encode("ascii")+b"})"
out=raw[:start]+replacement+raw[end:]
# Marker is a module-level constant; no behavior added by marker itself.
out+=("\n"+MARK+" = True\n").encode()
updated=out.decode("utf-8")
parsed=ast.parse(updated,filename=str(SOURCE))
if not any(isinstance(n,ast.Constant) and type(n.value) is str and n.value==ORIGIN for n in ast.walk(parsed)):
    raise SystemExit("STAGE_ORIGIN_PATCH_NO_STRING_LITERAL")
if any(isinstance(n,ast.Constant) and isinstance(n.value,bytes) and n.value==ORIGIN.encode("ascii") for n in ast.walk(parsed)):
    raise SystemExit("STAGE_ORIGIN_PATCH_BYTES_LITERAL_DETECTED")
if updated.count(ORIGIN)!=1:raise SystemExit("STAGE_ORIGIN_PATCH_UNEXPECTED_ORIGIN_COUNT")
SOURCE.write_text(updated,encoding="utf-8")
print("STAGE_ORIGIN_ALLOWLIST_PATCH=PASS")
print("STAGE_ORIGIN_ALLOWED_EXACT="+ORIGIN)
print("STAGE_ORIGIN_EXISTING_GUARD_UNCHANGED=PASS")
print("STAGE_ORIGIN_VALUE_TYPE=PYTHON_STR")
print("STAGE_ORIGIN_SOURCE_SHA256="+hashlib.sha256(out).hexdigest())
