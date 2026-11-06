#!/usr/bin/env python3
"""SBI Phase 2B: GCP READ-ONLY discovery -> privacy-safe GitHub audit PR.

The ONLY GCP operations are 'list', 'describe', and 'get-iam-policy'.
Detailed IAM identities, emails, URLs, environment variables, access tokens,
financial data, and raw Google API responses are NEVER written to GitHub.
Use --upload to push ONLY the sanitized JSON to a separate GitHub branch.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT = "meghraj-reconciliation"
REGION = "asia-south1"
REPO = "sujitkumardolui154-ctrl/meghraj-reconciliation"
REGISTRY = "cloud-run-source-deploy"
PROD = ("sbi-dashboard", "sbi-supervisor-backend", "sbi-reconciliation-api")
STAGE = "sbi-owner-private-stage-v1"
API_NAMES = (
    "run.googleapis.com", "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com", "iam.googleapis.com",
)
# Only these two GCP service-account roles are meaningful to compare in memory.
# Do not publish account strings. An absent direct IAM binding never establishes
# absence of inherited or resource-level financial write permissions.
SENSITIVE_PATTERN = re.compile(
    r"@|https?://|-----BEGIN|github_pat_|ghp_|gho_|ghu_|ghs_|ghr_|"
    r"ya29\.|AIza|AKIA|AIza|Authorization:|Bearer |private_key|client_secret",
    re.IGNORECASE,
)


def invoke(argv, *, cwd=None, timeout=45):
    try:
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return (result.returncode == 0, result.stdout if result.returncode == 0 else "")


def gcloud_json(*args):
    success, output = invoke(["gcloud", *args, "--format=json"], timeout=60)
    if not success:
        return None
    try:
        return json.loads(output)
    except (ValueError, TypeError):
        return None


def nested(obj, *keys):
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def safe_status(v):
    return "PASS" if v is not None else "NOT_ACCESSIBLE_OR_NOT_FOUND"


def clean_ingress(value):
    # Never put an arbitrary provider or user-supplied string in GitHub.
    if value in ("all", "internal", "internal-and-cloud-load-balancing"):
        return value
    return "NOT_VERIFIED"


def known_service_record(detail, *, present=None):
    if detail is None:
        return {
            "exists": present if present is False else "NOT_VERIFIED",
            "ready_revision": "NOT_VERIFIED",
            "identity_configured": "NOT_VERIFIED",
            "ingress": "NOT_VERIFIED",
            "secret_reference_count": "NOT_VERIFIED",
        }
    metadata = detail.get("metadata") or {}
    spec = detail.get("spec") or {}
    template = nested(spec, "template", "spec") or {}
    annotations = metadata.get("annotations") or {}
    containers = template.get("containers") or []
    env = containers[0].get("env") or [] if containers else []
    secret_refs = sum(
        1 for item in env if isinstance(item, dict)
        and (
            nested(item, "valueFrom", "secretKeyRef")
            or nested(item, "valueSource", "secretKeyRef")
        )
    )
    revision = nested(detail, "status", "latestReadyRevisionName")
    # Revision names contain internal config details. Publish only existence.
    return {
        "exists": True,
        "ready_revision": bool(revision),
        "identity_configured": bool(template.get("serviceAccountName")),
        "ingress": clean_ingress(annotations.get("run.googleapis.com/ingress")),
        "secret_reference_count": secret_refs,
    }


def service_identity(detail):
    return nested(detail or {}, "spec", "template", "spec", "serviceAccountName")


def collect():
    checks = {}
    acct = gcloud_json("auth", "list", "--filter=status:ACTIVE")
    checks["active_identity_lookup"] = safe_status(acct)
    active = bool(acct) if isinstance(acct, list) else False

    project = gcloud_json("projects", "describe", PROJECT)
    checks["project_read"] = safe_status(project)
    projects_ok = nested(project or {}, "projectId") == PROJECT

    services = gcloud_json(
        "run", "services", "list",
        "--project=" + PROJECT, "--region=" + REGION,
    )
    checks["cloud_run_list"] = safe_status(services)
    service_by_name = {}
    if isinstance(services, list):
        service_by_name = {
            nested(s, "metadata", "name"): s
            for s in services if isinstance(s, dict)
        }
    targets = {}
    details = {}
    for name in (*PROD, STAGE):
        # If list denied, absence cannot be interpreted as NOT FOUND.
        present = name in service_by_name if isinstance(services, list) else None
        detail = (
            gcloud_json("run", "services", "describe", name,
                        "--project=" + PROJECT, "--region=" + REGION)
            if present is not False else None
        )
        details[name] = detail
        checks["cloud_run_read_" + name] = (
            "PASS" if detail is not None else
            "NOT_PRESENT" if present is False else "NOT_ACCESSIBLE_OR_NOT_FOUND"
        )
        targets[name] = known_service_record(detail, present=present)

    prod_id = service_identity(details.get(PROD[0]))
    stage_id = service_identity(details.get(STAGE))
    stage_distinct = (
        (stage_id != prod_id) if stage_id and prod_id
        else "NOT_VERIFIED"
    )

    stage_public = "NOT_VERIFIED"
    if details.get(STAGE):
        policy = gcloud_json(
            "run", "services", "get-iam-policy", STAGE,
            "--project=" + PROJECT, "--region=" + REGION,
        )
        checks["staging_iam_policy_read"] = safe_status(policy)
        if isinstance(policy, dict) and isinstance(policy.get("bindings", []), list):
            members = [
                principal for binding in policy.get("bindings", [])
                for principal in binding.get("members", [])
                if isinstance(principal, str)
            ]
            stage_public = (
                "PUBLIC_GRANT_PRESENT" if any(
                    p in ("allUsers", "allAuthenticatedUsers") for p in members
                ) else "NO_PUBLIC_GRANT_IN_SERVICE_POLICY"
            )
    else:
        checks["staging_iam_policy_read"] = "NOT_VERIFIED"

    service_accounts = gcloud_json(
        "iam", "service-accounts", "list", "--project=" + PROJECT
    )
    checks["service_account_inventory"] = safe_status(service_accounts)
    total_sas = len(service_accounts) if isinstance(service_accounts, list) else None
    stage_like_sas = None
    if isinstance(service_accounts, list):
        stage_like_sas = sum(
            bool(re.search(r"stage|preview|canary|readonly|read-only",
                           str(item.get("email", "")).split("@")[0], re.IGNORECASE))
            for item in service_accounts if isinstance(item, dict)
        )

    registry = gcloud_json(
        "artifacts", "repositories", "describe", REGISTRY,
        "--project=" + PROJECT, "--location=" + REGION,
    )
    checks["artifact_registry_read"] = safe_status(registry)
    registry_exists = (
        nested(registry or {}, "format") == "DOCKER"
        if registry is not None else "NOT_VERIFIED"
    )
    images = gcloud_json(
        "artifacts", "docker", "images", "list",
        f"{REGION}-docker.pkg.dev/{PROJECT}/{REGISTRY}",
        "--project=" + PROJECT, "--limit=200",
    )
    checks["registry_images_list"] = safe_status(images)
    # This is an upper-bound sample count, NOT full repository completeness.
    image_count_sample = len(images) if isinstance(images, list) else None

    apis = gcloud_json("services", "list", "--enabled", "--project=" + PROJECT)
    checks["enabled_apis_read"] = safe_status(apis)
    enabled_names = set()
    if isinstance(apis, list):
        enabled_names = {
            item.get("config", {}).get("name")
            for item in apis if isinstance(item, dict)
        }
    api_flags = {
        name: (name in enabled_names) if isinstance(apis, list) else "NOT_VERIFIED"
        for name in API_NAMES
    }

    # STRICT ALLOWLIST: all human identities, raw policies, URLs, env values,
    # cloud response bytes, invoices, financial records remain in memory only.
    result = {
        "schema": "SBI_PHASE2_CLOUD_READINESS_SANITIZED_V1",
        "collected_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "authorized_cloud_shell_read_only",
        "project": PROJECT,
        "region": REGION,
        "active_gcloud_identity_present": active,
        "project_access_verified": projects_ok,
        "checks": checks,
        "service_count": len(services) if isinstance(services, list) else None,
        "expected_services": targets,
        "staging_account_distinct_from_dashboard_account": stage_distinct,
        "staging_service_public_invoker_policy": stage_public,
        "service_accounts_total_count": total_sas,
        "service_accounts_staging_like_count": stage_like_sas,
        "registry": {
            "expected_repository": REGISTRY,
            "docker_format_verified": registry_exists,
            "listed_image_sample_count_max_200": image_count_sample,
            "new_source_image_digest": "NOT_VERIFIED",
        },
        "api_enabled": api_flags,
        "deployment_gates": {
            "dedicated_staging_service_account_no_finance_writes": "NOT_VERIFIED",
            "inherited_and_resource_finance_iam_grants": "NOT_VERIFIED",
            "staging_only_container_digest_pushed": "NOT_VERIFIED",
            "live_authenticated_cloud_run_response": "NOT_VERIFIED",
            "financial_data_parity": "NOT_VERIFIED",
            "backup_isolated_restore": "NOT_VERIFIED",
            "production_traffic_unchanged": "NOT_VERIFIED_BY_THIS_READ_ONLY_SCAN",
            "financial_database_writes_executed_by_script": 0,
            "production_cutover": "BLOCKED",
        },
    }
    return result


def render(report):
    out = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if SENSITIVE_PATTERN.search(out):
        raise ValueError("BLOCKED_SENSITIVE_DATA_IN_SANITIZED_REPORT")
    return out


def exact_repo_git_root():
    ok, path = invoke(["git", "rev-parse", "--show-toplevel"])
    if not ok:
        raise RuntimeError("Run this script from the SBI Git repository checkout")
    root = Path(path.strip()).resolve()
    ok, origin = invoke(["git", "-C", str(root), "remote", "get-url", "origin"])
    if not ok:
        raise RuntimeError("Git origin not configured")
    url = origin.strip().replace("\\", "/")
    if not re.fullmatch(
        r"(?:https://github[.]com/|git@github[.]com:)"
        + re.escape(REPO) + r"(?:[.]git)?", url
    ):
        raise RuntimeError("BLOCKED_NON_APPROVED_GITHUB_ORIGIN")
    return root


def upload_to_github(root, report_path, report_name):
    # Branch-based upload never writes to 'main'. No arbitrary local files
    # are staged; git pushes only the selected sanitized JSON in a worktree.
    ok, _ = invoke(["git", "-C", str(root), "fetch", "--quiet", "origin", "main"])
    if not ok:
        raise RuntimeError("Git fetch failed. Check your GitHub read permissions")
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    branch = "audit/sbi-phase2-gcp-readiness-" + utc
    with tempfile.TemporaryDirectory(prefix="sbi-cloud-git-") as folder:
        checkout = Path(folder) / "checkout"
        cmd = ["git", "-C", str(root), "worktree", "add", "--quiet",
               "-b", branch, str(checkout), "origin/main"]
        ok, _ = invoke(cmd)
        if not ok:
            raise RuntimeError("Failed to create isolated audit worktree")
        try:
            target = checkout / "audit" / "cloud" / report_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(report_path.read_bytes())
            ok, _ = invoke(["git", "-C", str(checkout), "add", "--",
                             "audit/cloud/" + report_name])
            if not ok:
                raise RuntimeError("Unable to stage sanitized report")
            ok, _ = invoke([
                "git", "-C", str(checkout),
                "-c", "user.name=SBI Phase2 Cloud Shell Inventory",
                "-c", "user.email=phase2-inventory@users.noreply.github.com",
                "commit", "--quiet", "-m",
                "audit(cloud): safe Phase 2 staging inventory without credentials",
            ])
            if not ok:
                raise RuntimeError("Could not commit sanitized report")
            ok, _ = invoke([
                "git", "-C", str(checkout), "push", "--quiet",
                "--set-upstream", "origin", branch,
            ], timeout=120)
            if not ok:
                raise RuntimeError(
                    "GitHub push failed. Your local sanitized report is saved."
                    " Use existing GitHub sign-in; never paste a PAT in chat."
                )
            compare = (
                "https://github.com/" + REPO
                + "/compare/main..." + branch + "?expand=1"
            )
            # PR creation is optional. Branch upload already satisfies import.
            gh_ok, _ = invoke(["gh", "auth", "status"], timeout=12)
            if gh_ok:
                ok, output = invoke([
                    "gh", "pr", "create", "--base", "main", "--head", branch,
                    "--draft", "--title",
                    "SBI Phase 2: sanitized GCP readiness report",
                    "--body",
                    "Read-only Cloud Shell inventory. No credentials, account "
                    "addresses, IAM policy members, endpoints, secret env "
                    "values, finance rows or financial approval. "
                    "All unverified release gates remain blocked.",
                ], cwd=checkout, timeout=45)
                if ok and output.strip().startswith("https://github.com/"):
                    return branch, output.strip()
            return branch, compare
        finally:
            invoke(["git", "-C", str(root), "worktree",
                    "remove", "--force", str(checkout)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upload", action="store_true",
        help="Commit and push sanitized JSON on NEW GitHub audit branch")
    args = parser.parse_args()
    if not shutil_which("gcloud"):
        print("BLOCKED: gcloud CLI is required in Cloud Shell", file=sys.stderr)
        return 2
    try:
        root = exact_repo_git_root()
        report = collect()
        text = render(report)
        utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = Path.home() / "sbi_phase2_private_inventory"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(folder, 0o700)
        name = "SBI_PHASE2_GCP_READINESS_" + utc + ".json"
        path = folder / name
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        print("PHASE2_SAFE_INVENTORY=CREATED")
        print("LOCAL_SANITIZED_REPORT=" + str(path))
        print("GCP_PROJECT_READ=" + report["checks"]["project_read"])
        print("CLOUD_RUN_LIST=" + report["checks"]["cloud_run_list"])
        print("ARTIFACT_REGISTRY_READ=" + report["checks"]["artifact_registry_read"])
        print("ACTIVE_GCP_IDENTITY_PRESENT=" + str(report["active_gcloud_identity_present"]))
        print("FINANCIAL_WRITES=0; PRODUCTION_RELEASE=BLOCKED")
        if args.upload:
            branch, link = upload_to_github(root, path, name)
            print("GITHUB_SANITIZED_UPLOAD=SUCCESS")
            print("GITHUB_AUDIT_BRANCH=" + branch)
            print("GITHUB_REVIEW_URL=" + link)
        else:
            print("GITHUB_UPLOAD=NOT_REQUESTED; use --upload")
    except Exception as e:
        print("BLOCKED: " + str(e), file=sys.stderr)
        return 2
    return 0


def shutil_which(name):
    # Avoid needing a third-party package or dependency.
    from shutil import which
    return which(name)


if __name__ == "__main__":
    raise SystemExit(main())
