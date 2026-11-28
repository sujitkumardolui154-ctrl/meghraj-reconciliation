#!/usr/bin/env python3
"""SBI module QA planner: check exact-GitHub receipts BEFORE redundant QA.

Development QA is selected from changed paths, not an unconditional
combined 140-test rerun. Missing/failed evidence triggers the relevant tests;
UNKNOWN paths and unavailable diff fail closed to all relevant tests.
Production release and financial Apply gates are NEVER satisfied by this script.

No Github writes, changes to bank records, migrations, tokens or cloud deploys.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

GROUPS = (
    "invoice_db", "invoice_ui", "credit_note", "historical",
    "private_sources", "branch_master", "gst",
)
ALL_GROUPS = frozenset(GROUPS)
WORKFLOW = ".github/workflows/sbi-invoice-gst-combined-qa.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def qa_groups_for_path(path):
    """Conservative dependency-aware mapping. None = needs ALL QA.

    A missing path mapping is not permission to skip an unknown change.
    """
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
        return None
    if path.startswith(("docs/", "README", "staging/invoice-gst/APPROVED_")) and path.endswith((".md", ".txt")):
        return set()
    if path.startswith(".github/workflows/"):
        if path == WORKFLOW:
            return set(ALL_GROUPS)
        return set()  # Other workflow owns its own checks.
    if path.startswith(("tools/qa_module_policy.py", "tests/test_qa_module_policy.py")):
        return set()  # Own separate QA-policy workflow handles this.
    if path.startswith("staging/invoice-gst/"):
        return set(ALL_GROUPS)  # schema/vendor/master: shared financial surface
    if path in (
        "dashboard_source/production_gateway.py",
        "dashboard_source/dashboard_sessions.py",
        "dashboard_source/requirements.txt",
    ):
        return set(ALL_GROUPS)
    if path == "dashboard_source/index.html":
        return {"invoice_db", "invoice_ui", "credit_note", "private_sources"}
    if path in ("dashboard_source/invoice_gst_ui.js", "dashboard_source/invoice_annexure_intake.py"):
        return {"invoice_db", "invoice_ui"}
    if path.startswith("dashboard_source/invoice_gst_"):
        return {"invoice_db", "invoice_ui", "private_sources", "branch_master", "gst"}
    if path.startswith("dashboard_source/credit_note_"):
        return {"credit_note", "historical", "invoice_db"}
    if path.startswith("dashboard_source/test_credit_note_"):
        return {"historical", "credit_note"}
    if path.startswith("tests/test_credit_note_"):
        return {"credit_note", "historical"}
    if path == "tests/test_invoice_v2_qa.py":
        return {"invoice_ui", "invoice_db"}
    if path == "tests/test_invoice_gst_combined.py":
        return {"invoice_db", "invoice_ui"}
    if path.startswith("tests/test_invoice_gst_private_"):
        return {"private_sources", "invoice_db"}
    if path == "tests/test_invoice_gst_master_workbook_gate.py":
        return {"branch_master"}
    if path.startswith("scripts/sbi_invoice_gst_"):
        return {"private_sources", "invoice_db"}
    if path == "scripts/sbi_credit_note_history_catalog_preflight.py":
        return {"historical"}
    if path.startswith("staging/mxp-gst/"):
        return {"gst"}  # other dedicated Workstream D QA also owns this path
    if path.startswith(("staging/railway_public/", "staging/aws_lightsail/", "migration/")):
        return set()  # separate environment/migration workflow owns QA
    return None


def select_groups(changed, *, full=False):
    """Explicit full/release QA or unknown changes conservatively select all."""
    if full or changed is None:
        return list(GROUPS), ["FULL_OR_UNAVAILABLE_DIFF"]
    if not isinstance(changed, (list, tuple)):
        return list(GROUPS), ["INVALID_CHANGE_LIST"]
    selected = set()
    unknown = []
    for path in changed:
        groups = qa_groups_for_path(path)
        if groups is None:
            unknown.append(path)
        else:
            selected.update(groups)
    if unknown:
        return list(GROUPS), ["UNMAPPED_CHANGES_REQUIRE_FULL_QA"]
    return [g for g in GROUPS if g in selected], (
        ["MODULE_SCOPE_SELECTED"] if selected else ["NO_INVOICE_MODULE_CODE_CHANGED"]
    )


def prior_success_for_exact_sha(runs, sha, workflow_name=None, current_run_id=None):
    """Only a completed SUCCESS for this exact commit/workflow may be reused."""
    if not isinstance(runs, list) or not SHA_RE.fullmatch(str(sha)):
        return False
    candidates = [
        run for run in runs
        if isinstance(run, dict)
        and str(run.get("id")) != str(current_run_id)
        and run.get("head_sha") == sha
        and (not workflow_name or run.get("name") == workflow_name)
    ]
    if not candidates:
        return False
    # A newer failed/cancelled run supersedes an older PASS for the same
    # workflow/commit; prefer a failed-job-only rerun rather than a false PASS.
    latest = max(candidates, key=lambda r: int(r.get("id") or 0))
    return latest.get("status") == "completed" and latest.get("conclusion") == "success"


def github_runs(repo, workflow_file, sha, token="", timeout=8):
    """READ ONLY GitHub Actions receipt lookup, not a workflow dispatch/rerun."""
    if not REPO_RE.fullmatch(repo) or not SHA_RE.fullmatch(sha):
        raise ValueError("INVALID_REPO_OR_SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", workflow_file):
        raise ValueError("INVALID_WORKFLOW_NAME")
    target = (
        "https://api.github.com/repos/" + repo
        + "/actions/workflows/" + quote(workflow_file, safe="")
        + "/runs?head_sha=" + sha + "&per_page=100"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sbi-module-qa-preflight/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(target, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("GITHUB_QA_EVIDENCE_NOT_AVAILABLE")
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("INVALID_GITHUB_QA_EVIDENCE_RESPONSE")
    return payload["workflow_runs"]


def changed_files(base_sha, head_sha):
    if not SHA_RE.fullmatch(str(base_sha)) or not SHA_RE.fullmatch(str(head_sha)):
        return None
    try:
        raw = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRD",
             base_sha, head_sha, "--"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=12
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return sorted(set(raw.splitlines()))


def build_plan(changed, *, head_sha, github_evidence=None, workflow_exists=True,
               event="pull_request", current_run_id=None, full=False):
    groups, reasons = select_groups(changed, full=full)
    # A release request requires fresh acceptance of critical external gates.
    # A synthetic workflow PASS is not live financial-release authorization.
    release = event in ("deployment", "production_release")
    if release:
        groups = list(GROUPS)
        reasons = ["RELEASE_FRESH_EVIDENCE_MANDATORY"]
    reusable = (
        bool(groups) and workflow_exists and not release
        and prior_success_for_exact_sha(
            github_evidence if isinstance(github_evidence, list) else [],
            head_sha, "SBI invoice generation + GST combined QA (isolated)",
            current_run_id
        )
    )
    if not workflow_exists:
        reasons.append("REQUIRED_WORKFLOW_NOT_FOUND")
    if github_evidence is None:
        reasons.append("GITHUB_EXISTING_QA_NOT_VERIFIED_RUN_REQUIRED")
    elif reusable:
        reasons.append("EXACT_SHA_SUCCESS_EXISTS_REUSE_NOT_RERUN")
    elif groups:
        reasons.append("EXACT_SHA_REUSABLE_PASS_NOT_FOUND")
    return {
        "policy_version": "SBI_MODULE_QA_V1",
        "head_sha": head_sha,
        "phase": event,
        "changed_paths_count": len(changed) if changed is not None else None,
        "selected_groups": groups,
        "decision": (
            "BLOCK_REQUIRED_WORKFLOW_MISSING" if not workflow_exists else
            "REUSE_APPROVED_EXACT_SHA_QA" if reusable else
            "RUN_SELECTED_QA" if groups else "NO_INVOICE_QA_REQUIRED"
        ),
        "reused": reusable,
        "workflow_available": workflow_exists,
        "reason_codes": reasons,
        "financial_apply": "LOCKED",
        "production_deployment": "NOT_AUTHORIZED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--event", default="pull_request")
    parser.add_argument("--check-github", action="store_true")
    parser.add_argument("--full", action="store_true",
                        help="Explicit release/full combined QA (never skipped)")
    parser.add_argument("--github-output", default="")
    parser.add_argument("--changed-files", default="",
                        help="Optional newline-separated file list (for local CI QA)")
    args = parser.parse_args()
    head = args.head_sha or os.environ.get("GITHUB_SHA", "")
    if args.changed_files:
        paths = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
    else:
        paths = changed_files(args.base_sha, head)
    available = Path(WORKFLOW).is_file()
    evidence = None
    if args.check_github and available and args.repo and SHA_RE.fullmatch(head):
        try:
            evidence = github_runs(
                args.repo, Path(WORKFLOW).name, head,
                os.environ.get("GITHUB_TOKEN", "")
            )
        except (OSError, ValueError, HTTPError, URLError, RuntimeError):
            evidence = None  # FAIL CLOSED: run, don't declare a PASS
    plan = build_plan(
        paths, head_sha=head, github_evidence=evidence,
        workflow_exists=available,
        event=args.event, current_run_id=os.environ.get("GITHUB_RUN_ID"),
        full=args.full
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    if args.github_output:
        # GITHUB_OUTPUT is the only Actions channel: no secrets or PII.
        with open(args.github_output, "a", encoding="utf-8") as out:
            out.write("qa_reuse=" + str(plan["reused"]).lower() + "\n")
            out.write("qa_required=" +
                      str(plan["decision"] == "RUN_SELECTED_QA").lower() + "\n")
            for group in GROUPS:
                out.write(
                    group + "=" +
                    str(plan["decision"] == "RUN_SELECTED_QA"
                        and group in plan["selected_groups"]).lower() + "\n"
                )
    if not available:
        return 2  # no silently skipped required workflow
    return 0


if __name__ == "__main__":
    sys.exit(main())
