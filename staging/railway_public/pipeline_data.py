"""Read-only cached SBI pipeline monitoring data from the public GitHub project.

This module never connects to financial databases or calls GitHub mutation APIs.
Upstream failures become explicit unavailable states, never invented PASS values.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

REPO = "sujitkumardolui154-ctrl/meghraj-reconciliation"
API = "https://api.github.com/repos/" + REPO
RAW_TASKS = "https://raw.githubusercontent.com/" + REPO + "/main/agent/task_queue.json"
TTL_SECONDS = 120
_LOCK = Lock()
_LAST_AT = 0.0
_LAST = None


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "SBI-ReadOnly-Pipeline-Dashboard/1.0",
    })
    with urlopen(req, timeout=4) as result:
        body = result.read(450_000)
        if len(body) >= 450_000:
            raise ValueError("GitHub response exceeds limit")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub document shape")
    return data


def _workflow(name: str) -> dict:
    doc = _fetch_json(API + "/actions/workflows/" + name + "/runs?per_page=1&branch=main")
    runs = doc.get("workflow_runs", [])
    if not isinstance(runs, list) or not runs:
        return {"available": True, "state": "no_runs", "run": None}
    run = runs[0]
    if not isinstance(run, dict):
        raise ValueError("Invalid workflow run")
    return {
        "available": True,
        "state": str(run.get("status") or "unknown"),
        "run": {
            "name": str(run.get("name") or name)[:100],
            "status": str(run.get("status") or "unknown"),
            "conclusion": str(run.get("conclusion") or "pending"),
            "sha": str(run.get("head_sha") or "")[:40],
            "url": str(run.get("html_url") or ""),
            "created_at": str(run.get("created_at") or ""),
            "updated_at": str(run.get("updated_at") or ""),
        }
    }


def _task_data() -> dict:
    queue = _fetch_json(RAW_TASKS)
    original = queue.get("tasks")
    if not isinstance(original, list) or len(original) > 250:
        raise ValueError("Unexpected task register")
    tasks = []
    for entry in original:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        tasks.append({
            "id": entry["id"][:24],
            "title": str(entry.get("title") or "")[:180],
            "category": str(entry.get("category") or "Other")[:100],
            "execution": str(entry.get("execution") or "unknown")[:40],
            "verification": str(entry.get("verification") or "unverified")[:70],
            "approval_gate": str(entry.get("approval_gate") or "standard")[:40],
        })
    counts = Counter(t["execution"] for t in tasks)
    categories = {}
    for t in tasks:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = {"name": cat, "total": 0, "done": 0,
                               "blocked": 0, "in_progress": 0, "pending": 0}
        row = categories[cat]
        row["total"] += 1
        if t["execution"] in ("done", "approved"):
            row["done"] += 1
        if t["execution"] in ("blocked", "in_progress", "pending"):
            row[t["execution"]] += 1
    return {
        "available": True,
        "total": len(tasks),
        "counts": dict(counts),
        "categories": list(categories.values()),
        "tasks": tasks,
        "policy": {
            "financial_execution": str(queue.get("policy", {}).get("financial_execution", "restricted")),
            "database_writes": str(queue.get("policy", {}).get("live_database_writes", "disabled")),
        }
    }


def _collect() -> dict:
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "SBI Reconciliation",
        "source": "Public GitHub repository; cached read-only",
        "cache_seconds": TTL_SECONDS,
        "financial_api_connected": False,
        "financial_production": "restricted",
        "live_executor_rollback": "not_verified",
        "sources": {},
    }
    try:
        result["register"] = _task_data()
        result["sources"]["task_register"] = "available"
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError, OSError):
        result["register"] = {"available": False, "total": None,
                              "counts": {}, "categories": [], "tasks": []}
        result["sources"]["task_register"] = "unavailable"
    for key, filename in (
        ("staging", "sbi-aws-staging-release-request.yml"),
        ("qa", "sbi-consolidated-controller.yml"),
    ):
        try:
            result[key] = _workflow(filename)
            result["sources"][key] = "available"
        except (HTTPError, URLError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError, OSError):
            result[key] = {"available": False, "state": "unavailable", "run": None}
            result["sources"][key] = "unavailable"
    return result


def current_pipeline() -> dict:
    global _LAST, _LAST_AT
    with _LOCK:
        if _LAST is not None and monotonic() - _LAST_AT < TTL_SECONDS:
            return _LAST
        snapshot = _collect()
        _LAST, _LAST_AT = snapshot, monotonic()
        return snapshot
