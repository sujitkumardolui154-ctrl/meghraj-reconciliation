"""Load the OWNER-APPROVED SBI SOL master from private SHA-pinned JSON.

No branch master content, bank details or credentials are kept in GitHub.
Ambiguous, revoked or unapproved SOL mappings never produce a branch name.
The historical correction queue is NOT a permanent ban; an approved 99922
mapping is accepted when the currently pinned master uniquely approves it.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
import re
import stat

SCHEMA = "sbi-private-approved-sol-master/v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SOL = re.compile(r"[0-9]{1,12}\Z")
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000


class PrivateSolMasterReview(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise PrivateSolMasterReview(code)


def normalized_sol(value):
    if type(value) is not str or _SOL.fullmatch(value) is None:
        return None
    return value.lstrip("0") or None


def load_approved_sol_file(filename, expected_sha256):
    """Return (approved sol->official name, verified actual SHA).

    A fully missing master is a safe review mode, but a half-configured or
    tampered master fails closed before any row ingestion begins.
    """
    if not filename and not expected_sha256:
        return {}, None
    require(type(filename) is str and filename and
            type(expected_sha256) is str and _HEX.fullmatch(expected_sha256),
            "SOL_MASTER_PATH_AND_SHA_REQUIRED")
    path=Path(filename)
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and not path.parent.is_symlink(),
            "SOL_MASTER_PRIVATE_PATH_REQUIRED")
    info=path.stat()
    require(stat.S_ISREG(info.st_mode) and
            0 < info.st_size <= MAX_BYTES and
            not (stat.S_IMODE(info.st_mode) & 0o077) and
            not (stat.S_IMODE(path.parent.stat().st_mode) & 0o022),
            "SOL_MASTER_PRIVATE_PERMISSIONS_REQUIRED")
    data=path.read_bytes()
    require(len(data) <= MAX_BYTES and
            sha256(data).hexdigest()==expected_sha256,
            "SOL_MASTER_BYTES_SHA_MISMATCH")
    try:
        doc=json.loads(data)
    except (ValueError,UnicodeDecodeError):
        raise PrivateSolMasterReview("SOL_MASTER_JSON_INVALID") from None
    require(type(doc) is dict and doc.get("schema")==SCHEMA and
            type(doc.get("branches")) is list and
            0<len(doc["branches"])<=MAX_ROWS,
            "SOL_MASTER_SCHEMA_UNAPPROVED")
    seen=defaultdict(set)
    blocked=set()
    for row in doc["branches"]:
        require(type(row) is dict and
                set(row)=={"sol_id","official_branch_name","approved"},
                "SOL_MASTER_ROW_SCHEMA_INVALID")
        sol=normalized_sol(row["sol_id"])
        official=row["official_branch_name"]
        require(sol is not None and type(official) is str and
                official.strip() and len(official) <= 180 and
                type(row["approved"]) is bool,
                "SOL_MASTER_ROW_DATA_INVALID")
        if row["approved"]:
            seen[sol].add(official.strip())
        else:
            blocked.add(sol)
    selected={sol:next(iter(names)) for sol,names in seen.items()
              if len(names)==1 and sol not in blocked}
    return selected, expected_sha256
