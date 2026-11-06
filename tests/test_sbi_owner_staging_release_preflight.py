"""Offline deployment preflight regression. No real invoice data or clouds."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_owner_staging_release_preflight",
    ROOT / "tools" / "sbi_owner_staging_release_preflight.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OwnerStagingPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for rel in module.RELEASE_INPUTS:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)

    def tearDown(self):
        self.temp.cleanup()

    def test_01_all_source_modules_present(self):
        report = module.inspect(self.root)
        self.assertEqual(report["result"], "PASS_SOURCE_PACKAGE_ONLY")
        self.assertEqual(len(report["source_files"]), 8)

    def test_02_financial_production_never_auto_approved(self):
        report = module.inspect(self.root)
        self.assertEqual(report["production_release"], "BLOCKED")
        self.assertEqual(report["cloud_staging_deployment"], "NOT_PERFORMED")
        self.assertEqual(report["finance_database_write_permission"], "NOT_GRANTED")

    def test_03_missing_approved_rulebook_blocks(self):
        (self.root / "docs/owner-approved-candidate-screening-policy-20261106.md").unlink()
        report = module.inspect(self.root)
        self.assertEqual(report["result"], "BLOCKED_SOURCE_INTEGRITY")

    def test_04_removed_owner_rule_fails_closed(self):
        path=self.root / "docs/owner-approved-candidate-screening-policy-20261106.md"
        path.write_text(path.read_text().replace("OWNER-RULE-03", "DELETED-RULE-03"))
        self.assertEqual(module.inspect(self.root)["result"], "BLOCKED_SOURCE_INTEGRITY")

    def test_05_missing_credit_note_detector_fails_closed(self):
        path=self.root / "backend_source/credit_note_53_adapter.py"
        path.write_text(path.read_text().replace("CREDIT_NOTE_TOKEN","NO_TOKEN"))
        self.assertEqual(module.inspect(self.root)["result"], "BLOCKED_SOURCE_INTEGRITY")

    def test_06_source_edit_changes_manifest_hash_without_mutation(self):
        original = module.inspect(self.root)
        path = self.root / "backend_source/credit_note_53_adapter.py"
        path.write_text(path.read_text() + "\n# benign source marker\n")
        edited = module.inspect(self.root)
        self.assertNotEqual(
            original["source_files"]["backend_source/credit_note_53_adapter.py"]["sha256"],
            edited["source_files"]["backend_source/credit_note_53_adapter.py"]["sha256"]
        )

    def test_07_bundle_contains_only_eight_whitelisted_sources_and_manifest(self):
        out=self.root / "safe.zip"
        module.package(self.root, module.inspect(self.root), out)
        with zipfile.ZipFile(out) as f:
            names=set(f.namelist())
            self.assertEqual(names,set(module.RELEASE_INPUTS) | {"RELEASE_PREFLIGHT_MANIFEST.json"})
            self.assertTrue(all(not p.endswith(".csv") for p in names))
            self.assertTrue(f.testzip() is None)

    def test_08_no_package_when_integrity_failed(self):
        path=self.root / "tools/owner_candidate_policy_gate.py"
        path.unlink()
        with self.assertRaises(ValueError):
            module.package(self.root, module.inspect(self.root), self.root / "bad.zip")

    def test_09_symlinked_external_data_rejected(self):
        path=self.root / "backend_source/invoice_source_schema.py"
        outside=self.root / "outside.py"
        outside.write_text(path.read_text())
        path.unlink()
        path.symlink_to(outside)
        self.assertEqual(module.inspect(self.root)["result"],"BLOCKED_SOURCE_INTEGRITY")

    def test_10_existing_legacy_cloud_helper_is_not_deployment_proof(self):
        p=self.root/"staging/private_stage_deploy.sh"
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text("#!/bin/sh\ngcloud run deploy --image \"$IMAGE\" --ingress all\n")
        report=module.inspect(self.root)
        self.assertTrue(report["checks"]["legacy_stage_helper_requires_runtime_revalidation"])
        self.assertEqual(report["cloud_staging_deployment"],"NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
