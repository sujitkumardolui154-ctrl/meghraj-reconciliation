#!/usr/bin/env python3
"""Read-only *project-level* IAM survey for possible SBI staging identities.

Publishes only anonymous candidate counts and risk categories. Does NOT
establish absence of inherited/folder/org/resource-level finance privileges.
No account email, IAM member or role name is emitted in the sanitized report.
"""
import json
from pathlib import Path
import re
from datetime import datetime, timezone
import os
import sys

from collect_phase2_readiness import (
    PROJECT, gcloud_json, render, exact_repo_git_root, upload_to_github,
)

NAME_MARKERS = re.compile(r"stage|staging|preview|canary|readonly|read-only", re.I)
KNOWN_LOW_PRIVILEGE = {
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/artifactregistry.reader",
    "roles/run.invoker",
}
FINANCE_POTENTIAL = re.compile(
    r"datastore|firestore|firebase|editor|owner|storage|bigquery|secretmanager|"
    r"iam[.]|serviceusage[.]serviceUsageAdmin|cloudfunctions[.]admin",
    re.I,
)


def summarize(accounts, policy):
    if not isinstance(accounts, list):
        raise ValueError("SERVICE_ACCOUNT_LIST_NOT_VERIFIED")
    candidates = []
    for account in accounts:
        email = account.get("email") if isinstance(account, dict) else None
        if isinstance(email, str) and "@" in email and NAME_MARKERS.search(email.split("@")[0]):
            candidates.append(email.lower())
    candidates = sorted(set(candidates))
    bindings = policy.get("bindings") if isinstance(policy, dict) else None
    iam_read = isinstance(bindings, list)
    result = []
    for index, email in enumerate(candidates, start=1):
        direct = risky = nonallow = conditioned = 0
        if iam_read:
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                members = binding.get("members")
                if not isinstance(members, list) or "serviceAccount:" + email not in members:
                    continue
                role = binding.get("role", "")
                direct += 1
                if role not in KNOWN_LOW_PRIVILEGE:
                    nonallow += 1
                if not isinstance(role, str) or FINANCE_POTENTIAL.search(role):
                    risky += 1
                if "condition" in binding:
                    conditioned += 1
        result.append({
            "candidate_index": index,
            "direct_project_bindings_count": direct if iam_read else "NOT_VERIFIED",
            "potential_finance_or_privilege_bindings_count": risky if iam_read else "NOT_VERIFIED",
            "not_in_narrow_readonly_allowlist_count": nonallow if iam_read else "NOT_VERIFIED",
            "conditional_bindings_count": conditioned if iam_read else "NOT_VERIFIED",
            "inherited_and_resource_grants": "NOT_VERIFIED",
            "service_account_financial_write_denial_proven": False,
            "stage_identity_approved_for_deploy": False,
        })
    return {
        "schema": "SBI_PHASE2_STAGE_IAM_PROJECT_ONLY_V1",
        "collected_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project": PROJECT,
        "staging_name_candidates": len(candidates),
        "project_iam_policy_read": iam_read,
        "candidates": result,
        "identity_scope": "DIRECT_PROJECT_IAM_ONLY",
        "inherited_folder_org_resource_grants": "NOT_VERIFIED",
        "effective_firestore_financial_write_denial": "NOT_VERIFIED",
        "stage_iam_release": "BLOCKED_PENDING_EFFECTIVE_PERMISSIONS",
        "prod_traffic_or_iam_mutations": 0,
        "financial_database_writes": 0,
        "production_release": "BLOCKED",
    }


def main():
    if not Path.home().exists():
        raise SystemExit("HOME_DIRECTORY_UNAVAILABLE")
    root = exact_repo_git_root()
    accounts = gcloud_json("iam", "service-accounts", "list", "--project=" + PROJECT)
    policy = gcloud_json("projects", "get-iam-policy", PROJECT)
    result = summarize(accounts, policy)
    data = render(result)
    out_dir = Path.home() / "sbi_phase2_private_inventory"
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(out_dir, 0o700)
    name = "SBI_PHASE2_STAGE_IAM_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    out = out_dir / name
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    print("STAGE_IAM_PROJECT_POLICY_READ=" + str(result["project_iam_policy_read"]).upper())
    print("STAGE_LIKE_ACCOUNT_COUNT=" + str(result["staging_name_candidates"]))
    for x in result["candidates"]:
        print("CANDIDATE_" + str(x["candidate_index"]) + "_DIRECT_RISK_BINDINGS=" +
              str(x["potential_finance_or_privilege_bindings_count"]))
    print("EFFECTIVE_FINANCIAL_WRITE_DENIAL=NOT_VERIFIED")
    print("STAGE_IAM_RELEASE=BLOCKED_PENDING_EFFECTIVE_PERMISSIONS")
    print("LOCAL_SANITIZED_REPORT=" + str(out))
    if "--upload" in sys.argv[1:]:
        branch, link = upload_to_github(root, out, name)
        print("GITHUB_SANITIZED_UPLOAD=SUCCESS")
        print("GITHUB_REVIEW_URL=" + link)
    else:
        print("GITHUB_UPLOAD=NOT_REQUESTED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("BLOCKED: " + type(e).__name__ + " — " + str(e), file=sys.stderr)
        raise SystemExit(2)
