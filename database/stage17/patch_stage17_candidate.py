"""Patch ONLY the derived Stage 17 Docker image's /app/app.py.

Requires the six known PR129 blueprints and session initialization in
the expected order; refuses unknown layouts instead of guessing.
"""
import ast
from pathlib import Path

TARGET = Path("/app/app.py")
MARKER = "SBI_STAGE17_PG_REPORTING_INSERTED"

source = TARGET.read_text()
if MARKER in source:
    raise RuntimeError("STAGE17_ALREADY_PATCHED: refusing duplicate registration")

tree = ast.parse(source, filename=str(TARGET))
session_calls = []
registrations = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    f = node.func
    if isinstance(f, ast.Name) and f.id == "install_sessions":
        session_calls.append(node)
    elif isinstance(f, ast.Attribute) and f.attr == "register_blueprint":
        if node.args and isinstance(node.args[0], ast.Name):
            registrations.append((node.args[0].id, node))

required = {
    "tower",
    "workspace",
    "payment_evidence",
    "reconciliation_readiness",
    "readonly_reports",
    "bulk_report",
}
present = {name for name, _ in registrations}
if not required.issubset(present):
    raise RuntimeError(f"STAGE17_BLUEPRINTS_MISMATCH: missing {sorted(required - present)}")
targets = [node for name, node in registrations if name == "readonly_reports"]
if len(targets) != 1 or len(session_calls) != 1:
    raise RuntimeError("STAGE17_AUTH_LAYOUT_UNSUPPORTED")

target = targets[0]
if not session_calls[0].lineno < target.lineno:
    raise RuntimeError("STAGE17_AUTH_HOOK_ORDER_UNVERIFIED")
if not isinstance(target.func, ast.Attribute):
    raise RuntimeError("STAGE17_REGISTER_FUNCTION_INVALID")
if not isinstance(target.func.value, ast.Name) or target.func.value.id != "app":
    raise RuntimeError("STAGE17_FLASK_APP_VARIABLE_UNVERIFIED")

lines = source.splitlines(keepends=True)
end = target.end_lineno
indent = lines[target.lineno - 1][:len(lines[target.lineno - 1]) - len(lines[target.lineno - 1].lstrip())]
insertion = (
    f"{indent}# {MARKER}: isolated candidate image only\n"
    f"{indent}from pg_reporting_blueprint import pg_reporting_blueprint\n"
    f"{indent}app.register_blueprint(pg_reporting_blueprint)\n"
)
lines.insert(end, insertion)
out = "".join(lines)
ast.parse(out, filename=str(TARGET))
TARGET.with_name("app.py.before_stage17").write_text(source)
TARGET.write_text(out)
print("STAGE17_CANDIDATE_PATCH=PASS")
print("REGISTERED_NEW_BLUEPRINT=sbi_postgres_reporting_stage17")
print("AUTHORIZATION_DEFAULT=DENY")
