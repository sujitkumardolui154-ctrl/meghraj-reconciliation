"""No-AWS unit tests for R31.11.4G read-only release-gated preflight."""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import r31_11_4g_mtls_readonly_preflight as s


def safe_pg():
    return {
      "State":{"Running":True},
      "HostConfig":{"Privileged":False,"PortBindings":{}},
      "NetworkSettings":{"Networks":{s.QA_NETWORK:{}}},
    }


def safe_caddy():
    return {
      "State":{"Running":True},
      "HostConfig":{"Privileged":False},
    }


class SecurityPreflightTests(unittest.TestCase):
    def test_read_only_database_catalog_and_private_network_pass(self):
        def inspect(kind,name):
            if name==s.POSTGRES:return safe_pg()
            if name==s.QA_NETWORK:
                return {"Internal":True,"Attachable":False}
            raise AssertionError("unknown target")
        with (patch.object(s,"inspect_one",side_effect=inspect),
              patch.object(s,"docker",return_value=json.dumps({
                  "database":s.QA_DB,"owner_maps":2,"data_rows":0})) as docker):
            self.assertTrue(s.check_database_isolation())
            self.assertIn("BEGIN READ ONLY",str(docker.call_args))
            self.assertNotIn("INSERT INTO",str(docker.call_args))
        other=safe_pg()
        other["HostConfig"]["PortBindings"]={"5432/tcp":[{"HostPort":"5432"}]}
        with patch.object(s,"inspect_one",side_effect=lambda kind,name:
                          other if name==s.POSTGRES
                          else {"Internal":True,"Attachable":False}):
            with self.assertRaises(s.ReadOnlyBlocked):
                s.check_database_isolation()

    def test_caddy_checks_do_not_expose_config_or_accept_qa_route(self):
        config="https://example.invalid { reverse_proxy reporting:8080 }"
        with (patch.object(s,"inspect_one",return_value=safe_caddy()),
              patch.object(s,"docker",return_value=config)):
            digest=s.caddy_preflight()
        self.assertEqual(len(digest),64)
        with (patch.object(s,"inspect_one",return_value=safe_caddy()),
              patch.object(s,"docker",return_value=config+
                           " reverse_proxy sbi-r3114-private-postgres:5432")):
            with self.assertRaises(s.ReadOnlyBlocked):
                s.caddy_preflight()

    def test_ephemeral_cleanup_requires_absence_even_symlinks(self):
        seen=[]
        def fake_run(*cmd):
            seen.append(cmd)
            return (1,"")
        with (patch.object(s,"absent_docker") as absent,
              patch.object(s,"run",side_effect=fake_run)):
            self.assertTrue(s.ephemeral_cleanup())
        self.assertEqual(absent.call_count,2)
        self.assertTrue(all("test" in x for x in seen))
        with (patch.object(s,"absent_docker"),
              patch.object(s,"run",return_value=(0,""))):
            with self.assertRaises(s.ReadOnlyBlocked):
                s.ephemeral_cleanup()

    def test_success_is_planning_only_not_https_or_financial_acceptance(self):
        with (patch.object(s,"check_source"),
              patch.object(s,"check_database_isolation"),
              patch.object(s,"caddy_preflight",return_value="a"*64),
              patch.object(s,"ephemeral_cleanup"),
              redirect_stdout(StringIO()) as out):
            status=s.main(["--source-sha","f"*40])
        self.assertEqual(status,0)
        text=out.getvalue()
        self.assertIn("DB_R31_11_4G_MODE=READONLY_PLANNING_NO_AWS_CHANGES",text)
        self.assertIn("DB_R31_11_4G_EXTERNAL_MTLS_HTTPS=NOT_TESTED",text)
        self.assertIn("DB_R31_11_4G_R3112_QA_DESIGN=ACTIVE_RELEASE_GATED",text)
        self.assertIn("DB_R31_11_4G_FINANCIAL_APPLY=LOCKED",text)

    def test_failure_suppresses_sensitive_caddy_or_database_data(self):
        with (patch.object(s,"check_source",
                           side_effect=RuntimeError("PRIVATE_SECRET_TOKEN_SENTINEL")),
              redirect_stdout(StringIO()) as out):
            status=s.main(["--source-sha","f"*40])
        self.assertEqual(status,2)
        self.assertNotIn("PRIVATE_SECRET_TOKEN_SENTINEL",out.getvalue())
        self.assertIn("STOP=DB_R31_11_4G_PREFLIGHT_REVIEW_REQUIRED",out.getvalue())


if __name__=="__main__":
    unittest.main()
