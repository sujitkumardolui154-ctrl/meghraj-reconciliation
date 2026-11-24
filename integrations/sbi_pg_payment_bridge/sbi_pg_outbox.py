"""Private SQLite delivery outbox for the separate staging SBI app only.

Receipt persistence is owned by the original Flask payment handler. This outbox
stores the accepted workbook in a separate durable SQLite ledger and uses a
bounded, idempotent, insert-only PostgreSQL worker. It never mutates the original
receipt or PostgreSQL source rows. Requires a persistent private mount.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_ATTEMPTS = 100
STALE_SECONDS = 180


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _store():
    from sbi_payment_pg_bridge import QA_DATABASE, QA_HOST, QA_WRITER
    if (os.getenv('SBI_PG_PAYMENT_BRIDGE_ENABLED') != 'staging-only'
        or os.getenv('PGDATABASE') != QA_DATABASE
        or os.getenv('PGHOST') != QA_HOST
        or os.getenv('PGUSER') != QA_WRITER):
        raise RuntimeError('Unsafe staging outbox database identity')
    root = Path(os.environ['SBI_PAYMENT_EVIDENCE_DIR'])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RuntimeError('Invalid outbox directory')
    info = root.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('Private outbox directory permissions invalid')
    if str(root).startswith('/tmp/') and os.environ.get('SBI_PG_OUTBOX_ALLOW_TMPFS') != 'unit-test-only':
        raise RuntimeError('Persistent QA outbox volume required')
    return root


def _connect():
    path = _store() / 'sbi_pg_delivery_outbox.sqlite3'
    if path.is_symlink():
        raise RuntimeError('Outbox file may not be a symlink')
    connection = sqlite3.connect(str(path), timeout=8)
    try:
        os.chmod(path, 0o600)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA busy_timeout=8000')
        connection.execute('''CREATE TABLE IF NOT EXISTS delivery_queue (
           owner_uid TEXT NOT NULL,
           source_sha256 TEXT NOT NULL,
           payload BLOB,
           state TEXT NOT NULL CHECK(state IN
             ('PENDING','PROCESSING','RETRY','COMMITTED','NO_ELIGIBLE_ROWS','REVIEW_REQUIRED')),
           attempt_count INTEGER NOT NULL DEFAULT 0,
           last_error TEXT,
           review_json TEXT NOT NULL DEFAULT '[]',
           created_utc TEXT NOT NULL,
           updated_utc TEXT NOT NULL,
           lease_epoch REAL NOT NULL DEFAULT 0,
           PRIMARY KEY(owner_uid,source_sha256)
        )''')
        connection.commit()
        return connection
    except Exception:
        connection.close()
        raise


def queue_delivery(payload: bytes, owner_uid: str):
    if not owner_uid or len(owner_uid) > 200 or not isinstance(payload, bytes):
        raise ValueError('Invalid authenticated source identity or payload')
    if not 8 <= len(payload) <= MAX_BYTES:
        raise ValueError('Invalid payment Excel length')
    digest = hashlib.sha256(payload).hexdigest()
    now = _utc()
    with _connect() as con:
        con.execute('''INSERT OR IGNORE INTO delivery_queue
          (owner_uid,source_sha256,payload,state,created_utc,updated_utc)
          VALUES (?, ?, ?, 'PENDING', ?, ?)''',
          (owner_uid,digest,sqlite3.Binary(payload),now,now))
        found = con.execute('''SELECT length(payload),state FROM delivery_queue
          WHERE owner_uid=? AND source_sha256=?''',(owner_uid,digest)).fetchone()
        if not found:
            raise RuntimeError('Outbox insert did not persist')
        if found[1] not in ('COMMITTED','NO_ELIGIBLE_ROWS','REVIEW_REQUIRED') and found[0] != len(payload):
            raise RuntimeError('Outbox payload conflict')
    return digest


def _claim(owner_uid=None, source_sha=None):
    with _connect() as con:
        con.execute('BEGIN IMMEDIATE')
        conditions = ["(state IN ('PENDING','RETRY') OR (state='PROCESSING' AND lease_epoch < ?))",
                      'attempt_count < ?']
        params = [time.time()-STALE_SECONDS, MAX_ATTEMPTS]
        if owner_uid is not None:
            conditions.append('owner_uid=?')
            params.append(owner_uid)
        if source_sha is not None:
            conditions.append('source_sha256=?')
            params.append(source_sha)
        record = con.execute('''SELECT owner_uid,source_sha256,payload,
          attempt_count FROM delivery_queue WHERE '''+' AND '.join(conditions)+
          ' ORDER BY created_utc LIMIT 1',params).fetchone()
        if record is None:
            return None
        owner,digest,payload,attempts = record
        if not isinstance(payload,bytes) or hashlib.sha256(payload).hexdigest() != digest:
            raise RuntimeError('Corrupted immutable outbox source payload')
        con.execute('''UPDATE delivery_queue
          SET state='PROCESSING',attempt_count=attempt_count+1,
          lease_epoch=?,updated_utc=?
          WHERE owner_uid=? AND source_sha256=?''',
          (time.time(),_utc(),owner,digest))
        return owner,digest,payload,attempts+1


def _record(owner_uid, source_sha, state, reviews, diagnostic=None):
    if state not in ('RETRY','COMMITTED','NO_ELIGIBLE_ROWS','REVIEW_REQUIRED'):
        raise ValueError('Unsupported outbox state')
    serialized = json.dumps(reviews, ensure_ascii=False, separators=(',',':'))
    with _connect() as con:
        con.execute('''UPDATE delivery_queue SET state=?,
          review_json=?,last_error=?,updated_utc=?,lease_epoch=0,
          payload=CASE WHEN ?='COMMITTED' THEN NULL ELSE payload END
          WHERE owner_uid=? AND source_sha256=?''',
          (state,serialized,diagnostic,_utc(),state,owner_uid,source_sha))


def _read_status(owner_uid, digest):
    with _connect() as con:
        row = con.execute('''SELECT state FROM delivery_queue
            WHERE owner_uid=? AND source_sha256=?''',(owner_uid,digest)).fetchone()
        return row[0] if row else None


def process_queued(digest, owner_uid, processor, classifier):
    """Deliver exactly one queued batch; retry DB errors, retain review records."""
    if not re.fullmatch('[a-f0-9]{64}',digest):
        raise ValueError('Invalid SHA-256')
    claimed = _claim(owner_uid,digest)
    if not claimed:
        status = _read_status(owner_uid,digest)
        if status in ('COMMITTED','NO_ELIGIBLE_ROWS','REVIEW_REQUIRED'):
            return 'ALREADY_RECORDED' if status=='COMMITTED' else status
        raise RuntimeError('Outbox row unavailable or temporarily processing')
    owner,source_sha,payload,_ = claimed
    try:
        reviews = classifier(payload)
        state = processor(payload)
        if state not in ('COMMITTED','ALREADY_RECORDED','NO_ELIGIBLE_ROWS'):
            raise RuntimeError('Unknown PostgreSQL write result')
    except (ValueError, TypeError) as exc:
        # Invalid source evidence needs review. No PostgreSQL row is invented.
        _record(owner,source_sha,'REVIEW_REQUIRED',[],type(exc).__name__)
        return 'REVIEW_REQUIRED'
    except Exception as exc:
        _record(owner,source_sha,'RETRY',[],type(exc).__name__)
        raise
    if state=='NO_ELIGIBLE_ROWS':
        _record(owner,source_sha,'NO_ELIGIBLE_ROWS',reviews)
        return state
    _record(owner,source_sha,'COMMITTED',reviews)
    return state


def recover_missing_receipts(limit=250):
    """Recover crash between original SQLite receipt and queue creation.

    Only private .xlsx files named by original receipt UUID and with matching
    SQLite receipt SHA-256 may be enqueued. Never reads production evidence.
    """
    root = _store()
    db_files = list(root.glob('*.sqlite3')) + list(root.glob('*.db')) + list(root.glob('*.sqlite'))
    recovered = 0
    for db_file in db_files:
        if db_file.name=='sbi_pg_delivery_outbox.sqlite3' or db_file.is_symlink():
            continue
        try:
            with sqlite3.connect('file:'+str(db_file)+'?mode=ro',uri=True,timeout=2) as con:
                columns = {r[1] for r in con.execute('PRAGMA table_info(receipts)')}
                if not {'id','owner_uid','sha256'}.issubset(columns):
                    continue
                records = con.execute('''SELECT id,owner_uid,sha256 FROM receipts
                  ORDER BY created_utc DESC LIMIT ?''',(limit,)).fetchall()
        except sqlite3.DatabaseError:
            continue
        for receipt,owner,digest in records:
            if not isinstance(receipt,str) or not re.fullmatch('[0-9a-f]{32}',receipt):
                continue
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
                continue
            if _read_status(owner,digest):
                continue
            source = root/(receipt+'.xlsx')
            if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES:
                continue
            payload = source.read_bytes()
            if hashlib.sha256(payload).hexdigest() != digest:
                continue
            queue_delivery(payload,owner)
            recovered += 1
    return recovered


def process_pending(processor, classifier, limit=10):
    completed=0
    for _ in range(limit):
        claimed=_claim()
        if not claimed:
            break
        owner,digest,payload,_=claimed
        try:
            reviews=classifier(payload)
            state=processor(payload)
            if state not in ('COMMITTED','ALREADY_RECORDED','NO_ELIGIBLE_ROWS'):
                raise RuntimeError('Invalid PostgreSQL result')
            _record(owner,digest,'NO_ELIGIBLE_ROWS' if state=='NO_ELIGIBLE_ROWS' else 'COMMITTED',reviews)
            completed += 1
        except (ValueError, TypeError) as exc:
            _record(owner,digest,'REVIEW_REQUIRED',[],type(exc).__name__)
        except Exception as exc:
            _record(owner,digest,'RETRY',[],type(exc).__name__)
    return completed
