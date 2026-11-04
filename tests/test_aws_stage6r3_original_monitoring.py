"""Stage 6R.3 tests using actual original static monitoring code, never finance."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"staging/aws_lightsail/stage6r3_original_monitoring.py"
DOCKER=ROOT/"staging/aws_lightsail/Dockerfile.stage6r3"
RUNNER=ROOT/"staging/aws_lightsail/stage6r3_combined_monitoring.sh"
spec=importlib.util.spec_from_file_location("sbi_stage6r3",SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Stage6R3OriginalMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.profile={
            "SBI_RECOVERY_PROFILE":"lightsail-original-readonly-monitoring",
            "SBI_FINANCIAL_EXECUTION":"disabled",
            "SBI_BACKEND_CONNECTED":"false",
            "SBI_SOURCE_REVISION_PARITY":"unverified",
        }
        self.source=ROOT/"backend_source/main.py"

    def test_gate(self):
        self.assertEqual(mod.gate(self.profile,self.source),"READY_PRIVATE_ORIGINAL_MONITOR_ONLY")
        bad=deepcopy(self.profile)
        bad["SBI_FINANCIAL_EXECUTION"]="enabled"
        self.assertEqual(mod.gate(bad,self.source),"BLOCKED_FINANCE")
        bad=deepcopy(self.profile)
        bad["SBI_BACKEND_CONNECTED"]="true"
        self.assertEqual(mod.gate(bad,self.source),"BLOCKED_BACKEND")
        bad=deepcopy(self.profile)
        bad["SBI_SOURCE_REVISION_PARITY"]="verified"
        self.assertEqual(mod.gate(bad,self.source),"BLOCKED_PARITY")
        bad=deepcopy(self.profile)
        bad["GOOGLE_APPLICATION_CREDENTIALS"]="/private/creds"
        self.assertEqual(mod.gate(bad,self.source),"BLOCKED_CLOUD_CREDENTIALS_OR_BACKEND")

    def test_original_source_executes_static_routes(self):
        handler=mod.load_original(self.source)
        self.assertEqual(set(mod.SAFE),{"/health","/qa","/supervisor","/agents"})
        for route in mod.SAFE:
            data,status,headers=handler(SimpleNamespace(path=route,method="GET"))
            self.assertEqual(status,200)
            self.assertTrue(mod.allowed_payload(route,json.loads(data)),route)
        self.assertEqual(handler(SimpleNamespace(path="/unknown",method="GET"))[1],404)

    def test_source_fails_closed_if_monitoring_claims_live(self):
        invalid={
            "/health":{"financial_execution_enabled":True},
            "/qa":{"production_release":"READY"},
            "/supervisor":{"financial_engine":"DEPLOYED"},
            "/agents":{"live_agent_connection":True},
        }
        handler=mod.load_original(self.source)
        for route,changes in invalid.items():
            data,_,_=handler(SimpleNamespace(path=route,method="GET"))
            payload=json.loads(data)
            payload.update(changes)
            self.assertFalse(mod.allowed_payload(route,payload),route)

    def test_reject_unexpected_fields(self):
        handler=mod.load_original(self.source)
        payload=json.loads(handler(SimpleNamespace(path="/health",method="GET"))[0])
        payload["credit_note_rows"]=14374
        self.assertFalse(mod.allowed_payload("/health",payload))

    def test_inert_source_and_docker_contract(self):
        image=DOCKER.read_text()
        self.assertIn("FROM sbi-stage6r2-recovered:14115d966475",image)
        self.assertIn("USER 65534:65534",image)
        self.assertIn("PRIVATE_ORIGINAL_STATIC_MONITORING_NO_FINANCE",image)
        self.assertNotIn("pip install",image)
        code=SRC.read_text()
        self.assertIn('("127.0.0.1", 8082)',code)
        self.assertIn('self.path not in SAFE',code)
        for forbidden in ("import firebase_admin","import google.cloud","import boto3",
                          "firestore.Client(", "storage.Client(", "subprocess"):
            self.assertNotIn(forbidden,code)

    def test_combined_runner_isolation_and_cleanup(self):
        content=RUNNER.read_text()
        for marker in ("trap cleanup EXIT INT TERM",
                       "--pull=false --network none",
                       "--network none --read-only",
                       "--memory 128m",
                       "NETWORK_ISOLATION=PASS",
                       "TEMPORARY_CLEANUP=PASS",
                       "BATCH_QA=PASS",
                       "ORIGINAL_HEALTH",
                       "ORIGINAL_SUPERVISOR",
                       "REPORTS_DENIED",
                       "IMPORT_APPLY_DENIED"):
            self.assertIn(marker,content)
        for forbidden in ("--network host","--publish","docker compose up",
                          "docker restart", "gcloud auth","aws ec2"):
            self.assertNotIn(forbidden,content)

if __name__=="__main__":
    unittest.main()
