"""Stage 6 migration audit offline regression tests."""
import importlib.util
import pathlib
import tempfile
import unittest

SOURCE=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage6_source_migration_audit.py"
spec=importlib.util.spec_from_file_location("stage6audit",SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Stage6Tests(unittest.TestCase):
    def test_deployed_parity_not_claimed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            for name,path in m.FILES.items():
                file=root/path
                file.parent.mkdir(parents=True,exist_ok=True)
                file.write_text("")
            result=m.audit(root)
            self.assertEqual(result["full_application_on_aws"],"NOT_VERIFIED")
            self.assertIn("BLOCKED",result["stage6_release_gate"])
            self.assertEqual(result["financial_writes"],0)
            self.assertFalse(result["production_change"])
    def test_missing_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"required source file missing"):
                m.audit(pathlib.Path(d))
    def test_only_read_only_no_cloud_client_or_docker(self):
        text=SOURCE.read_text()
        for term in ("subprocess", "urllib", "requests.", "docker run", "docker compose",
                     "firebase_admin.auth", "google.cloud", "os.environ", "shutil.rmtree"):
            self.assertNotIn(term,text)
    def test_real_repository_markers_are_detectable(self):
        root=SOURCE.parents[2]
        r=m.audit(root)
        self.assertTrue(r["migration_dependencies_detected"]["cloud_run_identity_tokens"])
        self.assertTrue(r["migration_dependencies_detected"]["aws_preview_not_full_gateway"])
        self.assertTrue(r["feature_source_markers"]["report_index"])

if __name__=="__main__":
    unittest.main()
