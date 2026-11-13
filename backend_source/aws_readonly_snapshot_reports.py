"""Fail-closed AWS Phase 1 read-only, private immutable CSV report snapshot adapter.

No network clients, financial database imports, financial writes, or background
syncs. A private manifest must be pinned to an independent SHA256 from the
authorized operator, and each CSV is independently hashed and structurally
checked before disclosure. If no approved snapshot is mounted, the existing
AWS backend stays disconnected (HTTP 503).
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

KINDS = frozenset((
    "unpaid", "ok", "balance-review", "suspense",
    "credit-note", "reconciliation-changes",
))
CORE = frozenset(("unpaid", "ok", "balance-review"))
MAX_MANIFEST = 64 * 1024
MAX_REPORT_BYTES = 48 * 1024 * 1024
MAX_REPORT_ROWS = 20_000
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


class NotCertified(ValueError):
    """Publicly safe fail-closed reason with no path, customer or secret data."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_file(path, max_size):
    # Never follow a symlink from the selected path (including the mount root).
    if path.is_symlink() or path.parent.is_symlink():
        raise NotCertified("SNAPSHOT_PATH_UNSAFE")
    try:
        descriptor = os.open(
            str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_size):
                raise NotCertified("SNAPSHOT_FILE_INVALID")
            raw = stream.read(max_size + 1)
            if len(raw) != info.st_size:
                raise NotCertified("SNAPSHOT_FILE_CHANGED")
            return raw
    except NotCertified:
        raise
    except (OSError, ValueError):
        raise NotCertified("SNAPSHOT_FILE_UNAVAILABLE") from None


def _instant(value):
    if not isinstance(value, str):
        raise NotCertified("SNAPSHOT_APPROVAL_TIME_INVALID")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise NotCertified("SNAPSHOT_APPROVAL_TIME_INVALID") from None
    if parsed.tzinfo is None:
        raise NotCertified("SNAPSHOT_APPROVAL_TIME_INVALID")
    return parsed.astimezone(dt.timezone.utc)


def _load_manifest():
    root_name = os.environ.get("SBI_AWS_REPORT_SNAPSHOT_DIR", "")
    expected = os.environ.get("SBI_AWS_REPORT_MANIFEST_SHA256", "")
    if not root_name or not SHA_RE.fullmatch(expected):
        raise NotCertified("REPORT_DATA_NOT_CONNECTED")
    root = Path(root_name)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise NotCertified("SNAPSHOT_PATH_UNSAFE")
    raw = _safe_file(root / "manifest.json", MAX_MANIFEST)
    if _sha(raw) != expected:
        raise NotCertified("SNAPSHOT_MANIFEST_HASH_MISMATCH")
    try:
        manifest = json.loads(raw)
    except (UnicodeError, ValueError):
        raise NotCertified("SNAPSHOT_MANIFEST_INVALID") from None
    if not isinstance(manifest, dict):
        raise NotCertified("SNAPSHOT_MANIFEST_INVALID")
    if (manifest.get("schema") != "sbi-aws-phase1-private-snapshot/v1"
            or manifest.get("release_class") != "REPORTING_ONLY"
            or manifest.get("approval_status") != "INDEPENDENTLY_APPROVED"
            or manifest.get("financial_writes_disabled") is not True
            or manifest.get("reconciliation_executed") is not False):
        raise NotCertified("SNAPSHOT_APPROVAL_REQUIRED")
    if not SHA_RE.fullmatch(str(manifest.get("source_sha256", ""))):
        raise NotCertified("SNAPSHOT_SOURCE_HASH_REQUIRED")
    if not RECEIPT_RE.fullmatch(str(manifest.get("approval_receipt_id", ""))):
        raise NotCertified("SNAPSHOT_APPROVAL_RECEIPT_REQUIRED")
    issued = _instant(manifest.get("approved_at_utc"))
    expires = _instant(manifest.get("expires_at_utc"))
    now = dt.datetime.now(dt.timezone.utc)
    if not (issued <= now < expires and
            dt.timedelta(0) < expires - issued <= dt.timedelta(days=30)):
        raise NotCertified("SNAPSHOT_APPROVAL_EXPIRED")
    reports = manifest.get("reports")
    if not isinstance(reports, dict) or not reports or not set(reports) <= KINDS:
        raise NotCertified("SNAPSHOT_REPORT_INDEX_INVALID")
    return root, manifest


def _validated_csv(root, kind, entry, *, include_bytes):
    if not isinstance(entry, dict):
        raise NotCertified("SNAPSHOT_REPORT_INDEX_INVALID")
    # The path is derived from the route allowlist, never from the manifest.
    if entry.get("file") != kind + ".csv":
        raise NotCertified("SNAPSHOT_FILE_NAME_MISMATCH")
    if not SHA_RE.fullmatch(str(entry.get("sha256", ""))):
        raise NotCertified("SNAPSHOT_REPORT_HASH_REQUIRED")
    count = entry.get("row_count")
    columns = entry.get("column_count")
    if type(count) is not int or not (0 <= count <= MAX_REPORT_ROWS):
        raise NotCertified("SNAPSHOT_ROW_COUNT_INVALID")
    if type(columns) is not int or not (1 <= columns <= 100):
        raise NotCertified("SNAPSHOT_COLUMN_COUNT_INVALID")
    if kind in CORE | {"suspense"} and columns != 53:
        raise NotCertified("SNAPSHOT_53_COLUMN_PARITY_REQUIRED")
    if kind == "credit-note" and columns != 18:
        raise NotCertified("SNAPSHOT_18_COLUMN_PARITY_REQUIRED")
    if entry.get("classification") != "SOURCE_REFERENCE_ONLY":
        raise NotCertified("SNAPSHOT_REPORT_CLASS_INVALID")
    headers = entry.get("headers")
    if not isinstance(headers, list) or len(headers) != columns or not all(
        isinstance(x, str) and x.strip() for x in headers
    ) or len(headers) != len(set(headers)):
        raise NotCertified("SNAPSHOT_HEADERS_INVALID")
    # A pinned manifest must NOT be able to invent its own approved headers.
    # Match a separately operator-pinned approved source-header digest.
    header_pin_env = (
        "SBI_AWS_APPROVED_53_HEADERS_SHA256"
        if kind in CORE | {"suspense"} else
        "SBI_AWS_APPROVED_18_HEADERS_SHA256"
        if kind == "credit-note" else
        "SBI_AWS_APPROVED_" + kind.replace("-", "_").upper() + "_HEADERS_SHA256"
    )
    header_pin = os.environ.get(header_pin_env, "")
    header_bytes = json.dumps(
        headers, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if not SHA_RE.fullmatch(header_pin) or _sha(header_bytes) != header_pin:
        raise NotCertified("INDEPENDENT_HEADER_CONTRACT_NOT_VERIFIED")
    raw = _safe_file(root / (kind + ".csv"), MAX_REPORT_BYTES)
    if _sha(raw) != entry["sha256"]:
        raise NotCertified("SNAPSHOT_REPORT_HASH_MISMATCH")
    try:
        text = raw.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        actual_headers = next(reader)
        if actual_headers != headers:
            raise NotCertified("SNAPSHOT_HEADER_MISMATCH")
        rows = 0
        for row in reader:
            if len(row) != columns:
                raise NotCertified("SNAPSHOT_ROW_WIDTH_MISMATCH")
            # Refuse CSV cells which would execute as spreadsheet formulas.
            # Source exports must escape these as leading apostrophes.
            for value in row:
                if value.lstrip().startswith(("=", "+", "-", "@")):
                    raise NotCertified("SNAPSHOT_CSV_FORMULA_NOT_ESCAPED")
            rows += 1
            if rows > MAX_REPORT_ROWS:
                raise NotCertified("SNAPSHOT_ROW_COUNT_INVALID")
        if rows != count:
            raise NotCertified("SNAPSHOT_ROW_COUNT_MISMATCH")
    except (UnicodeError, csv.Error, StopIteration):
        raise NotCertified("SNAPSHOT_CSV_INVALID") from None
    details = {
        "rows": count,
        "columns": columns,
        "classification": "SOURCE_REFERENCE_ONLY",
        "reconciliation_executed": False,
        "url": "/reports/" + kind + ".csv",
    }
    return details, (raw if include_bytes else None)


def load_snapshot(kind=None, *, require_core=False):
    """Load and verify sealed report(s); no cached authorizations or hashes."""
    root, manifest = _load_manifest()
    reports = manifest["reports"]
    if kind is not None and kind not in KINDS:
        raise NotCertified("REPORT_NOT_APPROVED")
    if kind is not None and kind not in reports:
        raise NotCertified("REPORT_DATA_NOT_CERTIFIED")
    if require_core and not CORE <= reports.keys():
        raise NotCertified("REPORT_DATA_NOT_CERTIFIED")
    if "credit-note" in reports and manifest.get("credit_note_conflicts_resolved") is not True:
        # Do not allow a financial Credit Note export that papers over
        # the known historic conflicts awaiting source-level review.
        if kind == "credit-note":
            raise NotCertified("CREDIT_NOTE_CONFLICTS_PENDING_REVIEW")
        reports = {k: v for k, v in reports.items() if k != "credit-note"}
    selected = [kind] if kind is not None else sorted(reports)
    index = {}
    payload = None
    for name in selected:
        entry, data = _validated_csv(
            root, name, reports[name], include_bytes=(name == kind)
        )
        index[name] = entry
        if name == kind:
            payload = data
    if require_core and not CORE <= index.keys():
        raise NotCertified("REPORT_DATA_NOT_CERTIFIED")
    return {
        "source": "PINNED_PRIVATE_SOURCE_REFERENCE",
        "approval_receipt_id": manifest["approval_receipt_id"],
        "source_sha256": manifest["source_sha256"],
        "financial_execution_enabled": False,
        "reconciliation_executed": False,
        "reports": index,
    }, payload
