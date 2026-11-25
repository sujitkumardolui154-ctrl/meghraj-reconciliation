"""Private R31.11.3 Flask gate tests: no real Firebase, no AWS."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from flask import Flask, g

from r31_11_3_runtime_rls_blueprint import runtime_tenant_rls
import r31_11_3_runtime_rls_blueprint as b

APP_SOURCE=(Path(__file__).resolve().parent/"app.py").read_text("utf-8")
DOCKER_SOURCE=(Path(__file__).resolve().parent/
               "Dockerfile.r31_11_3_private_candidate").read_text("utf-8")

class RuntimeBlueprintSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.register_blueprint(runtime_tenant_rls)
        self.app.testing=True
        self.user=None
        @self.app.before_request
        def simulated_verified_session():
            # Unit-test stand-in for Firebase middleware; actual deployment
            # requires install_sessions(app) and independently verified cookie.
            if self.user is not None:
                g.dil_user=self.user

    def _environment(self):
        return patch.dict(os.environ,{
            "SBI_R31_PRIVATE_STAGING_ENABLED":"isolated-ownerqa-firebase-csrf-v1",
            "SBI_R31_11_3_RUNTIME_ENABLED":"private-firebase-rls-readonly-v1"
        })

    def test_feature_off_returns_503_before_any_database_call(self):
        with patch.object(b,"read_tenant_source_only") as read:
            with self.app.test_client() as client:
                result=client.get("/api/r31-private-qa/tenant-rls-source")
        self.assertEqual(result.status_code,503)
        read.assert_not_called()

    def test_no_authenticated_user_returns_401(self):
        with self._environment(),patch.object(b,"read_tenant_source_only") as read:
            with self.app.test_client() as client:
                result=client.get("/api/r31-private-qa/tenant-rls-source")
        self.assertEqual(result.status_code,401)
        read.assert_not_called()

    def test_signed_in_identity_is_not_derived_from_query_or_header(self):
        self.user=SimpleNamespace(uid="r3113-firebase-a",
                                  custom_claims={"dil_dashboard":True})
        with self._environment(),patch.object(
            b,"read_tenant_source_only",return_value=[]
        ) as read:
            with self.app.test_client() as client:
                result=client.get(
                    "/api/r31-private-qa/tenant-rls-source?uid=attacker&limit=8",
                    headers={"X-Owner-Uid":"r3113-firebase-b"})
        self.assertEqual(result.status_code,200)
        read.assert_called_once_with(self.user,limit=8)
        self.assertFalse(result.json["financial_execution_enabled"])
        self.assertFalse(result.json["production_financial_writes"])
        self.assertEqual(result.json["reconciliation_status"],"NOT_CALCULATED")

    def test_existing_app_only_registers_when_nested_private_flags(self):
        self.assertIn('if os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED")',APP_SOURCE)
        self.assertIn('if os.environ.get("SBI_R31_11_3_RUNTIME_ENABLED")',APP_SOURCE)
        self.assertIn("app.register_blueprint(runtime_tenant_rls)",APP_SOURCE)
        self.assertNotIn("r31_11_3_runtime_rls_adapter.py",(
            Path(__file__).resolve().parent/"Dockerfile.r31_private_staging"
        ).read_text("utf-8"))
        self.assertIn("COPY staging/aws_login_v150/r31_11_3_runtime_rls_adapter.py",
                      DOCKER_SOURCE)

if __name__=="__main__":
    unittest.main()
