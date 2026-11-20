#!/usr/bin/env python3
"""Read-only, redacted AWS reconciliation architecture discovery.

Run from the AWS host as a Docker-readable user; no container or finance writes.
Never prints raw gateway config, code contents, environment or credentials.
"""
import ast
import json
import re
import subprocess
from pathlib import Path

TARGETS = (
    "aws_lightsail-caddy-1",
    "sbi-login-workspace-stage",
    "sbi-login-v150-stage",
    "sbi-control-tower-board-v2-stage",
    "sbi-backend-readonly-stage",
    "sbi-backend-readonly-ingress-stage",
    "aws_lightsail-sbi-preview-1",
    "sbi-agent-stage",
)
AUDIT_CODE_CONTAINERS = (
    "sbi-login-workspace-stage",
    "sbi-login-v150-stage",
    "sbi-control-tower-board-v2-stage",
    "sbi-backend-readonly-stage",
    "aws_lightsail-sbi-preview-1",
    "sbi-agent-stage",
)
FINANCE = re.compile(r"reconcil|allocat|credit.?note|payment|invoice|gst|tax|tds|settle|suspense|sol.?match", re.I)
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./*{}<>:\-]+\Z")


def command(*args, timeout=20):
    try:
        r = subprocess.run(("docker",) + args, capture_output=True, text=True,
                           check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def classify_caddy(caddy_text, names):
    """Return metadata only, never the original Caddyfile lines or arbitrary tokens."""
    result = []
    for index, source in enumerate(caddy_text.splitlines(), 1):
        line = source.strip()
        if not line or line.startswith("#"):
            continue
        route = re.match(r"^(handle_path|handle|route)\s+(/\S+)", line)
        if route:
            scope = route.group(2)
            result.append({"line": index, "kind": "route_scope",
                           "path": scope if SAFE_PATH.fullmatch(scope) else "WITHHELD"})
        if re.search(r"\breverse_proxy\b", line):
            matches = [name for name in names if name in line]
            result.append({"line": index, "kind": "reverse_proxy",
                           "known_container_targets": matches,
                           "other_target_present": not bool(matches),
                           "https_token_present": bool(re.search(r"https://", line))})
        if re.match(r"^import\s", line):
            result.append({"line": index, "kind": "caddy_import", "scope": "UNINSPECTED"})
    return result


# Runs in the container. It does not import application modules or print source.
# Only normalized file paths/hashes and function/route declarations are emitted.
IN_CONTAINER_SCAN = r'''
import ast, hashlib, json, re
from pathlib import Path
finance = re.compile(r"reconcil|allocat|credit.?note|payment|invoice|gst|tax|tds|settle|suspense|sol.?match", re.I)
route_re = re.compile(r"/(?:[A-Za-z0-9_./*{}<>:\-]+)\Z")
root = Path('/app')
files = sorted(p for p in root.rglob('*.py')
               if len(p.relative_to(root).parts) <= 3
               and '__pycache__' not in p.parts)[:100] if root.is_dir() else []
results = []
for path in files:
    try:
        data=path.read_bytes()
        tree=ast.parse(data, filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        continue
    symbols=sorted(set(n.name for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and finance.search(n.name)))
    routes=[]
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in n.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ('route','get','post','put','patch','delete','api_route'):
                if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                    route=dec.args[0].value
                    if route_re.fullmatch(route) and finance.search(route):
                        routes.append(route)
    if symbols or routes:
        results.append({'file':str(path),'sha256':hashlib.sha256(data).hexdigest(),
                        'finance_named_symbols':symbols[:60], 'finance_named_routes':sorted(set(routes))[:30]})
print(json.dumps({'python_files_inspected':len(files),'candidate_files':results[:60]}))
'''


def main():
    raw = command("ps", "-a", "--format", "{{.Names}}")
    if raw is None:
        print("DOCKER_ACCESS=UNAVAILABLE; No audit executed")
        raise SystemExit(2)
    existing = set(raw.splitlines())
    print("D-016_COMBINED_READONLY_AUDIT=START")
    for name in TARGETS:
        if name not in existing:
            print("CONTAINER", name, "NOT_FOUND")
            continue
        inspected = command("inspect", name)
        if inspected is None:
            print("CONTAINER", name, "INSPECT_FAILED")
            continue
        info = json.loads(inspected)[0]
        state = info.get("State", {}).get("Status", "UNKNOWN")
        image = info.get("Image", "UNKNOWN")
        networks = sorted((info.get("NetworkSettings", {}).get("Networks") or {}).keys())
        ports = info.get("NetworkSettings", {}).get("Ports") or {}
        bindings = [f"{port}->{b.get('HostIp')}:{b.get('HostPort')}"
                    for port, values in ports.items() for b in (values or [])]
        print("CONTAINER", json.dumps({"name": name, "state": state,
              "image_sha": image, "networks": networks, "published_ports": bindings,
              "secret_mount_present": any(m.get("Destination", "").startswith("/run/secrets/")
                                          for m in info.get("Mounts", []))}))
    if "aws_lightsail-caddy-1" in existing:
        caddy = command("exec", "aws_lightsail-caddy-1", "cat", "/etc/caddy/Caddyfile")
        if caddy is None:
            print("GATEWAY_ROUTE_METADATA=UNAVAILABLE")
        else:
            print("GATEWAY_ROUTE_METADATA", json.dumps(classify_caddy(caddy, TARGETS)))
    for name in AUDIT_CODE_CONTAINERS:
        if name not in existing:
            continue
        scanned = command("exec", name, "python", "-c", IN_CONTAINER_SCAN, timeout=25)
        if scanned is None:
            print("APP_CODE_SYMBOLS", name, "UNAVAILABLE")
        else:
            try:
                parsed = json.loads(scanned)
                print("APP_CODE_SYMBOLS", name, json.dumps(parsed, separators=(',', ':')))
            except ValueError:
                print("APP_CODE_SYMBOLS", name, "UNPARSEABLE")
    print("FINANCIAL_DATABASE_QUERIES=0")
    print("FINANCIAL_WRITES=0")
    print("CONTAINER_MUTATIONS=0")
    print("COMBINED_FINANCIAL_ENGINE_VERIFIED=NO")
    print("D-016_COMBINED_READONLY_AUDIT=COMPLETE")


if __name__ == '__main__':
    main()
