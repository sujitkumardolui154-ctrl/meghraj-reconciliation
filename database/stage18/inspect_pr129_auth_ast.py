"""Stage 18: source-only PR129 authorization-chain inventory.

Run inside existing PR129 container with python3 -B.
AST only; imports, session handlers and Flask routes are NOT executed.
Prints only function/call/decorator names and count metrics, never source text,
tokens, emails, cookies or secret values.
"""
import ast
from pathlib import Path

ROOT = Path("/app")
TARGETS = [
    "app.py",
    "dashboard_sessions.py",
    "readonly_reports_gateway.py",
    "sbi_report_access.py",
    "cloud_auth.py",
]

def calls(node):
    result = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            f = child.func
            if isinstance(f, ast.Name):
                result.add(f.id)
            elif isinstance(f, ast.Attribute):
                result.add(f.attr)
    return sorted(result)

def methods(node):
    result = []
    for decorator in node.decorator_list:
        f = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(f, ast.Name):
            result.append(f.id)
        elif isinstance(f, ast.Attribute):
            result.append(f.attr)
    return result

parsed = {}
for filename in TARGETS:
    p = ROOT / filename
    if not p.is_file():
        print("FILE", filename, "MISSING")
        continue
    try:
        parsed[filename] = ast.parse(p.read_text(), filename=filename)
        print("FILE", filename, "AST_OK")
    except (SyntaxError, UnicodeError):
        print("FILE", filename, "AST_FAILED")

assert "app.py" in parsed
assert "dashboard_sessions.py" in parsed
assert "readonly_reports_gateway.py" in parsed

app_tree = parsed["app.py"]
calls_app = calls(app_tree)
print("SESSION_INSTALL_CALLED=", "install_sessions" in calls_app)

regs = set()
for node in ast.walk(app_tree):
    if not isinstance(node, ast.Call):
        continue
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "register_blueprint" and node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Name):
            regs.add(arg.id)
print("REGISTERED_BLUEPRINT_VARIABLES=", ",".join(sorted(regs)))
expected = {"tower", "workspace", "payment_evidence", "reconciliation_readiness", "readonly_reports", "bulk_report"}
print("EXPECTED_SIX_BLUEPRINTS=", expected.issubset(regs))

for fname, sought in [
    ("dashboard_sessions.py", ("install_sessions", "protect_dashboard", "csrf_valid", "is_master")),
    ("readonly_reports_gateway.py", ("_ready", "report_catalog", "source_report_csv")),
    ("sbi_report_access.py", ("require_report_access", "authorized_report_access")),
]:
    tree = parsed.get(fname)
    if tree is None:
        continue
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in sought:
        node = functions.get(name)
        if node is None:
            print(f"FUNCTION {fname}:{name}=NOT_FOUND")
            continue
        print(f"FUNCTION {fname}:{name}=FOUND line={node.lineno}")
        print(f" DECORATOR_NAMES={','.join(methods(node))}")
        print(f" CALLED_FUNCTION_NAMES={','.join(calls(node))}")
        print(f" CONDITIONAL_COUNT={sum(isinstance(n,(ast.If,ast.IfExp)) for n in ast.walk(node))}")
        print(f" RETURN_COUNT={sum(isinstance(n,ast.Return) for n in ast.walk(node))}")

tree = parsed["readonly_reports_gateway.py"]
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in n.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            fn = d.func
            if not isinstance(fn, ast.Attribute) or fn.attr not in ("route", "get", "post"):
                continue
            if not d.args:
                continue
            try:
                path = ast.literal_eval(d.args[0])
            except (ValueError, TypeError):
                path = "dynamic"
            if isinstance(path, str) and path.startswith("/api/reporting/"):
                print("REPORT_ROUTE=", path, " HANDLER=", n.name)

print("STAGE18_AUTH_SOURCE_INSPECTION=COMPLETE")
print("AUTH_CALLBACK_MAPPING=REQUIRES_CODE_REVIEW")
