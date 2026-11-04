"""AWS private import HMAC verifier with SQLite-backed replay prevention.

Requires a separately provisioned high-entropy key file and persistent,
private replay database accessible to all backend workers for the service.
No Google identity fallback and no financial database access.
"""
import hashlib
import hmac
import os
import re
import sqlite3
import time


MAX_BYTES = 8 * 1024 * 1024 + 65536
SKEW_SECONDS = 30


def _key(path):
    if not path or not os.path.isabs(path):
        raise ValueError("Dedicated service key file path required")
    with open(path, "rb") as stream:
        key = stream.read(257)
    if not 32 <= len(key) <= 256:
        raise ValueError("Invalid service key length")
    return key


def _record_nonce(db_path, nonce, timestamp, now):
    if not db_path or not os.path.isabs(db_path):
        return False
    # The directory must be private; do not use a shared system /tmp path.
    directory = os.path.dirname(db_path)
    if os.stat(directory).st_mode & 0o077:
        return False
    connection = sqlite3.connect(db_path, timeout=2.0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS import_nonces (nonce TEXT PRIMARY KEY, seen INTEGER NOT NULL)")
        connection.execute("DELETE FROM import_nonces WHERE seen < ?", (now - SKEW_SECONDS - 2,))
        connection.execute("INSERT INTO import_nonces (nonce, seen) VALUES (?, ?)", (nonce, timestamp))
        connection.commit()
        return True
    except (sqlite3.Error, OSError):
        connection.rollback()
        return False
    finally:
        connection.close()


def verify_aws_import_request(request, *, key_path=None, replay_db=None, now=None, nonce_store=None):
    """Fail closed; verify signature *before* import handler/Firestore client."""
    try:
        if request.method not in ("GET", "POST"):
            return False
        auth = request.headers.get("Authorization", "")
        match = re.fullmatch(r"SBI-HMAC-SHA256 ([0-9a-f]{64})", auth)
        timestamp = request.headers.get("X-SBI-Auth-Timestamp", "")
        nonce = request.headers.get("X-SBI-Auth-Nonce", "")
        if not match or not re.fullmatch(r"[0-9]{10,11}", timestamp):
            return False
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            return False
        current = int(time.time() if now is None else now)
        issued = int(timestamp)
        if abs(current - issued) > SKEW_SECONDS:
            return False
        if request.content_length is not None and request.content_length > MAX_BYTES:
            return False
        request.max_content_length = MAX_BYTES
        body = request.get_data(cache=True)
        if len(body) > MAX_BYTES:
            return False
        path = request.path
        if request.query_string:
            path += "?" + request.query_string.decode("ascii")
        if not path.startswith("/imports/") or "\n" in path or "\r" in path:
            return False
        digest = hashlib.sha256(body).hexdigest()
        payload = ("sbi-import-v1\n" + request.method + "\n" + path + "\n"
                   + timestamp + "\n" + nonce + "\n" + digest).encode("ascii")
        expected = hmac.new(_key(key_path or os.environ.get("SBI_AWS_IMPORT_KEY_FILE")),
                            payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(match.group(1), expected):
            return False
        if nonce_store is not None:
            return bool(nonce_store(nonce, issued, current))
        return _record_nonce(replay_db or os.environ.get("SBI_AWS_IMPORT_REPLAY_DB"),
                             nonce, issued, current)
    except (ValueError, TypeError, OSError, UnicodeError, sqlite3.Error):
        return False
