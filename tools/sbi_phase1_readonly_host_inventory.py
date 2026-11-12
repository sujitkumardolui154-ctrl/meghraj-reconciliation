#!/usr/bin/env python3
"""SBI Phase 1 source-and-host inventory, NOT a deployment or QA substitute.

Read only Git/source, Docker container metadata and localhost health endpoints.
No financial data queries, authentication tokens, credential contents, cloud
API calls, container execs, builds, releases or changes to existing containers.
The only write is a NEW owner-requested JSON evidence report.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

APPROVED_MAIN = "13727fcae5104267b2f6270224dc41c4bb0caae9"
MAIN_BLOBS = {
    "dashboard_source/production_gateway.py": "14cbd76cf6fb6f2d32a27c7a8c50fe956a49d5bd",
    "dashboard_source/dashboard_sessions.py": "de5656b33e0b4ff56e82086474c855316162a10e",
    "dashboard_source/dashboard_login_pages.py": "fab6575742a1ed643e35379d5793f74b8b56d82a",
    "dashboard_source/sbi_credit_report_auth.py": "31b6cd3a01f43859da3c9c9dc79e35282f695925",
    "backend_source/report_api.py": "73d2a83b44b25209979e0f89bc0f7c7967b8aad1",
}
LOCAL_HEALTH = (
    ("aws_readonly_health", "http://127.0.0.1:18086/healthz"),
    ("aws_readonly_ready", "http://127.0.0.1:18086/readyz"),
    ("legacy_private_health", "http://127.0.0.1:18082/healthz"),
    ("temporary_cn_staging", "http://127.0.0.1:18089/healthz"),
)
CONTAINER_FILTER = re.compile(r"(sbi|caddy|ingress)", re.I)
NO_REDIRECTS = 999


def command(args, *, timeout=12):
    try:
        r = subprocess.run(args, text=True, capture_output=True, timeout=timeout,
                           check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_source(root):
    result = {
        "git_head": command(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "tracked_changes": "UNKNOWN",
        "approved_main_source_pin": APPROVED_MAIN,
        "source_blobs": {},
    }
    changes = command(["git", "-C", str(root), "status", "--porcelain"])
    if changes is not None:
        result["tracked_changes"] = "PRESENT" if changes else "NONE"
    for name, expected in MAIN_BLOBS.items():
        p = root / name
        sha = (command(["git", "-C", str(root), "hash-object", str(p)])
               if p.is_file() else None)
        result["source_blobs"][name] = {
            "present": p.is_file(),
            "matches_reviewed_main_blob": sha == expected,
            "working_blob": sha,
        }
    result["github_main_file_parity"] = (
        all(x["matches_reviewed_main_blob"] for x in result["source_blobs"].values())
    )
    result["source_baseline_status"] = (
        "MATCHES_MAIN_REVIEWED_SOURCE"
        if result["github_main_file_parity"] and result["tracked_changes"] == "NONE"
        and result["git_head"] == APPROVED_MAIN
        else "REVIEW_REQUIRED_AWS_OR_SOURCE_MISMATCH"
    )
    return result


class DenyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def localhost_status():
    opener = urllib.request.build_opener(DenyRedirect)
    result = {}
    for label, url in LOCAL_HEALTH:
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "SBI-Phase1-Readiness-ReadOnly/1"}
            )
            with opener.open(request, timeout=2) as response:
                code = response.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (OSError, TimeoutError, ValueError):
            code = "UNREACHABLE"
        result[label] = {"url": url, "http_code": code}
    return result


def docker_inventory():
    output = command([
        "docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}"
    ], timeout=15)
    if output is None:
        return {"access": "NOT_AVAILABLE_OR_NOT_AUTHORIZED",
                "containers": [], "live_image_source_parity": "NOT_VERIFIED"}
    matched = []
    for line in output.splitlines():
        name, sep, rest = line.partition("|")
        if not sep or not CONTAINER_FILTER.search(name):
            continue
        _, _, status = rest.partition("|")
        inspect = command([
            "docker", "inspect", "--format",
            "{{.Image}}|{{.HostConfig.NetworkMode}}|"
            "{{.HostConfig.ReadonlyRootfs}}|{{.State.Running}}",
            name
        ], timeout=15)
        if inspect is None:
            metadata = ["NOT_VERIFIED"] * 4
        else:
            metadata = inspect.split("|")
            if len(metadata) != 4:
                metadata = ["NOT_VERIFIED"] * 4
        matched.append({
            "name": name,
            "status": status[:150],
            "immutable_image_id": metadata[0],
            "network_mode": metadata[1],
            "readonly_rootfs": metadata[2],
            "running": metadata[3],
            "image_to_git_source_provenance": "NOT_VERIFIED",
        })
        if len(matched) >= 25:
            break
    return {"access": "READ_ONLY_METADATA_AVAILABLE",
            "containers": matched,
            "live_image_source_parity": "NOT_VERIFIED"}


def inventory(host_root, cn_root):
    source = git_source(host_root)
    cn = {
        "path_exists": cn_root.is_dir(),
        "isolated_preview_source_present":
            (cn_root / "staging/sbi_cn_isolated_stage_app.py").is_file(),
        "credit_note_validation_source_present":
            (cn_root / "backend_source/credit_note_validation.py").is_file(),
        "running_authenticated_preview": "NOT_VERIFIED",
        "live_firebase_authorization": "NOT_TESTED",
        "live_financial_database_connected": False,
    }
    report = {
        "schema": "sbi-phase1-reporting-release-inventory-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "DASHBOARD_LOGIN_READONLY_REPORTS_CN_PREVIEW",
        "read_only_inventory": True,
        "aws_source": source,
        "credit_note_candidate": cn,
        "docker": docker_inventory(),
        "localhost_health": localhost_status(),
        "github_reporting_workflow": {
            "source_qa_run": "43012842580",
            "source_verifier": "PASS",
            "production_auth_and_promotion": "SKIPPED_IN_VERIFIED_RUN",
            "independent_release_evidence": "NOT_VERIFIED",
        },
        "release_components": {
            "dashboard_ui": "SOURCE_PRESENT_DEPLOYED_IMAGE_NOT_VERIFIED",
            "firebase_login": "SOURCE_PRESENT_REAL_SESSION_NOT_TESTED",
            "readonly_reports": "SOURCE_PRESENT_LIVE_READ_AUTH_AND_VALUES_NOT_VERIFIED",
            "credit_note_preview": "SEPARATE_SOURCE_NOT_LIVE_INTEGRATED",
            "financial_database_writes": "DISALLOWED",
        },
        "release_gates": {
            "current_running_baseline_image": "NOT_CERTIFIED",
            "real_firebase_auth": "NOT_TESTED",
            "report_viewer_authorization": "NOT_TESTED_LIVE",
            "readonly_report_http_and_values": "NOT_VERIFIED",
            "independent_iam_scope": "NOT_VERIFIED",
            "backup_restore_and_rollback": "NOT_VERIFIED",
            "candidate_vs_deployed_image_parity": "NOT_VERIFIED",
            "sha_bound_production_release_evidence": "NOT_PRESENT_IN_THIS_AUDIT",
        },
        "service_deployments": "NOT_PERFORMED",
        "cloud_api_calls": 0,
        "financial_data_reads": 0,
        "financial_database_writes": 0,
        "phase1_ready_for_production": False,
        "phase1_status": "BLOCKED_PENDING_LIVE_AUTH_REPORT_AND_RELEASE_EVIDENCE",
    }
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host-root", default="/home/ubuntu/sbi-aws-app")
    p.add_argument("--cn-root", default="/home/ubuntu/sbi-cn-combined-qa")
    p.add_argument("--out", required=True, help="NEW JSON QA report, no overwrite")
    args = p.parse_args()
    out = Path(args.out).resolve()
    if out.suffix.lower() != ".json" or not out.parent.is_dir() or out.exists():
        p.error("Output must be a new .json file in an existing directory")
    result = inventory(Path(args.host_root), Path(args.cn_root))
    # Exclusive create; never change original evidence or application state.
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    os.chmod(out, 0o600)
    print("=== SBI PHASE 1 REAL HOST INVENTORY ===")
    print("AWS_SOURCE_SHA=" + str(result["aws_source"]["git_head"]))
    print("AWS_MAIN_BLOB_PARITY=" +
          ("PASS" if result["aws_source"]["github_main_file_parity"] else "REVIEW_REQUIRED"))
    print("AWS_SOURCE_BASELINE=" + result["aws_source"]["source_baseline_status"])
    print("DOCKER_METADATA=" + result["docker"]["access"])
    print("MATCHED_RUNNING_CONTAINERS=" + str(len(result["docker"]["containers"])))
    for c in result["docker"]["containers"]:
        print("CONTAINER_NAME=" + c["name"] +
              " IMAGE_ID=" + c["immutable_image_id"] +
              " RUNNING=" + c["running"])
    for name, item in result["localhost_health"].items():
        print("LOCAL_ENDPOINT_" + name.upper() + "=" + str(item["http_code"]))
    for name, status in result["release_components"].items():
        print("PHASE1_" + name.upper() + "=" + status)
    print("REAL_FIREBASE_LOGIN=NOT_TESTED")
    print("LIVE_REPORT_VALUES=NOT_VERIFIED")
    print("FINANCIAL_WRITES=NOT_PERFORMED")
    print("PRODUCTION_DEPLOYMENT=NOT_PERFORMED")
    print("PRODUCTION_RELEASE=BLOCKED")
    print("PHASE1_REPORT=" + str(out))
    print("PHASE1_INVENTORY=COMPLETE_WITH_PRODUCTION_GATES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
