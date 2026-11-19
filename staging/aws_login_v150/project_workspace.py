"""Private, non-financial personal project notes and tasks.

Every operation requires the existing verified Firebase dashboard session.
Mutation requires the existing exact-origin CSRF guard. Data is stored ONLY in a
dedicated host-backed SQLite volume, never in the financial database or GitHub.
"""
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, g, jsonify, request
from dashboard_sessions import csrf_valid

workspace = Blueprint("sbi_private_workspace", __name__)

MAX_ITEMS = 300
KINDS = {"note", "task"}
TASK_STATUSES = {"pending", "in_progress", "done"}
PRIORITIES = {"P0", "P1", "P2"}
ITEM_ID = re.compile(r"^[a-f0-9]{32}$")
DUE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _db():
    name = os.environ.get("SBI_PRIVATE_WORKSPACE_DB", "")
    if not name or not Path(name).is_absolute():
        raise OSError("Workspace storage has not been configured")
    target = Path(name)
    parent = target.parent
    if target.is_symlink() or not parent.is_dir() or parent.is_symlink():
        raise OSError("Private workspace directory unavailable")
    conn = sqlite3.connect(name, timeout=4)
    # Private owner-only database, never an exposed temp or financial file.
    os.chmod(name, 0o600)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 4000")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS personal_items ("
        "item_id TEXT PRIMARY KEY, owner_uid TEXT NOT NULL, "
        "kind TEXT NOT NULL CHECK(kind IN ('note','task')), "
        "title TEXT NOT NULL, body TEXT NOT NULL, "
        "priority TEXT NOT NULL, status TEXT NOT NULL, due_on TEXT NOT NULL, "
        "created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_personal_items_owner "
        "ON personal_items(owner_uid, updated_utc DESC)"
    )
    conn.commit()
    return conn


def _owner():
    return str(g.dil_user.uid)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate(data, original=None):
    if not isinstance(data, dict) or len(data) > 9:
        raise ValueError("Invalid project note/task")
    base = dict(original or {})
    for key in data:
        if key not in {"title", "body", "kind", "priority", "status", "due_on"}:
            raise ValueError("Unrecognized project note/task field")
    base.update(data)
    kind = base.get("kind", "task")
    if kind not in KINDS:
        raise ValueError("Select project note or personal task")
    if original and kind != original["kind"]:
        raise ValueError("Item type cannot be changed")
    title = base.get("title", "")
    body = base.get("body", "")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 140:
        raise ValueError("Title must contain 1–140 characters")
    if not isinstance(body, str) or len(body) > 4000:
        raise ValueError("Details must be 4,000 characters or fewer")
    priority = base.get("priority", "P1")
    status = base.get("status", "pending" if kind == "task" else "note")
    due_on = base.get("due_on", "")
    if kind == "note":
        if status not in ("note", "pending"):
            raise ValueError("Project notes cannot be marked as release approvals")
        status = "note"
        priority = "P1"
        due_on = ""
    elif priority not in PRIORITIES or status not in TASK_STATUSES:
        raise ValueError("Invalid task priority or status")
    if not isinstance(due_on, str) or (due_on and not DUE_DATE.fullmatch(due_on)):
        raise ValueError("Due date must be YYYY-MM-DD")
    return (kind, title.strip(), body.strip(), priority, status, due_on)


def _mutation_data():
    if not csrf_valid():
        return None, (jsonify(error="Same-origin CSRF verification required"), 403)
    if request.content_length is None or request.content_length > 12_000:
        return None, (jsonify(error="Project note/task request too large"), 413)
    if not request.is_json:
        return None, (jsonify(error="JSON request required"), 415)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify(error="Invalid JSON object"), 400)
    return data, None


def _item(row):
    return {name: row[name] for name in (
        "item_id", "kind", "title", "body", "priority", "status",
        "due_on", "created_utc", "updated_utc"
    )}


@workspace.route("/control-tower/api/workspace", methods=["GET", "POST"])
def personal_items():
    if request.method == "POST":
        data, rejection = _mutation_data()
        if rejection:
            return rejection
        try:
            kind, title, body, priority, status, due_on = _validate(data)
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        try:
            with closing(_db()) as conn, conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM personal_items WHERE owner_uid = ?",
                    (_owner(),),
                ).fetchone()[0]
                if count >= MAX_ITEMS:
                    return jsonify(error="Private workspace limit reached"), 409
                item_id, now = secrets.token_hex(16), _now()
                conn.execute(
                    "INSERT INTO personal_items "
                    "(item_id,owner_uid,kind,title,body,priority,status,due_on,"
                    "created_utc,updated_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (item_id, _owner(), kind, title, body, priority, status,
                     due_on, now, now),
                )
            return jsonify(
                ok=True, item_id=item_id, financial_writes=False,
            ), 201
        except (OSError, sqlite3.Error):
            return jsonify(error="Private workspace storage unavailable"), 503

    try:
        with closing(_db()) as conn, conn:
            rows = conn.execute(
                "SELECT * FROM personal_items WHERE owner_uid = ? "
                "ORDER BY updated_utc DESC LIMIT ?",
                (_owner(), MAX_ITEMS),
            ).fetchall()
        return jsonify(
            items=[_item(row) for row in rows],
            storage="host_persistent_private_sqlite",
            financial_writes=False,
            github_published=False,
        )
    except (OSError, sqlite3.Error):
        return jsonify(error="Private workspace storage unavailable"), 503


@workspace.route("/control-tower/api/workspace/<item_id>", methods=["PATCH", "DELETE"])
def modify_personal_item(item_id):
    if not ITEM_ID.fullmatch(item_id):
        return jsonify(error="Invalid item ID"), 404
    data, rejection = _mutation_data()
    if rejection:
        return rejection
    if request.method == "DELETE" and data:
        return jsonify(error="Delete request must not include changes"), 422
    try:
        with closing(_db()) as conn, conn:
            row = conn.execute(
                "SELECT * FROM personal_items WHERE item_id=? AND owner_uid=?",
                (item_id, _owner()),
            ).fetchone()
            if row is None:
                return jsonify(error="Personal item not found"), 404
            if request.method == "DELETE":
                conn.execute(
                    "DELETE FROM personal_items WHERE item_id=? AND owner_uid=?",
                    (item_id, _owner()),
                )
                return jsonify(ok=True, deleted=True, financial_writes=False)
            try:
                kind, title, body, priority, status, due_on = _validate(
                    data, dict(row)
                )
            except ValueError as exc:
                return jsonify(error=str(exc)), 422
            conn.execute(
                "UPDATE personal_items SET title=?,body=?,priority=?,status=?,"
                "due_on=?,updated_utc=? WHERE item_id=? AND owner_uid=?",
                (title, body, priority, status, due_on, _now(), item_id, _owner()),
            )
            return jsonify(ok=True, item_id=item_id, financial_writes=False)
    except (OSError, sqlite3.Error):
        return jsonify(error="Private workspace storage unavailable"), 503
