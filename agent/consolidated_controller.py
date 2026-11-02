"""Consolidated SBI agent controller: real task triage, change-aware QA and release gates.

No fabricated coding agent: AI code generation must be provided by an explicitly
configured, authenticated coding integration. This controller is operational
locally and via CI, but cannot autonomously write financial data or promote
traffic.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = "ABCDEFGHIJKLMN"
ALLOWED = {"pending", "in_progress", "done", "blocked", "approved"}
TESTS = (
    ("financial_contract", "test_financial_contract.py"),
    ("import_receipts", "test_import_receipt_audit.py"),
    ("credit_note_auth", "test_credit_note_auth_contract.py"),
    ("credit_note_snapshot", "test_credit_note_snapshot_integrity.py"),
    ("aws_staging_contract", "test_aws_staging_release_contract.py"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(data: dict) -> dict:
    tasks = data["tasks"]
    ids = [item["id"] for item in tasks]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("Duplicate or empty task identifiers")
    for item in tasks:
        if not item["id"] or item["id"][0] not in CATEGORIES:
            raise ValueError("Unknown task category")
        if item.get("execution") not in ALLOWED:
            raise ValueError("Invalid task state: " + str(item.get("id")))
    counts = Counter(t["execution"] for t in tasks)
    buckets = Counter(t["id"][0] for t in tasks)
    return {
        "task_total": len(tasks),
        "buckets": dict(sorted(buckets.items())),
        "states": dict(sorted(counts.items())),
        "financial_write_permitted": False,
        "traffic_promotion_permitted": False,
        "coding_agent_configured": False,
    }


def changed_files(base: str | None) -> list[str]:
    if not base:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", base + "...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if proc.returncode:
        raise RuntimeError("Git comparison failed; cannot reuse cached QA evidence")
    return [s for s in proc.stdout.splitlines() if s]


def choose_tests(files: list[str], force_full: bool) -> list[tuple[str, str]]:
    if force_full or not files:
        return list(TESTS)
    # Deployment and staging changes affect the release boundary; never skip QA.
    if any(f.startswith(("agent/", ".github/", "deployment/", "staging/", "migration/")) for f in files):
        return list(TESTS)
    selected = set()
    for file in files:
        if any(x in file for x in ("financial", "payment", "reconciliation")):
            selected.add("financial_contract")
        if any(x in file for x in ("import", "receipt", "database")):
            selected.add("import_receipts")
        if any(x in file for x in ("auth", "session", "gateway")):
            selected.add("credit_note_auth")
        if any(x in file for x in ("credit", "report", "snapshot")):
            selected.add("credit_note_snapshot")
    if not selected and not all(f.startswith("docs/") or f.endswith(".md") for f in files):
        # Unknown source paths are not proof that tests are unnecessary.
        return list(TESTS)
    return [item for item in TESTS if item[0] in selected]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="review base ref for change-scoped tests")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--full-tests", action="store_true")
    parser.add_argument("--output", default="/tmp/sbi-agentic-gate.json")
    args = parser.parse_args()
    queue = ROOT / "agent" / "task_queue.json"
    report = evaluate(json.loads(queue.read_text(encoding="utf-8")))
    files = changed_files(args.base)
    selected = choose_tests(files, args.full_tests)
    report.update({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_source_sha256": digest(queue),
        "changed_files": files,
        "test_plan": [name for name, _ in selected],
        "test_results": [],
        "release_status": "REVIEW_REQUIRED",
        "agent_capability": "DETERMINISTIC_ORCHESTRATOR_ONLY",
    })
    if args.run_tests:
        for name, filename in selected:
            test_path = ROOT / "tests" / filename
            if not test_path.is_file():
                report["test_results"].append({"name": name, "result": "MISSING"})
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                 "-p", filename, "-v"],
                cwd=ROOT, capture_output=True, text=True, timeout=240,
                check=False,
            )
            report["test_results"].append({
                "name": name, "result": "PASS" if proc.returncode == 0 else "FAIL",
                "exit_code": proc.returncode,
                "log_tail": (proc.stdout + proc.stderr)[-2500:],
            })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("TASKS=" + str(report["task_total"]))
    print("TESTS_SELECTED=" + ",".join(report["test_plan"]))
    print("RELEASE_STATUS=REVIEW_REQUIRED")
    print("AGENT_CAPABILITY=DETERMINISTIC_ORCHESTRATOR_ONLY")
    if any(x["result"] != "PASS" for x in report["test_results"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
