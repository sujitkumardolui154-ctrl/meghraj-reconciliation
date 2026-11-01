import ast
import inspect
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault(
    "FIREBASE_WEB_API_KEY",
    "TEST_ONLY_NOT_A_REAL_FIREBASE_KEY"
)

from production_gateway import app
from firebase_admin import auth

report = {
    "step": 175,
    "mode": "local_synthetic_testing",
    "csrf_validator_found": False,
    "csrf_references": [],
    "csrf_bootstrap_status": None,
    "session_status": None,
    "firebase_verification_reached": False,
    "result": "BLOCKED"
}

print("=== STEP 175: AUTHENTICATION DIAGNOSTIC ===")

# Inspect actual registered session handler.
rule = next(
    (r for r in app.url_map.iter_rules()
     if r.rule == "/auth/session"),
    None
)

if rule is None:
    raise RuntimeError("Session endpoint not registered")

handler = inspect.unwrap(app.view_functions[rule.endpoint])
closure = inspect.getclosurevars(handler)

dependencies = {
    **closure.globals,
    **closure.nonlocals
}

validator = dependencies.get("csrf_valid")

if callable(validator):
    report["csrf_validator_found"] = True

    try:
        source = inspect.getsource(validator)
        tree = ast.parse(inspect.cleandoc(source))

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                value = node.value
                if isinstance(value, str) and any(
                    term in value.lower()
                    for term in (
                        "csrf", "xsrf", "origin",
                        "referer", "header", "cookie"
                    )
                ):
                    report["csrf_references"].append(value[:80])
    except (OSError, TypeError, SyntaxError):
        report["inspection_note"] = (
            "Validator source not available through inspection"
        )

# Exercise CSRF and Firebase boundary locally.
client = app.test_client()

with app.test_request_context(base_url="https://localhost"):
    pass

csrf_response = client.get(
    "/auth/csrf",
    base_url="https://localhost"
)

report["csrf_bootstrap_status"] = csrf_response.status_code

csrf_body = csrf_response.get_json(silent=True) or {}
token = csrf_body.get("csrf_token")

if isinstance(token, str) and token:
    # Do not mock or bypass the CSRF validator.
    with patch.object(
        auth,
        "verify_id_token",
        side_effect=ValueError("QA_FIREBASE_BOUNDARY")
    ) as verifier:

        response = client.post(
            "/auth/session",
            base_url="https://localhost",
            json={"idToken": "QA_SYNTHETIC_TOKEN"},
            headers={
                "X-CSRF-Token": token,
                "Origin": "https://localhost",
                "Referer": "https://localhost/login"
            }
        )

        report["session_status"] = response.status_code
        report["firebase_verification_reached"] = verifier.called

        if verifier.called:
            report["result"] = "CSRF_GATE_PASSED"
else:
    report["inspection_note"] = "CSRF token missing or invalid"

output = Path("reports/step175_auth_diagnostic.json")
output.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

# Never print the CSRF token itself.
print("CSRF VALIDATOR FOUND:", report["csrf_validator_found"])
print("CSRF IDENTIFIERS:", report["csrf_references"])
print("CSRF BOOTSTRAP HTTP:", report["csrf_bootstrap_status"])
print("SESSION HTTP:", report["session_status"])
print(
    "FIREBASE BOUNDARY REACHED:",
    report["firebase_verification_reached"]
)
print("RESULT:", report["result"])
print("REPORT:", output.resolve())
print("STEP 175 COMPLETE")
