"""Fail-closed approval validator for private reporting staging; no cloud calls."""
import json
import os
import re
import sys

_SHA = re.compile(r"^[a-f0-9]{64}$")

def approved(raw, commit_sha):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(value, dict):
        return False
    return (
        isinstance(commit_sha, str) and bool(_SHA.fullmatch(commit_sha))
        and value.get("release_scope") == "reporting_only"
        and value.get("decision") == "APPROVED_FOR_PRIVATE_STAGING"
        and value.get("source_sha") == commit_sha
        and isinstance(value.get("dataset_sha256"), str)
        and bool(_SHA.fullmatch(value["dataset_sha256"]))
        and isinstance(value.get("reviewer"), str)
        and bool(value["reviewer"].strip())
        and value.get("private_evidence_verified") is True
        and value.get("financial_execution") == "RESTRICTED"
        and value.get("production_traffic_change") is False
        and value.get("financial_database_writes") is False
    )

if __name__ == "__main__":
    if approved(os.environ.get("REPORTING_APPROVAL_JSON", ""), os.environ.get("GITHUB_SHA", "")):
        print("PRIVATE_REPORTING_APPROVAL=PASS")
    else:
        print("PRIVATE_REPORTING_APPROVAL=BLOCKED")
        sys.exit(2)
