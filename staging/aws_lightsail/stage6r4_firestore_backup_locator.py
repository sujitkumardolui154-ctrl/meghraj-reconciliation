#!/usr/bin/env python3
"""SBI Stage 6R.4: Cloud-Shell-free, metadata-only Firestore export locator.

Reads only path names/stats under explicit backup directories. The sole optional
file-content read is a user-supplied Firestore operation status JSON, never a key
or credentials file. No network, database, IAM, Docker or AWS API calls.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

PROJECT = "meghraj-reconciliation"
EXPECTED = {
    "baseline_invoice_rows": 14374,
    "unique_invoice_numbers": 14360,
    "original_columns": 53,
    "credit_note_conflicts_pending": 5,
    "release_status": "REVIEW_REQUIRED",
    "source_sha256": "433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1",
}
SKIP = frozenset((".git",".ssh",".aws",".config",".cache",".venv","venv",
                  "__pycache__", "node_modules", "site-packages", ".docker"))
MAX_ENTRIES = 12000
MAX_DEPTH = 6

def inventory(root):
    """Inspect bounded path names; never open financial files."""
    root = Path(root).expanduser()
    counts = {"overall_export_metadata":0,"collection_export_metadata":0,
              "candidate_operation_json":0}
    if not root.exists():
        return {"status":"DIRECTORY_NOT_PRESENT","counts":counts,"entries_scanned":0}
    if root.is_symlink() or not root.is_dir() or len(root.resolve().parts) < 4:
        return {"status":"UNSAFE_DIRECTORY","counts":counts,"entries_scanned":0}
    examined = 0
    stack=[(root,0)]
    while stack and examined < MAX_ENTRIES:
        current, depth = stack.pop()
        try:
            entries=list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            examined+=1
            if examined > MAX_ENTRIES:
                break
            if entry.name in SKIP or entry.is_symlink():
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH:
                        stack.append((Path(entry.path),depth+1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            name=entry.name.lower()
            if name.endswith(".overall_export_metadata"):
                counts["overall_export_metadata"]+=1
            elif name.endswith(".export_metadata"):
                counts["collection_export_metadata"]+=1
            elif name.endswith(".json") and ("firestore" in name or "export-operation" in name):
                counts["candidate_operation_json"]+=1
    status=("SCAN_LIMIT_REACHED" if examined >= MAX_ENTRIES else
            "CANDIDATE_METADATA_FOUND" if any(counts.values()) else "NO_EXPORT_METADATA_FOUND")
    return {"status":status,"counts":counts,"entries_scanned":min(examined,MAX_ENTRIES)}

def inspect_operation(path):
    if not path:
        return {"status":"NOT_PROVIDED"}
    file=Path(path).expanduser()
    if not file.is_file() or file.is_symlink() or file.suffix.lower()!=".json" or file.stat().st_size>1048576:
        return {"status":"INVALID_STATUS_FILE"}
    try:
        obj=json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(obj,dict):
            return {"status":"INVALID_STATUS_JSON"}
        response=obj.get("response") or {}
        meta=obj.get("metadata") or {}
        if not isinstance(response,dict) or not isinstance(meta,dict):
            return {"status":"INVALID_STATUS_JSON"}
        path_value=response.get("outputUriPrefix") or meta.get("outputUriPrefix")
        has_gcs_prefix=isinstance(path_value,str) and path_value.startswith("gs://") and len(path_value)>6
        done=obj.get("done") is True
        errored=bool(obj.get("error"))
        operation_name = str(obj.get("name", ""))
        correct_project=(operation_name.startswith("projects/"+PROJECT+"/databases/")
                         and "/operations/" in operation_name)
        kind=str(meta.get("@type", "")) + " " + str(response.get("@type", ""))
        is_export="ExportDocuments" in kind
        ready=done and has_gcs_prefix and not errored and correct_project and is_export
        return {
            "status":"DONE_GCS_PREFIX_PRESENT" if ready else "NOT_VERIFIED_COMPLETE",
            "operation_completed":done,
            "has_gcs_prefix":has_gcs_prefix,
            "operation_error":errored,
            "export_prefix_sha256_12":hashlib.sha256(path_value.encode()).hexdigest()[:12] if has_gcs_prefix else None,
            "source_project_in_operation_name":correct_project,
            "export_operation_type_present":is_export
        }
    except (OSError,ValueError,TypeError,UnicodeError):
        return {"status":"INVALID_STATUS_JSON"}

def assess(source_root, roots, operation_path=None):
    source_root=Path(source_root).expanduser()
    source_available=(source_root/"backend_source/main.py").is_file() and (
        source_root/"dashboard_source/production_gateway.py").is_file()
    inventories=[inventory(x) for x in roots]
    operation=inspect_operation(operation_path)
    metadata_count=sum(item["counts"]["overall_export_metadata"] for item in inventories)
    return {
      "stage":"6R.4_FIRESTORE_BACKUP_DISCOVERY",
      "audit":"LOCAL_METADATA_ONLY_NO_CLOUD_SHELL",
      "source_recovery":"PASS" if source_available else "BLOCKED",
      "backup_locations_checked":len(inventories),
      "backup_inventories":inventories,
      "local_overall_export_metadata_candidates":metadata_count,
      "operation_status":operation,
      "gcloud_cli_installed":bool(shutil.which("gcloud")),
      "gsutil_installed":bool(shutil.which("gsutil")),
      "authenticated_gcs_access":"NOT_TESTED",
      "prior_report_manifest_reference":EXPECTED,
      "manifest_not_equivalent_to_database":True,
      "full_firestore_export_integrity":"NOT_VERIFIED",
      "real_firebase_login":"NOT_TESTED",
      "financial_database":"NOT_CONNECTED",
      "financial_writes":0,
      "host_services_changed":False,
      "production_cutover":"BLOCKED",
      "discovery_audit":"PASS" if source_available else "BLOCKED",
      "recovery_gate":"BLOCKED_PENDING_AUTHORIZED_GCS_EXPORT_AND_PARITY",
      "next_gate":"RECOVER_EXPORT_OUTPUT_URI_FROM_GCP_OPERATIONS_OR_STORAGE",
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",required=True)
    parser.add_argument("--backup-root",action="append",default=[])
    parser.add_argument("--operation-json",default=None)
    args=parser.parse_args()
    data=assess(args.source_root,args.backup_root,args.operation_json)
    print(json.dumps(data,sort_keys=True,indent=2))
    return 0 if data["discovery_audit"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
