#!/usr/bin/env python3
"""Fail-closed public-repository content check. Does not assert absence of all secrets."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(
    ["git", "ls-files", "-z"], cwd=ROOT
).decode("utf-8", errors="replace").split("\0")
bad_suffix = (".xlsx", ".xls", ".csv", ".sqlite", ".db", ".pem", ".p12", ".key", ".env", ".zip", ".jsonl")
bad_names = ("credentials", "service-account", "firebase-adminsdk", "firestore", "invoice_details", "payment_received", "private-audits")
patterns = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}"),
]
issues = []
for rel in files:
    if not rel:
        continue
    p = ROOT / rel
    lower = rel.lower()
    if lower.endswith(bad_suffix) or any(x in lower for x in bad_names):
        issues.append((rel, "blocked filename or extension"))
        continue
    if not p.is_file() or p.stat().st_size > 2_000_000:
        continue
    data = p.read_bytes()
    for pattern in patterns:
        if pattern.search(data):
            issues.append((rel, "potential secret; review locally"))
            break
for rel, why in issues:
    print(f"BLOCKED: {rel}: {why}")
print(f"TRACKED_FILES={len([x for x in files if x])}")
print(f"ISSUES={len(issues)}")
print("FINANCIAL_DATABASE_WRITES=0")
sys.exit(1 if issues else 0)
