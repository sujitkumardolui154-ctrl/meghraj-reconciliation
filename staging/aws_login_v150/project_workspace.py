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
    # The existing persistent SQLite file is migrated in place. Never
    # recreate the table or discard notes/task history on rollout.
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS personal_items ("
        "item_id TEXT PRIMARY KEY, owner_uid TEXT NOT NULL, "
        "kind TEXT NOT NULL CHECK(kind IN ('note','task')), "
        "title TEXT NOT NULL, body TEXT NOT NULL, "
        "priority TEXT NOT NULL, status TEXT NOT NULL, due_on TEXT NOT NULL, "
        "created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL, "
        "sort_order INTEGER NOT NULL DEFAULT 0)"
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(personal_items)")}
    if "sort_order" not in columns:
        conn.execute(
            "ALTER TABLE personal_items ADD COLUMN "
            "sort_order INTEGER NOT NULL DEFAULT 0"
        )
        # Existing users receive stable ordering by original insertion rowid.
        conn.execute("UPDATE personal_items SET sort_order=rowid WHERE sort_order=0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_personal_items_owner "
        "ON personal_items(owner_uid, updated_utc DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_personal_items_order "
        "ON personal_items(owner_uid, kind, priority, status, sort_order)"
    )
    conn.commit()
    return conn


def _next_order(conn, owner_uid, priority):
    result = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM personal_items "
        "WHERE owner_uid=? AND kind='task' AND priority=?",
        (owner_uid, priority),
    ).fetchone()
    return result[0]


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
        "due_on", "created_utc", "updated_utc", "sort_order"
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
                order = _next_order(conn, _owner(), priority) if kind == "task" else 0
                conn.execute(
                    "INSERT INTO personal_items "
                    "(item_id,owner_uid,kind,title,body,priority,status,due_on,"
                    "created_utc,updated_utc,sort_order) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (item_id, _owner(), kind, title, body, priority, status,
                     due_on, now, now, order),
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
                "ORDER BY CASE kind WHEN 'task' THEN 0 ELSE 1 END, "
                "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, "
                "sort_order ASC, updated_utc DESC LIMIT ?",
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


@workspace.post("/control-tower/api/workspace/reorder")
def reorder_personal_tasks():
    """Persist a complete owner-scoped P0/P1/P2 *active* lane order atomically."""
    data, rejection = _mutation_data()
    if rejection:
        return rejection
    if set(data) != {"priority", "ordered_ids"}:
        return jsonify(error="Reorder requires only priority and ordered_ids"), 422
    priority, ids = data["priority"], data["ordered_ids"]
    if priority not in PRIORITIES or not isinstance(ids, list) or len(ids) > MAX_ITEMS:
        return jsonify(error="Invalid task bucket or list"), 422
    if any(not isinstance(value, str) or not ITEM_ID.fullmatch(value) for value in ids):
        return jsonify(error="Invalid task ID in reorder list"), 422
    if len(ids) != len(set(ids)):
        return jsonify(error="Duplicate task IDs are not allowed"), 422
    try:
        with closing(_db()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            actual = {
                row["item_id"] for row in conn.execute(
                    "SELECT item_id FROM personal_items WHERE owner_uid=? "
                    "AND kind='task' AND priority=? AND status!='done'",
                    (_owner(), priority),
                )
            }
            if actual != set(ids):
                return jsonify(
                    error="Task bucket changed. Reload your tasks and try again.",
                    financial_writes=False,
                ), 409
            now = _now()
            for position, item_id in enumerate(ids, 1):
                conn.execute(
                    "UPDATE personal_items SET sort_order=?,updated_utc=? "
                    "WHERE owner_uid=? AND item_id=? AND kind='task' "
                    "AND priority=? AND status!='done'",
                    (position, now, _owner(), item_id, priority),
                )
        return jsonify(ok=True, priority=priority, updated=len(ids),
                       financial_writes=False, github_published=False)
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
            # Moving priorities or restoring an archived task puts it at the
            # end of its active bucket. No official GitHub task is modified.
            moved = kind == "task" and (
                priority != row["priority"] or
                (row["status"] == "done" and status != "done")
            )
            order = _next_order(conn, _owner(), priority) if moved else row["sort_order"]
            conn.execute(
                "UPDATE personal_items SET title=?,body=?,priority=?,status=?,"
                "due_on=?,sort_order=?,updated_utc=? WHERE item_id=? AND owner_uid=?",
                (title, body, priority, status, due_on, order, _now(), item_id, _owner()),
            )
            return jsonify(ok=True, item_id=item_id, financial_writes=False)
    except (OSError, sqlite3.Error):
        return jsonify(error="Private workspace storage unavailable"), 503
