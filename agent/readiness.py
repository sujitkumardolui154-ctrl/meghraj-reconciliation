"""Read-only SBI task queue and source-readiness audit; no network or cloud writes."""
from __future__ import annotations

import ast
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "agent" / "task_queue.json"
OUTPUT = Path(os.environ.get("SBI_READINESS_OUTPUT", "/tmp/sbi-agent-readiness.json"))


def main():
    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    ids = [task["id"] for task in tasks]
    # Validate the authoritative A–N register without hard-coding an obsolete
    # 50-task or 88-task count. A new ID is never proof of completion.
    expected_categories = {
        "A": "A — Reports Development",
        "B": "B — Database Update",
        "C": "C — Database Backup & Recovery",
        "D": "D — Financial Engine",
        "E": "E — Deployment & Operations",
        "F": "F — Intelligent Chatbot",
        "G": "G — UI/UX Engineering",
        "H": "H — AI Development Automation",
        "I": "I — Performance & Caching",
        "J": "J — GitHub DevOps & CI/CD",
        "K": "K — AWS Migration & Hosting",
        "L": "L — Data Intelligence & Branch Matching",
        "M": "M — Audit, Compliance & Security",
        "N": "N — Release Governance",
    }
    if (not tasks or len(ids) != len(set(ids))
            or any(not isinstance(task_id, str) or len(task_id) != 3
                   or task_id[0] not in expected_categories
                   or not task_id[1:].isdigit() for task_id in ids)):
        raise ValueError("A–N task queue has duplicate or malformed IDs")
    categories_found = set()
    for task in tasks:
        category = task.get("category")
        letter = task["id"][0]
        if category != expected_categories[letter]:
            raise ValueError("Task ID/workstream mismatch: " + task["id"])
        if task.get("execution") not in ("pending", "in_progress", "blocked", "done", "approved"):
            raise ValueError("Unrecognized task execution state: " + task["id"])
        categories_found.add(letter)
    if categories_found != set(expected_categories):
        raise ValueError("Missing required A–N workstream in task queue")
    policy = data["policy"]
    if (policy["live_database_writes"] != "disabled"
            or policy["financial_execution"] != "restricted"
            or policy["cloud_deployment"] != "disabled"):
        raise ValueError("Unsafe execution policy")

    source = ROOT / "backend_source"
    python_files = sorted(source.rglob("*.py")) if source.exists() else []
    syntax_errors = []
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:
            syntax_errors.append({
                "file": str(path.relative_to(ROOT)),
                "error_type": type(exc).__name__
            })
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "project": data["project"],
        "read_only": True,
        "task_total": len(tasks),
        "workstream_count": len(categories_found),
        "execution_states": dict(Counter(t["execution"] for t in tasks)),
        "done_or_approved_tasks": sum(t["execution"] in ("done", "approved") for t in tasks),
        "user_checklist": dict(Counter(t.get("user_checklist", "unspecified") for t in tasks)),
        "independently_verified_tasks": sum(
            t["verification"] == "verified" for t in tasks),
        "backend_source_available": source.exists(),
        "python_source_files": len(python_files),
        "syntax_errors": syntax_errors,
        "release_ready": False,
        "execution_mode": "AUDIT_ONLY",
        "next_action": "Safely publish reviewed source in a private execution repository; verify authentication and recoverable database backups."
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("SBI_AGENT_TASKS:", len(tasks))
    print("USER_CHECKED:", result["user_checklist"].get("checked", 0))
    print("INDEPENDENTLY_VERIFIED:", result["independently_verified_tasks"])
    print("BACKEND_SOURCE_FILES:", len(python_files))
    print("PYTHON_SYNTAX_ERRORS:", len(syntax_errors))
    print("MODE: AUDIT_ONLY")
    print("AUTONOMOUS_CODING: NOT_CONFIGURED")
    print("CLOUD_DEPLOYMENT: DISABLED")
    print("FINANCIAL_EXECUTION: RESTRICTED")
    print("AUDIT_OUTPUT:", OUTPUT)
    if syntax_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
