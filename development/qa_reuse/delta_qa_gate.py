#!/usr/bin/env python3
"""SBI R31.14 separate Development QA module: reuse verified tests, run only delta.

READ ONLY. This program plans needed QA; it NEVER dispatches workflows,
changes databases/Caddy/Firebase/DNS, or grants production release.
Trust existing GitHub QA only after matching workflow, exact executed SHA,
successful *latest* run, and identical code blob IDs on the candidate HEAD.
Synthetic tests never substitute for a real external HTTPS/mTLS acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("evidence_registry.json")
REPOSITORY = "sujitkumardolui154-ctrl/meghraj-reconciliation"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
BLOB40 = SHA40
SAFE_ID = re.compile(r"^[a-z0-9_]{3,90}$")
RUN_FILE = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")


class GateError(RuntimeError):
    pass


def git(*args: str, root: Path = ROOT) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise GateError("GIT_READ_ONLY_CHECK_FAILED") from None
    return r.stdout.strip()


def checked_source(expected_sha: str, root: Path = ROOT) -> None:
    if not SHA40.fullmatch(expected_sha):
        raise GateError("EXPECTED_SHA_INVALID")
    if git("rev-parse", "HEAD", root=root) != expected_sha:
        raise GateError("SOURCE_COMMIT_CHANGED")
    if git("status", "--porcelain", root=root):
        raise GateError("SOURCE_UNCOMMITTED_OR_UNTRACKED")


def load_registry(path: Path = REGISTRY) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 32768:
        raise GateError("REGISTRY_UNAVAILABLE")
    try:
        content = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise GateError("REGISTRY_INVALID_JSON") from None
    if (type(content) is not dict
            or content.get("schema") != "SBI-CROSS-MODULE-QA-REUSE-V1"
            or type(content.get("source_evidence")) is not list
            or len(content["source_evidence"]) != 3
            or type(content.get("remaining_live_gates")) is not list
            or len(content["remaining_live_gates"]) != 7
            or content.get("release", {}).get("financial_apply") != "LOCKED"
            or content.get("release", {}).get("production_release") != "BLOCKED"
            or content.get("release", {}).get("external_mtls") != "NOT_TESTED"):
        raise GateError("REGISTRY_SECURITY_SCOPE_CHANGED")
    seen = set()
    for row in content["source_evidence"]:
        if type(row) is not dict or not SAFE_ID.fullmatch(str(row.get("id"))):
            raise GateError("EVIDENCE_ENTRY_INVALID")
        if row["id"] in seen:
            raise GateError("EVIDENCE_DUPLICATED")
        seen.add(row["id"])
        if (type(row.get("workflow_run_id")) is not int
                or row["workflow_run_id"] < 1
                or not RUN_FILE.fullmatch(str(row.get("workflow_file")))
                or not SHA40.fullmatch(str(row.get("executed_sha")))
                or not isinstance(row.get("workflow_name"), str)
                or not row["workflow_name"]
                or type(row.get("source_blobs")) is not dict
                or not row["source_blobs"]):
            raise GateError("EVIDENCE_ENTRY_INVALID")
        for path, sha in row["source_blobs"].items():
            if (type(path) is not str or not path
                    or path.startswith("/") or ".." in path.split("/")
                    or not BLOB40.fullmatch(str(sha))):
                raise GateError("EVIDENCE_SOURCE_BLOB_INVALID")
    if seen != {"synthetic_mtls_4j", "dns_owner_4o_design", "pki_4p_design"}:
        raise GateError("REQUIRED_EVIDENCE_MISSING")
    return content


def current_blobs(entry: dict, root: Path = ROOT) -> bool:
    """All relevant sources must be byte-identical, not just same test names."""
    for path, executed_blob_sha in entry["source_blobs"].items():
        try:
            now = git("rev-parse", "--verify", "HEAD:" + path, root=root)
        except GateError:
            return False
        if now != executed_blob_sha:
            return False
    return True


def github_runs_for_exact_sha(entry: dict, repo: str = REPOSITORY) -> list[dict]:
    """GET only, no dispatch, log, token, credential or workflow mutation."""
    if repo != REPOSITORY:
        raise GateError("REPOSITORY_NOT_APPROVED")
    path = quote(entry["workflow_file"], safe="")
    url = ("https://api.github.com/repos/" + repo
           + "/actions/workflows/" + path + "/runs?head_sha="
           + entry["executed_sha"] + "&per_page=100")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sbi-cross-module-qa-delta/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, method="GET", headers=headers), timeout=15) as response:
            if response.status != 200:
                raise GateError("GITHUB_EVIDENCE_NOT_AVAILABLE")
            data = json.load(response)
    except GateError:
        raise
    except Exception:
        # Do not disclose network errors that may include auth metadata.
        raise GateError("GITHUB_EVIDENCE_NOT_AVAILABLE") from None
    if type(data) is not dict or type(data.get("workflow_runs")) is not list:
        raise GateError("GITHUB_EVIDENCE_FORMAT_INVALID")
    return data["workflow_runs"]


def latest_workflow_verified(entry: dict, runs: list[dict]) -> bool:
    """Pinned completed pass must exist; a newer failure invalidates reuse."""
    candidates = [
        x for x in runs if type(x) is dict
        and x.get("head_sha") == entry["executed_sha"]
        and x.get("name") == entry["workflow_name"]
        and type(x.get("id")) is int
    ]
    if not candidates:
        return False
    pinned = [x for x in candidates if x["id"] == entry["workflow_run_id"]]
    if len(pinned) != 1 or pinned[0].get("conclusion") != "success" or pinned[0].get("status") != "completed":
        return False
    latest = max(candidates, key=lambda x: x["id"])
    return latest.get("status") == "completed" and latest.get("conclusion") == "success"


def decision(entry: dict, *, source_matches: bool, runs: list[dict] | None) -> str:
    if not source_matches:
        return "TARGETED_SOURCE_QA_REQUIRED"
    if runs is None:
        return "GITHUB_EVIDENCE_UNVERIFIED"
    return ("REUSE_EXACT_SOURCE_GITHUB_PASS"
            if latest_workflow_verified(entry, runs)
            else "REVIEW_OR_TARGETED_QA_REQUIRED")


def build_plan(registry: dict, status: dict[str, str]) -> dict:
    if set(status) != {entry["id"] for entry in registry["source_evidence"]}:
        raise GateError("QA_STATUS_INCOMPLETE")
    return {
        "schema": "SBI-R31.14-DELTA-QA-PLAN-V1",
        "per_test_decisions": status,
        "reused_existing_qa": sorted(k for k, v in status.items()
                                    if v == "REUSE_EXACT_SOURCE_GITHUB_PASS"),
        "targeted_source_qa": sorted(k for k, v in status.items()
                                     if v == "TARGETED_SOURCE_QA_REQUIRED"),
        "unverified_or_review": sorted(k for k, v in status.items()
                                      if v in ("GITHUB_EVIDENCE_UNVERIFIED",
                                               "REVIEW_OR_TARGETED_QA_REQUIRED")),
        "prior_private_firebase_to_pg": "PRIOR_OPERATOR_EVIDENCE_SCOPE_ONLY_NOT_EXTERNAL",
        "separate_migration_safety": "KNOWN_GITHUB_FAILURE_REVIEW_REQUIRED",
        "remaining_external_mtls_release_gates": list(registry["remaining_live_gates"]),
        "additional_workflows_dispatched": 0,
        "external_mtls": "NOT_TESTED",
        "financial_apply": "LOCKED",
        "production_deployment": "NOT_AUTHORIZED",
        "production_release": "BLOCKED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="R31.14 cross-module QA evidence reuse")
    p.add_argument("--source-sha", required=True)
    p.add_argument("--check-github", action="store_true",
                   help="Read-only check of recorded GitHub workflow runs")
    args = p.parse_args(argv)
    print("=== DB-R31.14 CROSS-MODULE DELTA QA PRE-EXECUTION GATE ===", flush=True)
    try:
        checked_source(args.source_sha)
        data = load_registry()
        status = {}
        for row in data["source_evidence"]:
            matching = current_blobs(row)
            runs = github_runs_for_exact_sha(row) if args.check_github and matching else None
            status[row["id"]] = decision(
                row, source_matches=matching, runs=runs
            )
        plan = build_plan(data, status)
        for k, v in status.items():
            print("DB_R31_14_" + k.upper() + "=" + v, flush=True)
        print("DB_R31_14_REUSED_QA=" + str(len(plan["reused_existing_qa"])), flush=True)
        print("DB_R31_14_TARGETED_QA=" + str(len(plan["targeted_source_qa"])), flush=True)
        print("DB_R31_14_UNVERIFIED_OR_REVIEW=" + str(len(plan["unverified_or_review"])),
              flush=True)
        print("DB_R31_14_LIVE_GATES_PENDING=" +
              str(len(plan["remaining_external_mtls_release_gates"])), flush=True)
        print("DB_R31_14_PRIVATE_MIGRATION_SAFETY=REVIEW_KNOWN_GITHUB_FAILURE", flush=True)
        print("DB_R31_14_EXTERNAL_HTTPS_MTLS=NOT_TESTED", flush=True)
        print("DB_R31_14_FINANCIAL_APPLY=LOCKED", flush=True)
        print("DB_R31_14_PRODUCTION_RELEASE=BLOCKED", flush=True)
        if plan["unverified_or_review"] or not args.check_github:
            print("STOP=DB_R31_14_GITHUB_EVIDENCE_OR_TARGETED_QA_REVIEW_REQUIRED", flush=True)
            return 2
        print("DB_R31_14_DEVELOPMENT_QA_PRECHECK=PASS_REUSE_AND_DELTA_PLAN_ONLY",
              flush=True)
        return 0
    except GateError as error:
        # Codes are hard-coded; no raw GitHub errors or customer data.
        print("STOP=DB_R31_14_" + str(error), flush=True)
        return 2
    except Exception:
        print("STOP=DB_R31_14_UNEXPECTED_READONLY_AUDIT_FAILURE", flush=True)
        return 2
    finally:
        print("DB_R31_14_EXTERNAL_LIVE_ACCEPTANCE=BLOCKED_PENDING_REAL_APPROVALS",
              flush=True)
        print("DB_R31_14_FINANCIAL_APPLY=LOCKED", flush=True)
        print("DB_R31_14_PRODUCTION_RELEASE=BLOCKED", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
