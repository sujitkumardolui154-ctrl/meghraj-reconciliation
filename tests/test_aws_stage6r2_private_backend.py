"""Stage 6R.2 tests: recovered backend must stay inert, private and finance-free."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SHELL=ROOT/"staging/aws_lightsail/stage6r2_backend_shell.py"
RUNNER=ROOT/"staging/aws_lightsail/stage6r2_combined_backend_smoke.sh"
DOCKER=ROOT/"staging/aws_lightsail/Dockerfile.stage6r2"
IGNORE=ROOT/"staging/aws_lightsail/Dockerfile.stage6r2.dockerignore"
spec=importlib.util.spec_from_file_location("stage6r2",SHELL)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6R2PrivateBackendTests(unittest.TestCase):
    def make_source(self,root):
        for name in mod.REQUIRED:
            p=Path(root)/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.touch()

    def test_positive_gate_is_only_inert_package(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_source(root)
            env={"SBI_RECOVERY_PROFILE":"lightsail-isolated-no-finance",
                 "SBI_FINANCIAL_EXECUTION":"disabled",
                 "SBI_BACKEND_CONNECTED":"false"}
            self.assertEqual(mod.gate(env,Path(root)),"READY_INERT_BACKEND_PACKAGE")

    def test_missing_module_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            env={"SBI_RECOVERY_PROFILE":"lightsail-isolated-no-finance",
                 "SBI_FINANCIAL_EXECUTION":"disabled",
                 "SBI_BACKEND_CONNECTED":"false"}
            self.assertEqual(mod.gate(env,Path(root)),"BLOCKED_SOURCE_MODULES")

    def test_bad_profiles_block(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_source(root)
            base={"SBI_RECOVERY_PROFILE":"lightsail-isolated-no-finance",
                  "SBI_FINANCIAL_EXECUTION":"disabled",
                  "SBI_BACKEND_CONNECTED":"false"}
            for key,bad in (("SBI_RECOVERY_PROFILE","production"),
                            ("SBI_FINANCIAL_EXECUTION","enabled"),
                            ("SBI_BACKEND_CONNECTED","true")):
                env=dict(base)
                env[key]=bad
                self.assertTrue(mod.gate(env,Path(root)).startswith("BLOCKED_"))

    def test_all_methods_inert_and_loopback(self):
        source=SHELL.read_text()
        for marker in ('("127.0.0.1",8081)',"self.reply(503,",
                       "do_PUT=do_POST","do_DELETE=do_POST","NOT_CONNECTED",
                       "FINANCIAL_EXECUTION=DISABLED"):
            self.assertIn(marker,source)
        for forbidden in ("import firebase_admin", "import google.cloud", "import boto3",
                          "from backend_source", "os.system(", "subprocess"):
            self.assertNotIn(forbidden,source)

    def test_image_locks_nonroot_and_local_base(self):
        s=DOCKER.read_text()
        self.assertIn("FROM sbi-stage6d-candidate:c949777ffa32",s)
        self.assertIn("COPY --chown=65534:65534 backend_source/",s)
        self.assertIn("USER 65534:65534",s)
        self.assertIn('PRIVATE_RECOVERY_BACKEND_PACKAGE_ONLY_NO_FINANCE',s)
        self.assertNotIn("RUN pip install",s)
        ignore=IGNORE.read_text()
        self.assertIn("**/*.pem",ignore)
        self.assertIn("**/*.key",ignore)

    def test_combined_runner_no_public_or_existing_service_actions(self):
        s=RUNNER.read_text()
        for marker in ("trap cleanup EXIT INT TERM","git -C \"$repo\" archive",
                       "--pull=false --network none","--network none --read-only",
                       "CONTAINER_CLEANUP=PASS","BATCH_QA=PASS","BACKEND_API_IMPLEMENTATION=NOT_CONNECTED",
                       "REPORTS_DENIED","IMPORT_APPLY_DENIED","ADMIN_USERS_DENIED"):
            self.assertIn(marker,s)
        for forbidden in ("--network host","--publish","-p 127.0.0.1:",
                          "docker compose", "docker service", "gcloud ",
                          "aws ec2","docker stop $(docker ps"):
            self.assertNotIn(forbidden,s)
if __name__=="__main__":
    unittest.main()
