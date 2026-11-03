"""Fail-closed independent reporting-only private staging approval check.

No cloud, finance or database calls. The approval JSON must be injected from
protected GitHub secret, and is never printed or committed.
"""
import json
import os
import re
import sys

SHA256 = re.compile(r"^[0-9a-f]{64}$")

def approved(raw, commit_sha):
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return all((
        data.get("release_scope") == "reporting_only",
        data.get("decision") == "APPROVED_FOR_PRIVATE_STAGING",
        data.get("source_sha") == commit_sha,
        isinstance(commit_sha, str) and bool(SHA256.fullmatch(commit_sha)),
        isinstance(data.get("dataset_sha256"), str)
            and bool(SHA256.fullmatch(data["dataset_sha256"])),
        isinstance(data.get("reviewer"), str) and bool(data["reviewer"].strip()),
        data.get("private_evidence_verified") is True,
        data.get("financial_execution") == "RESTRICTED",
        data.get("production_traffic_change") is False,
        data.get("financial_database_writes") is False,
    ))

if __name__ == "__main__":
    if approved(os.getenv("REPORTING_APPROVAL_JSON", ""), os.getenv("GITHUB_SHA", "")):
        print("PRIVATE_REPORTING_APPROVAL=PASS")
    else:
        print("PRIVATE_REPORTING_APPROVAL=BLOCKED")
        sys.exit(2)
