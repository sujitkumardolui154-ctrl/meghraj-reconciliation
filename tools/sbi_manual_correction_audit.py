#!/usr/bin/env python3
"""Validate the manual SBI task-correction queue without financial access or writes.

Use: python3 tools/sbi_manual_correction_audit.py
The authoritative A–N task_queue.json remains the execution status source.
Manual triage NEVER implies that a task was implemented or approved.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "agent" / "task_queue.json"
PLAN = ROOT / "agent" / "manual_correction_plan.json"
FINANCE_GATES = {"database_write", "finance_release"}


def validate(queue: dict, plan: dict) -> dict:
    errors: list[str] = []
    tasks = queue.get("tasks")
    entries = plan.get("items")
    if not isinstance(tasks, list) or not isinstance(entries, list):
        raise ValueError("Task register and manual queue must have arrays")
    indexed = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            errors.append("invalid_authoritative_task")
            continue
        tid = task["id"]
        if tid in indexed:
            errors.append("duplicate_authoritative_id")
        indexed[tid] = task
    pending = {tid for tid, t in indexed.items() if t.get("execution") == "pending"}
    manual_ids = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("invalid_manual_item")
            continue
        tid = item["id"]
        manual_ids.append(tid)
        original = indexed.get(tid)
        if original is None:
            errors.append("unknown_id")
            continue
        if original.get("execution") not in ("pending", "in_progress", "done"):
            errors.append("unknown_execution_state")
        elif original.get("execution") in ("in_progress", "done"):
            # Source implementation can advance a triaged task only with evidence.
            if not str(original.get("evidence") or "").strip():
                errors.append("advanced_task_missing_evidence")
            if original.get("execution") == "done":
                verification = str(original.get("verification") or "").lower()
                disallowed = ("", "not_verified", "partial_verified",
                              "source_implementation_under_review")
                if (verification in disallowed
                        or verification.startswith("not_verified")
                        or not any(key in verification for key in
                                   ("pass", "verified", "certified", "approved"))):
                    errors.append("done_task_missing_verification")
        if item.get("title") != original.get("title"):
            errors.append("title_mismatch")
        if item.get("approval_gate") != original.get("approval_gate"):
            errors.append("approval_gate_mismatch")
        if item.get("manual_review") != "TRIAGED_NOT_EXECUTED":
            errors.append("premature_execution_claim")
        if not all(isinstance(item.get(key), str) and item[key].strip()
                   for key in ("lane", "batch", "priority", "next_action",
                               "required_evidence", "constraint")):
            errors.append("incomplete_manual_instruction")
        if original.get("approval_gate") in FINANCE_GATES and (
            not str(item.get("lane", "")).startswith("C_")
            or item.get("priority") != "P3"
            or "NO_" not in str(item.get("constraint", ""))
        ):
            errors.append("financial_approval_mismatch")
    if len(manual_ids) != len(set(manual_ids)):
        errors.append("duplicate_manual_id")
    # The plan records a baseline cohort. A triaged task may later progress;
    # new pending tasks must still be added to the manual plan.
    if not pending.issubset(set(manual_ids)):
        errors.append("pending_coverage_mismatch")
    scope = plan.get("scope") or {}
    if (scope.get("pending_triaged") != len(entries)
            or scope.get("total_tasks") != len(tasks)
            or not isinstance(scope.get("completed_unchanged"), int)
            or scope["completed_unchanged"] >
            sum(t.get("execution") == "done" for t in tasks if isinstance(t, dict))):
        errors.append("scope_count_mismatch")
    policy = plan.get("gate_policy") or {}
    source_policy = queue.get("policy") or {}
    if (policy.get("financial_execution") != "RESTRICTED"
            or policy.get("database_writes") != "DISABLED"
            or policy.get("public_traffic") != "UNCHANGED"
            or policy.get("triage_does_not_mean_execution") is not True
            or source_policy.get("financial_execution") != "restricted"
            or source_policy.get("live_database_writes") != "disabled"):
        errors.append("restricted_policy_mismatch")
    return {
        "status": "PASS" if not errors else "REVIEW_REQUIRED",
        "total": len(tasks),
        "pending_triaged": len(set(manual_ids) & pending),
        "baseline_triaged": len(manual_ids),
        "advanced_from_baseline": sum(
            item.get("id") in indexed and indexed[item["id"]].get("execution") != "pending"
            for item in entries if isinstance(item, dict) and isinstance(item.get("id"), str)
        ),
        "completed": sum(t.get("execution") == "done" for t in tasks if isinstance(t, dict)),
        "priority_counts": dict(sorted(Counter(
            item.get("priority") for item in entries if isinstance(item, dict)
        ).items())),
        "errors": sorted(set(errors)),
        "financial_execution": "RESTRICTED",
        "database_writes": "DISABLED",
        "source_changes": 0,
    }


def main() -> int:
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    result = validate(queue, plan)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
