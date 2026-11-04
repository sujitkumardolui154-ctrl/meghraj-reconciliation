"""Offline assertions for the Stage 6D.3 network-none localhost HTTP batch."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/"staging/aws_lightsail/stage6d3_local_http_batch.sh"
class Stage6D3BatchContracts(unittest.TestCase):
    def test_isolated_runtime_and_cleanup(self):
        data=PATH.read_text()
        for marker in ("trap finish EXIT INT TERM","docker rm -f \"$NAME\"",
                       "--network none", "--read-only", "--cap-drop ALL",
                       "--security-opt no-new-privileges", "--memory 256m",
                       "--pids-limit 64", "docker exec -i", "127.0.0.1:8080",
                       "NO_PUBLIC_NETWORK=PASS", "BATCH_QA=", "NEXT_GATE="):
            self.assertIn(marker,data,marker)
        for forbidden in ("--publish ", "-p 127.0.0.1:", "--network host",
                          "--privileged", "/var/run/docker.sock:", "aws ec2",
                          "gcloud auth", "docker compose up", "docker stop $(docker ps"):
            self.assertNotIn(forbidden,data,forbidden)

    def test_auth_and_finance_negative_cases(self):
        data=PATH.read_text()
        for marker in ("ANONYMOUS_ROOT_REDIRECT", "LOGIN_PAGE_LOCAL_HTTP",
                       "CSRF_COOKIE_SECURE","UNTRUSTED_POST_ORIGIN_DENIED",
                       "TRUSTED_ORIGIN_WITHOUT_CSRF_DENIED",
                       "FINANCIAL_REPORT_DENIED","IMPORT_API_DENIED",
                       "FIREBASE_CONFIG_UNSET","FIREBASE_REAL_LOGIN=NOT_TESTED"):
            self.assertIn(marker,data)
if __name__=="__main__":
    unittest.main()
