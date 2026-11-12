#!/usr/bin/env python3
"""SBI CN external release-evidence preflight (read-only, no cloud connections).

Collects verifiable *host-local* evidence without reading financial values,
credentials or login cookies. External authorization, IAM, backup restore and
financial parity remain UNVERIFIED until independently proven; this script
never certifies them, approves a release or starts a financial service.

Only intentional write: a NEW QA JSON report at a caller-specified path.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

EXPECTED_PRODUCTION_GATEWAY = "dashboard_source/production_gateway.py"
REQUIRED_SOURCE = (
    "staging/sbi_cn_isolated_stage_app.py",
    "dashboard_source/sbi_cn_staging_preview.py",
    "dashboard_source/dashboard_sessions.py",
    "backend_source/credit_note_registry_readonly.py",
    "backend_source/credit_note_registry_audit.py",
    "backend_source/credit_note_import_file.py",
    "tools/sbi_cn_combined_remaining_qa.py",
)
CLOUD_GATES = (
    ("REAL_FIREBASE_LOGIN_REVOCATION", "NOT_TESTED"),
    ("PRIVATE_TLS_STAGING_ACCESS", "NOT_VERIFIED"),
    ("EFFECTIVE_GOOGLE_CLOUD_READONLY_IAM", "NOT_VERIFIED"),
    ("LIVE_FIRESTORE_AUTHORIZED_READS", "NOT_ATTEMPTED"),
    ("INVOICE_CN_REPLACEMENT_INDEX_PARITY", "NOT_VERIFIED"),
    ("FIVE_HISTORICAL_CN_CONFLICT_DECISIONS", "PENDING_REVIEW"),
    ("LIVE_PAYMENT_IMPORT_AND_VALUE_PARITY", "NOT_TESTED"),
    ("INDEPENDENT_FIRESTORE_BACKUP_RESTORE", "NOT_VERIFIED"),
    ("OWNER_PRODUCTION_AUTHORIZATION", "NOT_GRANTED"),
)
# These are only evidence-presence checks, not approved source identities.
KNOWN_EVIDENCE_NAMES = (
    "credit-note_snapshot-20261101T110857Z_manifest.json",
    "credit-note_snapshot-20261101T110857Z_conflicts.csv",
)


def _git(root, args):
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _source_preflight(root):
    missing = [item for item in REQUIRED_SOURCE if not (root / item).is_file()]
    gateway = root / EXPECTED_PRODUCTION_GATEWAY
    if gateway.is_file():
        data = gateway.read_text(encoding="utf-8", errors="replace")
        unchanged_route_boundary = (
            "create_credit_note_staging_blueprint" not in data
            and "sbi_cn_isolated_stage_app" not in data
        )
    else:
        unchanged_route_boundary = False
    stage = root / "staging/sbi_cn_isolated_stage_app.py"
    if stage.is_file():
        stage_text = stage.read_text(encoding="utf-8", errors="replace")
        disconnected = (
            "offline_preview" in stage_text
            and "STAGING_FINANCIAL_DATABASE_NOT_CONNECTED" in stage_text
        )
    else:
        disconnected = False
    return {
        "required_source_files_present": not missing,
        "missing_source_files": missing,
        "production_gateway_does_not_register_stage": unchanged_route_boundary,
        "staging_handler_explicitly_offline": disconnected,
        "source_boundary_pass": (not missing) and unchanged_route_boundary and disconnected,
    }


def _host_evidence(evidence_root):
    # Record only metadata; never read, print or return source record values.
    files = []
    for name in KNOWN_EVIDENCE_NAMES:
        item = evidence_root / name
        try:
            if item.is_file():
                files.append({
                    "artifact": name,
                    "present": True,
                    "size_bytes": item.stat().st_size,
                })
            else:
                files.append({"artifact": name, "present": False})
        except OSError:
            files.append({"artifact": name, "present": False})
    return files


def collect(root, evidence_root):
    root = Path(root)
    src = _source_preflight(root)
    source_commit = _git(root, ["rev-parse", "HEAD"])
    clean = _git(root, ["status", "--porcelain"]) == ""
    # Do NOT execute gcloud, Docker, curl, Firebase or Firestore APIs.
    tools_found = {
        "gcloud_cli_present": shutil.which("gcloud") is not None,
        "aws_cli_present": shutil.which("aws") is not None,
        "docker_cli_present": shutil.which("docker") is not None,
    }
    metadata = {
        "google_application_credentials_path_configured":
            bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        "gcp_project_env_configured":
            bool(os.environ.get("GOOGLE_CLOUD_PROJECT")),
        "cloud_service_key_contents_inspected": False,
        "network_requests_made": False,
    }
    return {
        "schema": "sbi-cn-external-readiness-preflight/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit or "NOT_VERIFIED",
        "source_worktree_clean": clean,
        "source_checks": src,
        "host_tool_presence": tools_found,
        "credential_configuration_flags": metadata,
        "evidence_file_presence": _host_evidence(Path(evidence_root)),
        "external_gates": dict(CLOUD_GATES),
        "external_gates_certified": 0,
        "real_login_tested": False,
        "live_database_connected": False,
        "financial_values_read": False,
        "financial_writes": "NOT_PERFORMED",
        "database_backfill": "NOT_PERFORMED",
        "production_deployment": "NOT_PERFORMED",
        "owner_production_approval": "NOT_GRANTED",
        "production_cutover": "BLOCKED",
        "preflight_status": (
            "LOCAL_SOURCE_PREFLIGHT_PASS_EXTERNAL_BLOCKERS"
            if src["source_boundary_pass"] and source_commit and clean
            else "LOCAL_SOURCE_REVIEW_REQUIRED_EXTERNAL_BLOCKERS"
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True,
                        help="New QA JSON report path; never overwritten")
    parser.add_argument("--evidence-root",
                        default="/home/ubuntu/sbi-private-evidence")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = collect(root, args.evidence_root)

    target = Path(args.report).resolve()
    if target.suffix != ".json" or target.exists() or not target.parent.is_dir():
        parser.error("REPORT_MUST_BE_NEW_JSON_IN_EXISTING_DIRECTORY")
    # x-mode ensures existing financial/source files cannot be overwritten.
    with target.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    os.chmod(target, 0o600)
    print("=== SBI CN EXTERNAL READINESS EVIDENCE PREFLIGHT ===")
    print("SOURCE_COMMIT=" + result["source_commit"])
    print("SOURCE_WORKTREE_CLEAN=" + str(result["source_worktree_clean"]))
    print("SOURCE_BOUNDARY=" + (
        "PASS" if result["source_checks"]["source_boundary_pass"] else "REVIEW_REQUIRED"
    ))
    for item in result["evidence_file_presence"]:
        print("EVIDENCE_PRESENT_" + item["artifact"].replace(".", "_").upper() +
              "=" + str(item["present"]))
    for name, state in result["external_gates"].items():
        print(name + "=" + state)
    print("READ_ONLY_IAM_CERTIFIED=NO")
    print("REAL_FIREBASE_LOGIN=NOT_TESTED")
    print("LIVE_FINANCIAL_VALUES=NOT_ACCESSED")
    print("FINANCIAL_WRITES=NOT_PERFORMED")
    print("PRODUCTION_CUTOVER=BLOCKED")
    print("QA_REPORT=" + str(target))
    print("SBI_EXTERNAL_READINESS=" + result["preflight_status"])
    return 0 if result["preflight_status"].startswith("LOCAL_SOURCE_PREFLIGHT_PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
