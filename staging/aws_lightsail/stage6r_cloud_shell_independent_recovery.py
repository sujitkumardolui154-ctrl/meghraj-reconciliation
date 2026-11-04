#!/usr/bin/env python3
"""Stage 6R: assess GitHub-recoverable SBI application without Cloud Shell.

Reads known repository source *paths only*. Does not import source modules, inspect
secrets, access Firebase, retrieve data, start a service or mutate an AWS/GCP host.
"""
import argparse
import json
from pathlib import Path

REQUIRED = {
  "dashboard": ("dashboard_source/production_gateway.py",
                "dashboard_source/index.html",
                "dashboard_source/dashboard_sessions.py",
                "dashboard_source/dashboard_login_pages.py",
                "dashboard_source/requirements.txt"),
  "backend": ("backend_source/main.py",
              "backend_source/report_api.py",
              "backend_source/payment_report_rules.py",
              "backend_source/credit_note_report.py",
              "backend_source/requirements.txt"),
  "lightsail_candidate": ("staging/aws_lightsail/Dockerfile.stage6d",
                          "dashboard_source/stage6d_private_entry.py",
                          "staging/aws_lightsail/stage6d3_local_http_batch.sh"),
  "source_contracts": ("backend_source/invoice_import_contract.json",
                       "backend_source/invoice_source_schema.py",
                       "backend_source/sbi_firestore_contract_v5.py"),
  "migration_governance": ("AGENTS.md",
                           "docs/SBI_STAGE6D8_IDENTITY_APPROVAL_INTAKE.md"),
}

def inspect(root):
    root = Path(root).resolve()
    sections = {}
    for section, items in REQUIRED.items():
        found = {}
        for name in items:
            target=(root/name).resolve()
            found[name] = target.is_relative_to(root) and target.is_file()
        sections[section] = {
            "status":"PASS" if all(found.values()) else "BLOCKED",
            "found":sum(found.values()),
            "required":len(found),
            "missing":[name for name, exists in found.items() if not exists],
        }
    source_ready = all(value["status"] == "PASS" for value in sections.values())
    return {
        "stage":"6R_CLOUD_SHELL_INDEPENDENT_RECOVERY",
        "source_origin":"GITHUB_WORKING_COPY_NOT_LIVE_GCP_REVISION",
        "sections":sections,
        "source_recovery":"PASS" if source_ready else "BLOCKED",
        "target":"EXISTING_AWS_LIGHTSAIL_ONLY",
        "new_ec2_instances":0,
        "lightsail_live_runtime":"NOT_TESTED_BY_THIS_AUDIT",
        "deployed_gcp_revision_parity":"NOT_VERIFIED",
        "firebase_server_identity":"NOT_ESTABLISHED",
        "live_firestore_access":"NOT_VERIFIED",
        "gcs_firestore_export_access":"NOT_VERIFIED",
        "google_drive_recovery_vault":"FOUND_EMPTY_AT_LAST_CONNECTED_METADATA_CHECK",
        "financial_data_transfer":"NOT_PERFORMED",
        "financial_writes":0,
        "existing_services_changed":False,
        "production_cutover":"BLOCKED",
        "batch_qa":"PASS" if source_ready else "BLOCKED",
        "next_gate":"PRIVATE_SOURCE_PACKAGE_AND_GCP_BACKUP_ACCESS_RECOVERY" if source_ready else "RETRIEVE_MISSING_GITHUB_SOURCE",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    args=p.parse_args()
    try:
        result=inspect(args.repo)
    except (OSError, ValueError):
        print("BATCH_QA=BLOCKED")
        print("NEXT_GATE=VERIFY_SOURCE_DIRECTORY")
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["batch_qa"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
