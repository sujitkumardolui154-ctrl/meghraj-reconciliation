"""SBI Stage 19: redact-sensitive AST auth policy inspection.

Read-only; never imports PR129 app or evaluates its auth code. Displays masked
branch conditions and call names for the already-running PR129 backend. Does
not print credentials, literal tokens, email addresses, or cookie values.
"""
import ast
import copy
from pathlib import Path

ROOT = Path("/app")
FILES = {
    "app.py": [],
    "dashboard_sessions.py": ["install_sessions", "protect_dashboard", "is_master", "csrf_valid"],
    "readonly_reports_gateway.py": ["_ready", "report_catalog", "source_report_csv"],
    "sbi_report_access.py": [],
}
MAX_BRANCHES = 45

class MaskLiterals(ast.NodeTransformer):
    def visit_Constant(self, node):
        if isinstance(node.value, str):
            value = node.value
            # Route path prefixes are non-secret operational identifiers.
            public_path = value.startswith("/") and len(value) < 90 and all(ch.isprintable() for ch in value)
            return ast.copy_location(ast.Constant(value if public_path else "<REDACTED_STRING>"), node)
        if isinstance(node.value, (bytes, bytearray)):
            return ast.copy_location(ast.Constant("<REDACTED_BYTES>"), node)
        return node

def display_expr(expr):
    return ast.unparse(MaskLiterals().visit(copy.deepcopy(expr)))[:380]

def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return "dynamic"

def function_calls(node):
    return sorted({call_name(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)})

def decorator_names(node):
    return [call_name(d.func if isinstance(d, ast.Call) else d) for d in node.decorator_list]

def examine(node, filename):
    print(f"FUNCTION file={filename} name={node.name} line={node.lineno}")
    print("  DECORATORS=", ",".join(decorator_names(node)))
    print("  CALL_NAMES=", ",".join(function_calls(node)))
    conditional_nodes = [n for n in ast.walk(node) if isinstance(n, (ast.If, ast.IfExp))]
    print("  CONDITIONAL_BRANCHES=", len(conditional_nodes))
    for n in conditional_nodes[:MAX_BRANCHES]:
        print(f"  BRANCH line={n.lineno}: {display_expr(n.test)}")
    if len(conditional_nodes) > MAX_BRANCHES:
        print("  BRANCHES_TRUNCATED=YES")
    print("  RETURN_COUNT=", sum(isinstance(n, ast.Return) for n in ast.walk(node)))

app_ast = None
session_ast = None
report_ast = None
for filename, wanted in FILES.items():
    source = ROOT / filename
    if not source.is_file():
        print(f"FILE={filename} STATUS=MISSING")
        continue
    try:
        tree = ast.parse(source.read_text(), filename=filename)
    except (SyntaxError, UnicodeError):
        print(f"FILE={filename} STATUS=PARSE_ERROR")
        continue
    print(f"FILE={filename} STATUS=AST_OK")
    if filename == "app.py": app_ast = tree
    if filename == "dashboard_sessions.py": session_ast = tree
    if filename == "readonly_reports_gateway.py": report_ast = tree
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for n in functions:
        if n.name in wanted or (filename == "sbi_report_access.py" and any(k in n.name.lower() for k in ("auth", "access", "report", "permit", "allow"))):
            examine(n, filename)

assert app_ast is not None and session_ast is not None and report_ast is not None
app_calls = [n for n in ast.walk(app_ast) if isinstance(n, ast.Call) and call_name(n.func) == "install_sessions"]
session_fns = [n for n in ast.walk(session_ast) if isinstance(n, ast.FunctionDef) and n.name == "protect_dashboard"]
report_fns = {n.name for n in ast.walk(report_ast) if isinstance(n, ast.FunctionDef)}
auth_decorators = decorator_names(session_fns[0]) if session_fns else []
print("SESSION_INSTALL_CALLS=", len(app_calls))
print("GLOBAL_PROTECT_HOOK=", "before_request" in auth_decorators)
print("REPORT_HANDLERS_PRESENT=", {"report_catalog", "source_report_csv"}.issubset(report_fns))
print("AUTH_POLICY_AST_REVIEW=COMPLETE")
print("AUTH_CALLBACK_BINDING=NOT_PERFORMED")
print("AUTHENTICATED_USER_API_TEST=NOT_PERFORMED")
