"""Owner-only non-financial priority tasks: durable SQLite and GitHub Issues.

This module never reads invoice, payment or Firestore data. GitHub credentials
stay on the server; a task is marked "synced" only on verified issue response.
Source task_queue.json and financial release gates are deliberately immutable.
"""
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = "sujitkumardolui154-ctrl/meghraj-reconciliation"
API = "https://api.github.com/repos/" + REPO
LOCK = RLock()
PRIORITIES = frozenset(("P0", "P1", "P2"))
STATUSES = frozenset(("pending", "in_progress", "done"))
IDENTIFIER = re.compile(r"^OWN-[a-f0-9]{16}$")
SENSITIVE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|github_pat_[A-Za-z0-9_]+|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,})"
)


class InvalidTask(ValueError):
    pass


class StaleTask(ValueError):
    pass


class GitHubUnavailable(Exception):
    pass


def storage_available():
    path = os.environ.get("SBI_PRIORITY_DB_PATH", "")
    return (bool(path) and Path(path).is_absolute()
            and Path(path).parent.is_dir())


def enabled():
    owner_key = os.environ.get("SBI_TASK_OWNER_KEY", "")
    github_key = os.environ.get("SBI_GITHUB_ISSUES_TOKEN", "")
    return storage_available() and len(owner_key) >= 32 and len(github_key) >= 20


def authorized(owner_key):
    expected = os.environ.get("SBI_TASK_OWNER_KEY", "")
    return (enabled() and isinstance(owner_key, str)
            and hmac.compare_digest(owner_key, expected))


def _db():
    path = os.environ["SBI_PRIORITY_DB_PATH"]
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS priority_tasks (
        id TEXT PRIMARY KEY, priority TEXT NOT NULL, title TEXT NOT NULL,
        details TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
        github_number INTEGER, github_url TEXT, sync_state TEXT NOT NULL,
        created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS priority_task_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        revision INTEGER NOT NULL, action TEXT NOT NULL, at_utc TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _row(row):
    return dict(row) if row is not None else None


def list_tasks():
    if not storage_available():
        return []
    with LOCK:
        with _db() as conn:
            return [_row(r) for r in conn.execute(
                "SELECT * FROM priority_tasks ORDER BY created_utc DESC LIMIT 250"
            )]


def _clean(payload):
    if not isinstance(payload, dict):
        raise InvalidTask("Expected a task object")
    priority = payload.get("priority")
    status = payload.get("status")
    title = payload.get("title")
    details = payload.get("details", "")
    if priority not in PRIORITIES or status not in STATUSES:
        raise InvalidTask("Choose a valid priority and task status")
    if not isinstance(title, str) or not 5 <= len(title.strip()) <= 140:
        raise InvalidTask("Task title must have 5–140 characters")
    if not isinstance(details, str) or len(details) > 1500:
        raise InvalidTask("Task details exceed 1500 characters")
    title, details = title.strip(), details.strip()
    if SENSITIVE.search(title + "\n" + details):
        raise InvalidTask("Do not submit credentials or secrets")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in title + details):
        raise InvalidTask("Control characters are not permitted")
    return priority, status, title, details


def _get(conn, task_id):
    if not isinstance(task_id, str) or not IDENTIFIER.fullmatch(task_id):
        raise InvalidTask("Unknown task identifier")
    row = conn.execute("SELECT * FROM priority_tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise InvalidTask("Unknown task identifier")
    return _row(row)


def _request_github(method, suffix, payload=None):
    token = os.environ["SBI_GITHUB_ISSUES_TOKEN"]
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    endpoint = ("https://api.github.com" if suffix.startswith("/search/issues?") else API)
    req = Request(endpoint + suffix, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SBI-Owner-Priority-Editor/1",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=8) as response:
            if response.status not in ((201,) if method == "POST" else (200,)):
                raise GitHubUnavailable("GitHub did not accept the task")
            raw = response.read(100000)
            if len(raw) >= 100000:
                raise GitHubUnavailable("GitHub response limit exceeded")
            return json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        # Never return credential-bearing request headers or source content.
        raise GitHubUnavailable("GitHub task synchronization unavailable") from exc


def _marker(task_id):
    return "<!-- SBI_PRIORITY_TASK:" + task_id + " -->"


def _issue_payload(task):
    body = (
        "## Owner-managed SBI Priority Task\n\n"
        "**Priority:** " + task["priority"] + "\n\n"
        "**Status:** " + task["status"].replace("_", " ") + "\n\n"
        "**Description:**\n\n" + (task["details"] or "(No details provided)") + "\n\n"
        "**Editor record:** " + task["id"] + " · revision " + str(task["revision"]) + "\n\n"
        "> Task metadata only. This issue does not authorize production deployment, "
        "financial settlement, database imports or a release gate override.\n\n"
        + _marker(task["id"])
    )
    return {"title": "[Priority " + task["priority"] + "] " + task["title"], "body": body}


def _verified_issue(doc, task_id):
    number = doc.get("number") if isinstance(doc, dict) else None
    link = doc.get("html_url") if isinstance(doc, dict) else None
    if (type(number) is not int or number <= 0
            or link != "https://github.com/" + REPO + "/issues/" + str(number)):
        raise GitHubUnavailable("GitHub issue identity was not verified")
    return number, link


def _publish(task):
    marker = _marker(task["id"])
    body = _issue_payload(task)
    if task["github_number"] is not None:
        number = task["github_number"]
        old = _request_github("GET", "/issues/" + str(number))
        _verified_issue(old, task["id"])
        if marker not in str(old.get("body") or ""):
            raise GitHubUnavailable("GitHub issue ownership marker mismatch")
        issue = _request_github("PATCH", "/issues/" + str(number), body)
        if marker not in str(issue.get("body") or ""):
            raise GitHubUnavailable("GitHub issue update not verified")
        return _verified_issue(issue, task["id"])

    # Search before creating. This helps recover after a response/database
    # interruption without making duplicate public issues.
    query = urlencode({"q": "repo:" + REPO + " in:body SBI_PRIORITY_TASK:" + task["id"]})
    search = _request_github("GET", "/search/issues?" + query)
    matches = [item for item in search.get("items", [])
               if isinstance(item, dict) and marker in str(item.get("body") or "")]
    if len(matches) > 1:
        raise GitHubUnavailable("Duplicate GitHub task identities require review")
    if matches:
        old = matches[0]
        number, _ = _verified_issue(old, task["id"])
        issue = _request_github("PATCH", "/issues/" + str(number), body)
    else:
        issue = _request_github("POST", "/issues", body)
    if marker not in str(issue.get("body") or ""):
        raise GitHubUnavailable("GitHub issue body was not verified")
    return _verified_issue(issue, task["id"])


def _sync(conn, task_id):
    task = _get(conn, task_id)
    try:
        number, link = _publish(task)
    except GitHubUnavailable:
        # Durable local task remains queued for an owner-triggered retry.
        return _get(conn, task_id)
    with conn:
        conn.execute("""UPDATE priority_tasks SET github_number=?,github_url=?,
                        sync_state='synced' WHERE id=? AND revision=?""",
                     (number, link, task_id, task["revision"]))
    return _get(conn, task_id)


def save_task(payload, *, task_id=None):
    if not enabled():
        raise RuntimeError("Priority editor is not configured")
    priority, status, title, details = _clean(payload)
    with LOCK:
        with _db() as conn:
            stamp = _stamp()
            if task_id is None:
                task_id = "OWN-" + secrets.token_hex(8)
                revision = 1
                with conn:
                    conn.execute("""INSERT INTO priority_tasks
                         (id,priority,title,details,status,revision,github_number,
                          github_url,sync_state,created_utc,updated_utc)
                         VALUES (?,?,?,?,?,1,NULL,NULL,'pending',?,?)""",
                         (task_id, priority, title, details, status, stamp, stamp))
                    conn.execute("""INSERT INTO priority_task_audit
                         (task_id,revision,action,at_utc) VALUES (?,1,'create',?)""",
                         (task_id, stamp))
            else:
                old = _get(conn, task_id)
                revision = payload.get("expected_revision")
                if type(revision) is not int or revision != old["revision"]:
                    raise StaleTask("Task changed; refresh before editing")
                with conn:
                    conn.execute("""UPDATE priority_tasks SET priority=?,status=?,
                         title=?,details=?,revision=revision+1,sync_state='pending',
                         updated_utc=? WHERE id=?""",
                         (priority, status, title, details, stamp, task_id))
                    conn.execute("""INSERT INTO priority_task_audit
                         (task_id,revision,action,at_utc) VALUES (?,?, 'edit',?)""",
                         (task_id, revision+1, stamp))
            return _sync(conn, task_id)


def retry_task(task_id):
    if not enabled():
        raise RuntimeError("Priority editor is not configured")
    with LOCK:
        with _db() as conn:
            return _sync(conn, task_id)
