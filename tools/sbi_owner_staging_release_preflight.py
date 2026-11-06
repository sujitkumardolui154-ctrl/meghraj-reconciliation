#!/usr/bin/env python3
"""Owner-approved SBI release PRE-FLIGHT ONLY.

Creates a small source-only staging evidence bundle. Never accesses financial
data, GCP/AWS, credentials, Firestore or a production deployment API.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

RELEASE_INPUTS = (
    "backend_source/invoice_source_schema.py",
    "backend_source/credit_note_53_adapter.py",
    "backend_source/sbi_marker_precedence_shadow.py",
    "tools/owner_candidate_policy_gate.py",
    "docs/owner-approved-candidate-screening-policy-20261106.md",
    "tests/test_credit_note_annotation_qa.py",
    "tests/test_sbi_marker_precedence_shadow.py",
    "tests/test_owner_candidate_policy_gate.py",
)
SOURCE_CHECKS = {
    "docs/owner-approved-candidate-screening-policy-20261106.md": (
        "OWNER-RULE-01", "OWNER-RULE-02", "OWNER-RULE-03",
        "FINANCIAL", "PRODUCTION"),
    "backend_source/credit_note_53_adapter.py": (
        "CREDIT_NOTE_TOKEN", "REPORT_HEADERS", "header_mapping"),
    "backend_source/sbi_marker_precedence_shadow.py": (
        "PROTECT_HISTORICAL_BANK_L_OK", "new_allocation_approved"),
    "tools/owner_candidate_policy_gate.py": (
        "New Allocation Approved", "NO", "production_release"),
}
BLOCKED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".pdf", ".zip", ".env", ".jsonl"}
BLOCKED_TOKENS = ("/.git/", "/.env", "/secrets/", "/credentials/")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            part = stream.read(1024 * 1024)
            if not part:
                break
            digest.update(part)
    return digest.hexdigest()


def inspect(root):
    root = Path(root).resolve()
    checks = {}
    checks["owner_policy_files_present"] = True
    checks["required_source_markers_present"] = True
    files = {}
    for relative in RELEASE_INPUTS:
        candidate = root / relative
        # Reject links BEFORE resolving: an in-root symlink is still unsafe.
        p = candidate.resolve()
        if candidate.is_symlink() or not p.is_relative_to(root) or not p.is_file():
            checks["owner_policy_files_present"] = False
            continue
        # Whitelist alone is not enough: only regular source/doc/test files.
        if p.suffix in BLOCKED_EXTENSIONS or any(x in ("/" + relative) for x in BLOCKED_TOKENS):
            checks["owner_policy_files_present"] = False
            continue
        content = p.read_text(encoding="utf-8")
        expected = SOURCE_CHECKS.get(relative, ())
        if not all(m in content for m in expected):
            checks["required_source_markers_present"] = False
        files[relative] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    checks["all_eight_inputs_exactly_present"] = len(files) == len(RELEASE_INPUTS)
    # An earlier deploy helper copied a production image and used ingress=all.
    # It is not evidence that this merged source was built or safely deployed.
    legacy = root / "staging/private_stage_deploy.sh"
    if legacy.exists():
        raw = legacy.read_text(encoding="utf-8")
        checks["legacy_stage_helper_requires_runtime_revalidation"] = (
            "--image \"$IMAGE\"" in raw or "--ingress all" in raw
        )
    else:
        checks["legacy_stage_helper_requires_runtime_revalidation"] = False
    hard_pass = all(checks[k] for k in (
        "owner_policy_files_present",
        "required_source_markers_present",
        "all_eight_inputs_exactly_present",
    ))
    return {
        "schema": "SBI_OWNER_RELEASE_PREFLIGHT_V1",
        "result": "PASS_SOURCE_PACKAGE_ONLY" if hard_pass else "BLOCKED_SOURCE_INTEGRITY",
        "source_files": files,
        "checks": checks,
        "owner_business_rule_approval": "ACCEPTED",
        "independent_financial_ledger_parity": "NOT_VERIFIED",
        "credit_note_amount_parity": "NOT_VERIFIED",
        "finance_database_write_permission": "NOT_GRANTED",
        "cloud_staging_deployment": "NOT_PERFORMED",
        "cloud_identity_and_rollback": "NOT_VERIFIED",
        "production_release": "BLOCKED",
    }


def package(root, report, destination):
    if report["result"] != "PASS_SOURCE_PACKAGE_ONLY":
        raise ValueError("Cannot package failed source integrity")
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    root = Path(root).resolve()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for relative in sorted(RELEASE_INPUTS):
            out.write(root / relative, arcname=relative)
        out.writestr("RELEASE_PREFLIGHT_MANIFEST.json", json.dumps(
            report, indent=2, sort_keys=True
        ) + "\n")
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-dir", default="staging_release_preflight")
    args = parser.parse_args(argv)
    result = inspect(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "release_preflight.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result["result"] != "PASS_SOURCE_PACKAGE_ONLY":
        print(json.dumps(result, indent=2))
        return 1
    archive = package(args.root, result, out_dir / "owner_staging_source_evidence.zip")
    result["archive_sha256"] = sha256(archive)
    (out_dir / "release_preflight.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "SOURCE_PREFLIGHT": result["result"],
        "SOURCE_ARTIFACT_SHA256": result["archive_sha256"],
        "CLOUD_STAGING_DEPLOYMENT": result["cloud_staging_deployment"],
        "FINANCIAL_DATABASE_WRITES": 0,
        "PRODUCTION_RELEASE": "BLOCKED"
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
