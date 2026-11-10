#!/usr/bin/env python3
"""Read-only, metadata-only comparison inventory for SBI return to Google Cloud.

Run in the AWS application checkout or a recovered source checkout:
  python3 tools/sbi_return_to_gcloud_inventory.py --root .
Do not upload source code, credentials, financial records or internal env files.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ALLOW_ROOTS = ("backend_source", "dashboard_source", "source", "tests",
               "agent", "deployment", "migration", "staging", "tools", ".github")
ALLOW_FILES = ("README.md", "render.yaml")
SUFFIXES = {".py", ".js", ".css", ".html", ".json", ".yaml", ".yml",
            ".toml", ".txt", ".md", ".sh"}
BLOCK_PARTS = {".git", ".env", "node_modules", "__pycache__", "secrets",
               "credentials", "backups", "exports", "private", "data",
               "invoices", "payments", "reports", "evidence", ".venv"}
BLOCK_NAMES = {"service-account.json", "firebase-adminsdk.json",
               ".env", ".env.production"}
MAX_FILE = 2 * 1024 * 1024

def run_git(root, *args):
    p = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, timeout=15)
    return p.stdout.strip() if p.returncode == 0 else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="sbi_return_to_gcloud_inventory.json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise SystemExit("SOURCE_ROOT_NOT_FOUND")
    files = []
    for top in (*ALLOW_ROOTS, *ALLOW_FILES):
        path = root / top
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else path.rglob("*")
        for p in candidates:
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(root)
            if any(part.lower() in BLOCK_PARTS for part in rel.parts):
                continue
            if p.name.lower() in BLOCK_NAMES or p.suffix.lower() not in SUFFIXES:
                continue
            if p.stat().st_size > MAX_FILE:
                continue
            # Hashes and paths only. No source contents are exported.
            files.append({
                "path": rel.as_posix(),
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            })
    report = {
        "purpose": "offline source comparison; NO production authorization",
        "git_head": run_git(root, "rev-parse", "HEAD"),
        "git_branch": run_git(root, "branch", "--show-current"),
        "tracked_source_files": len(files),
        "files": sorted(files, key=lambda f: f["path"]),
        "limitations": [
            "Only allowed code/config paths included; other source may be missing.",
            "No AWS runtime, Cloud Run IAM, secret values or database state verified.",
            "Public GitHub must never receive private financial data or credentials.",
            "All financial writes and production cutover remain blocked.",
        ],
    }
    out = Path(args.out).resolve()
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("SOURCE_FILES_INVENTORIED=" + str(len(files)))
    print("GIT_HEAD=" + str(report["git_head"] or "UNAVAILABLE"))
    print("OUTPUT=" + str(out))
    print("FINANCIAL_WRITES=0")
    print("PRODUCTION_DEPLOYMENT=NOT_ATTEMPTED")
    print("=== RETURN TO GCLOUD INVENTORY COMPLETE ===")

if __name__ == "__main__":
    main()
