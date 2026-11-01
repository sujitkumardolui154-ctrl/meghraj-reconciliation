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
    if len(tasks) != 42 or len(ids) != len(set(ids)):
        raise ValueError("Task queue failed unique-ID and size validation")
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
        "user_checklist": dict(Counter(t["user_checklist"] for t in tasks)),
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
