"""Read-only MXP GST alias resolution. Does not modify sources or financial records."""
from __future__ import annotations
import json
import re
from pathlib import Path

CONFIG = Path(__file__).parent / "config" / "approved_alias_rules_v2_7.json"
def normalize(value: str) -> str:
    """Conservative comparison key; does not perform fuzzy matching."""
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()

def resolve_name(raw: str, master: list[dict], config: dict | None = None) -> dict:
    """Resolve only unambiguous, exact official-name / approved alias candidates.

    master rows: Official Branch Name, SOL ID, Search Aliases (semicolon-separated).
    Never uses source row position. All non-unique hits require manual review.
    """
    cfg = config or json.loads(CONFIG.read_text(encoding="utf-8"))
    key = normalize(raw)
    if not key:
        return {"status": "REVIEW_REQUIRED", "reason": "SOURCE_BRANCH_MISSING"}
    generic = {normalize(x) for x in cfg["non_unique_names_require_context"]}
    if key in generic or re.fullmatch(r"RBO [IVX]+", key):
        return {"status": "REVIEW_REQUIRED", "reason": "INCOMPLETE_LOCATION_OR_RBO"}
    blocked = {(normalize(x["alias"]), x["wrong_sol"].zfill(5))
               for x in cfg["blocked_aliases"]}
    matches = []
    for entry in master:
        sol = str(entry.get("SOL ID", "")).strip().zfill(5)
        official = str(entry.get("Official Branch Name", "")).strip()
        exact = key == normalize(official)
        aliases = [a.strip() for a in str(entry.get("Search Aliases", "") or "").split(";") if a.strip()]
        alias_match = any(key == normalize(a) and (key, sol) not in blocked for a in aliases)
        if exact or alias_match:
            matches.append({"official_name": official, "sol_id": sol,
                            "method": "EXACT_OFFICIAL" if exact else "UNIQUE_APPROVED_ALIAS"})
    # Owner-approved overrides are only for *exact*, location-specific identities.
    special = [x for x in cfg["approved_specific"] if key == normalize(x["input"])]
    if len(special) == 1:
        x = special[0]
        return {"status": "APPROVED_SPECIFIC", "official_name": x["official_name"],
                "sol_id": x["sol_id"], "method": "OWNER_APPROVED_LOCATION_SPECIFIC"}
    unique = {(m["official_name"], m["sol_id"]):m for m in matches}
    if len(unique) == 1:
        return {"status": "MATCHED", **next(iter(unique.values()))}
    return {"status": "REVIEW_REQUIRED",
            "reason": "MULTIPLE_MASTER_MATCHES" if unique else "NO_VERIFIED_MASTER_MATCH"}
