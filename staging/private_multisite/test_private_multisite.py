"""Offline-only QA for private multi-location replacement architecture."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import json
import os
import runpy
import sys
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name, filename):
    s = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return mod


origin = module("sbi_private_origin", "private_origin.py")
qa = module("sbi_private_qa", "private_qa_preflight.py")


class PrivateMultisiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = qa.load_json(qa.GATE_FILE)
        cls.legacy = qa.load_json(qa.PUBLIC_EXTERNAL_MATRIX)

    def test_seven_private_gates_and_original_public_tests_still_blocked(self):
        self.assertEqual(qa.verify(self.policy, self.legacy), 7)
        self.assertEqual(len(self.policy["gates"]), 7)
        self.assertEqual(self.policy["original_public_external_mtls"]["acceptance_tests_executed"], 0)
        self.assertEqual(len(self.legacy["external_cases"]), 22)
        self.assertEqual(self.policy["production_release"], "BLOCKED")

    def test_no_domain_purchase_and_no_external_funnel(self):
        self.assertFalse(self.policy["domain_purchase_required"])
        self.assertEqual(self.policy["https_transport"], "TAILSCALE_SERVE_PRIVATE_HTTPS_NO_FUNNEL")
        self.assertFalse(self.policy["actual_tailnet_deployed"])
        self.assertFalse(self.policy["public_ingress_closed_verified"])

    def test_source_qa_does_not_approve_a_private_gate(self):
        fake = deepcopy(self.policy)
        fake["gates"][0]["status"] = "PASS"
        with self.assertRaises(ValueError):
            qa.verify(fake, self.legacy)

    def test_cannot_label_old_external_tests_passed_or_waived(self):
        for item in ("acceptance_tests_executed", "scope"):
            fake = deepcopy(self.policy)
            fake["original_public_external_mtls"][item] = (
                22 if item == "acceptance_tests_executed" else "WAIVED"
            )
            with self.subTest(item=item), self.assertRaises(ValueError):
                qa.verify(fake, self.legacy)
        bad = deepcopy(self.legacy)
        bad["external_cases"][0]["status"] = "PASS"
        with self.assertRaises(ValueError):
            qa.verify(self.policy, bad)

    def test_lock_cannot_be_disabled_by_manifest(self):
        for prop,value in (
            ("financial_apply","ENABLED"),
            ("production_release","APPROVED"),
            ("actual_tailnet_deployed",True),
            ("public_ingress_closed_verified",True),
            ("legacy_external_design_change_approved",True),
            ("actual_employee_access_tests_completed",22),
        ):
            fake = deepcopy(self.policy)
            fake[prop] = value
            with self.subTest(prop=prop), self.assertRaises(ValueError):
                qa.verify(fake, self.legacy)

    def test_valid_private_fqdn(self):
        good = "https://sbi-workspace.mycompany.ts.net"
        self.assertEqual(origin.validate_private_origin(good),good)

    def test_http_ipv4_ipv6_sslip_userinfo_wildcards_and_paths_denied(self):
        for val in (
            "http://sbi-workspace.mycompany.ts.net",
            "https://sbi-preview.13-232-241-221.sslip.io",
            "https://127.0.0.1",
            "https://[::1]",
            "https://sbi-workspace.mycompany.ts.net:443",
            "https://sbi-workspace.mycompany.ts.net/",
            "https://sbi-workspace.mycompany.ts.net/auth",
            "https://sbi-workspace.mycompany.ts.net?x=1",
            "https://sbi-workspace.mycompany.ts.net#fragment",
            "https://user@sbi-workspace.mycompany.ts.net",
            "https://*.mycompany.ts.net",
            "https://sbi-workspace.mycompany.ts.net.evil.example",
            "https://UPPERCASE.mycompany.ts.net",
            "https://machine.ts.net",
            "",
            " https://sbi-workspace.mycompany.ts.net ",
        ):
            with self.subTest(value=val),self.assertRaises(ValueError):
                origin.validate_private_origin(val)

    def test_mode_disabled_maintains_legacy_origin(self):
        self.assertIsNone(origin.configured_private_origin({}))

    def test_partial_or_unknown_mode_must_fail_closed(self):
        for env in (
            {origin.MODE_KEY: origin.APPROVED_MODE},
            {origin.ORIGIN_KEY: "https://machine.company.ts.net"},
            {origin.MODE_KEY: "public-funnel",
             origin.ORIGIN_KEY: "https://machine.company.ts.net"},
        ):
            with self.subTest(env=list(env)),self.assertRaises(ValueError):
                origin.configured_private_origin(env)

    def test_mode_requires_exact_explicit_origin(self):
        v = origin.configured_private_origin({
            origin.MODE_KEY: origin.APPROVED_MODE,
            origin.ORIGIN_KEY: "https://machine.company.ts.net"
        })
        self.assertEqual(v,"https://machine.company.ts.net")

    def test_private_entrypoint_overrides_all_legacy_origins_and_host(self):
        fake_app = types.SimpleNamespace(config={})
        fake_origins = {"https://old-cloudrun.example", "https://public.sslip.io"}
        fake_sessions = types.ModuleType("dashboard_sessions")
        fake_sessions.ORIGINS = fake_origins
        fake_runtime = types.ModuleType("app")
        fake_runtime.app = fake_app
        private_mod = types.ModuleType("private_origin")
        private_mod.configured_private_origin = origin.configured_private_origin
        env={origin.MODE_KEY:origin.APPROVED_MODE,
             origin.ORIGIN_KEY:"https://sbi.company.ts.net"}
        with patch.dict(os.environ,env,clear=True),patch.dict(sys.modules,{
            "app":fake_runtime,"dashboard_sessions":fake_sessions,
            "private_origin":private_mod
        }):
            result=runpy.run_path(str(HERE / "private_entrypoint.py"))
        self.assertIs(result["app"],fake_app)
        self.assertEqual(fake_origins,{"https://sbi.company.ts.net"})
        self.assertEqual(fake_app.config["TRUSTED_HOSTS"],["sbi.company.ts.net"])

    def test_private_entrypoint_fails_without_opt_in(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(RuntimeError):
            runpy.run_path(str(HERE/"private_entrypoint.py"))

    def test_private_docker_is_new_separate_candidate_not_existing_caddy(self):
        df=(HERE/"Dockerfile.private_multisite_review").read_text("utf-8")
        self.assertIn("private_entrypoint:app",df)
        self.assertIn("COPY staging/private_multisite/private_origin.py",df)
        self.assertIn("COPY staging/private_multisite/private_entrypoint.py",df)
        self.assertNotIn("app:app\"]",df)
        current=(HERE.parents[0]/"aws_login_v150"/"Caddyfile.workspace").read_text("utf-8")
        self.assertNotIn("ts.net",current)

    def test_no_real_deployment_or_external_data_needed(self):
        self.assertEqual(len(self.policy["reused_evidence"]),5)
        self.assertFalse(self.policy["actual_tailnet_deployed"])
        self.assertFalse(self.policy["public_ingress_closed_verified"])


if __name__=="__main__":
    unittest.main()
