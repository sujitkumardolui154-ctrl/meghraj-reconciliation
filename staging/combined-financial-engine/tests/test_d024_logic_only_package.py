"""D-024 source-only release package: deterministic, synthetic-only QA."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "staging/combined-financial-engine/logic_only_package.py"
spec = importlib.util.spec_from_file_location("logic_only_package", SCRIPT)
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)


class LogicOnlyPackageTests(unittest.TestCase):
    def test_contains_exact_allowlisted_files_and_no_customer_workbooks(self):
        with TemporaryDirectory() as t:
            bundle = Path(t) / "one.tar.gz"
            result = pkg.build_candidate(PROJECT_ROOT, bundle)
            self.assertEqual(result["status"], "LOGIC_ONLY_PACKAGE_CREATED")
            self.assertFalse(result["canonical_allocator_certified"])
            self.assertFalse(result["production_deployed"])
            self.assertFalse(result["historical_data_used"])
            with tarfile.open(bundle, "r:gz") as tar:
                names = [m.name for m in tar.getmembers()]
                self.assertEqual(set(names), set(pkg.ALLOWLIST) | {"release_manifest.json"})
                self.assertEqual(len(names), len(set(names)))
                self.assertFalse(any(name.endswith((".xlsx", ".xls", ".csv", ".pdf", ".db", ".sqlite"))
                                     for name in names))
                manifest = json.load(tar.extractfile("release_manifest.json"))
                self.assertEqual(manifest["source_count"], len(pkg.ALLOWLIST))
                self.assertFalse(manifest["historical_data_included"])
                self.assertFalse(manifest["financial_write_permission"])
                self.assertEqual(manifest["production_cutover"], "BLOCKED")
                for entry in manifest["source_files"]:
                    data = tar.extractfile(entry["path"]).read()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])

    def test_archive_is_deterministic(self):
        with TemporaryDirectory() as t:
            first = pkg.build_candidate(PROJECT_ROOT, Path(t) / "a.tar.gz")
            second = pkg.build_candidate(PROJECT_ROOT, Path(t) / "b.tar.gz")
            self.assertEqual(first["archive_sha256"], second["archive_sha256"])

    def test_bundle_runs_synthetic_probe_in_isolated_python(self):
        with TemporaryDirectory() as t:
            bundle = Path(t) / "staging.tar.gz"
            pkg.build_candidate(PROJECT_ROOT, bundle)
            extract_dir = Path(t) / "candidate"
            extract_dir.mkdir()
            with tarfile.open(bundle, "r:gz") as tar:
                tar.extractall(extract_dir, filter="data")
            probe = extract_dir / "staging/combined-financial-engine/synthetic_only_probe.py"
            for flag in ("--status", "--synthetic-selftest"):
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(probe), flag],
                    capture_output=True, text=True, cwd=extract_dir,
                    timeout=30, check=True,
                )
                output = json.loads(result.stdout)
                self.assertEqual(output["production_release"], "BLOCKED")
                self.assertEqual(output["financial_writes"], "NOT_PERFORMED")
                if flag == "--synthetic-selftest":
                    self.assertEqual(output["synthetic_logic_test"], "PASS")

    def test_probe_rejects_real_file_parameter(self):
        with TemporaryDirectory() as t:
            pkg.build_candidate(PROJECT_ROOT, Path(t) / "a.tar.gz")
            probe = (PROJECT_ROOT / "staging/combined-financial-engine"
                     / "synthetic_only_probe.py")
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(probe), "--file", "old.xlsx"],
                capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("error:", result.stderr)

    def test_network_imports_rejected(self):
        for code in (b"import requests", b"import socket",
                     b"from google.cloud import firestore",
                     b"__import__('subprocess')",
                     b"from os import getenv",
                     b"database.commit()"):
            with self.subTest(code=code):
                with self.assertRaises(pkg.UnsafeStagingSource):
                    pkg._code_preflight("demo.py", code)

    def test_absent_or_wrong_manifest_is_denied(self):
        module_file = (PROJECT_ROOT / "staging/combined-financial-engine"
                       / "logic_only_deploy_gate.py")
        gate_spec = importlib.util.spec_from_file_location("gate_check", module_file)
        gate = importlib.util.module_from_spec(gate_spec)
        gate_spec.loader.exec_module(gate)
        with self.assertRaises(gate.LogicOnlyPolicyBlocked):
            gate.check_logic_only_manifest({
                **gate.REQUIRED,
                "test_source": "HISTORICAL_INVOICE",
                "existing_finance_data_paths": [],
                "historical_backfill_jobs": [],
                "financial_database_endpoints": [],
            })

if __name__ == "__main__":
    unittest.main()
