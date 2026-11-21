"""Patch only Stage23 derived image, preserving previous app.py content.

Refuses unknown or duplicate PR129 source layouts.
Never changes the running container, host files or database.
"""
import ast
from pathlib import Path

PATH=Path("/app/app.py")
MARKER="SBI_STAGE23_SERVER_SIDE_POLICY_BRIDGE"
source=PATH.read_text()
if MARKER in source:
    raise RuntimeError("STAGE23_ALREADY_PATCHED")
tree=ast.parse(source)
register=[]
install=[]
for n in ast.walk(tree):
    if not isinstance(n,ast.Call): continue
    if isinstance(n.func,ast.Name) and n.func.id=="install_sessions":
        install.append(n)
    if (isinstance(n.func,ast.Attribute) and n.func.attr=="register_blueprint"
        and isinstance(n.func.value,ast.Name) and n.func.value.id=="app"
        and n.args and isinstance(n.args[0],ast.Name)
        and n.args[0].id=="pg_reporting_blueprint"):
        register.append(n)

if len(install)!=1 or len(register)!=1:
    raise RuntimeError("STAGE23_UNEXPECTED_AUTH_OR_BLUEPRINT_LAYOUT")
if install[0].lineno >= register[0].lineno:
    raise RuntimeError("STAGE23_SESSION_INSTALL_ORDER_INVALID")

node=register[0]
lines=source.splitlines(keepends=True)
indent=lines[node.lineno-1][:len(lines[node.lineno-1])-len(lines[node.lineno-1].lstrip())]
insertion=(
    f"{indent}# {MARKER} (isolated image only)\n"
    f"{indent}from stage23_auth_bridge import authorize_postgres_report\n"
    f"{indent}app.config['SBI_PG_REPORT_AUTH_CHECK'] = authorize_postgres_report\n"
)
lines.insert(node.end_lineno,insertion)
out="".join(lines)
ast.parse(out)
PATH.with_name("app.py.before_stage23").write_text(source)
PATH.write_text(out)
print("STAGE23_BRIDGE_REGISTERED_IN_CANDIDATE=PASS")
print("STAGE23_AUTH_CALLBACK=EXISTING_CAN_VIEW_REPORT_FAIL_CLOSED")
print("REAL_AUTHENTICATED_USER_QA=NOT_PERFORMED")
