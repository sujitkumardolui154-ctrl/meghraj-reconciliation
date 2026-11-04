"""Stage 6R.4 recovery metadata locator tests; no live credentials or data reads."""
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"staging/aws_lightsail/stage6r4_firestore_backup_locator.py"
spec=importlib.util.spec_from_file_location("sbi_stage6r4",SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6R4Tests(unittest.TestCase):
    def test_repo_source_pass_but_recovery_stays_blocked(self):
        data=mod.assess(ROOT,[])
        self.assertEqual(data["discovery_audit"],"PASS")
        self.assertEqual(data["recovery_gate"],"BLOCKED_PENDING_AUTHORIZED_GCS_EXPORT_AND_PARITY")
        self.assertEqual(data["authenticated_gcs_access"],"NOT_TESTED")
        self.assertEqual(data["financial_database"],"NOT_CONNECTED")
        self.assertEqual(data["financial_writes"],0)
        self.assertFalse(data["host_services_changed"])
        self.assertEqual(data["prior_report_manifest_reference"]["baseline_invoice_rows"],14374)
        self.assertEqual(data["prior_report_manifest_reference"]["release_status"],"REVIEW_REQUIRED")

    def test_metadata_inventory_does_not_open_export_data(self):
        with TemporaryDirectory(prefix="stage6r4-") as temp:
            path=Path(temp)/"archive"
            path.mkdir()
            (path/"20261101.overall_export_metadata").write_bytes(b"binary metadata")
            (path/"ALL_NAMESPACES_KIND_rows.export_metadata").write_bytes(b"metadata")
            (path/"firebase-export-operation.json").write_text("NOT VALID JSON")
            (path/"invoice.xlsx").write_bytes(b"sensitive content")
            result=mod.inventory(path)
            self.assertEqual(result["status"],"CANDIDATE_METADATA_FOUND")
            self.assertEqual(result["counts"]["overall_export_metadata"],1)
            self.assertEqual(result["counts"]["collection_export_metadata"],1)
            self.assertEqual(result["counts"]["candidate_operation_json"],1)

    def test_operation_status_done_not_data_integrity(self):
        with TemporaryDirectory(prefix="stage6r4-") as temp:
            path=Path(temp)/"operation.json"
            path.write_text(json.dumps({
                "name":"projects/meghraj-reconciliation/databases/(default)/operations/example",
                "done":True,
                "metadata":{"@type":"type.googleapis.com/google.firestore.admin.v1.ExportDocumentsMetadata",
                            "outputUriPrefix":"gs://private-bucket/sbi-export"},
                "response":{"outputUriPrefix":"gs://private-bucket/sbi-export"}
            }))
            status=mod.inspect_operation(path)
            self.assertEqual(status["status"],"DONE_GCS_PREFIX_PRESENT")
            self.assertTrue(status["has_gcs_prefix"])
            self.assertNotIn("gs://",json.dumps(status))
            self.assertNotIn("private-bucket",json.dumps(status))

    def test_incomplete_operation_does_not_pass(self):
        with TemporaryDirectory(prefix="stage6r4-") as temp:
            path=Path(temp)/"operation.json"
            path.write_text(json.dumps({"done":False,"metadata":{"outputUriPrefix":"gs://bucket/path"}}))
            self.assertEqual(mod.inspect_operation(path)["status"],"NOT_VERIFIED_COMPLETE")

    def test_no_cli_network_or_cloud_side_effects(self):
        code=SRC.read_text()
        for forbidden in ("import boto3", "import google", "import requests",
                          "import firebase_admin","subprocess","os.system(",
                          "urllib.request", "storage.Client(", "firestore.Client("):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":
    unittest.main()
