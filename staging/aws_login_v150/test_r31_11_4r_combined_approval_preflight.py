"""4R offline QA: full combined approval preflight never authorizes deployment.

All AWS/PG/Caddy operations mocked in CI; there is no deployment path.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4r_combined_approval_preflight as r

SHA="a"*40


class R3114RDeploymentGateTests(unittest.TestCase):
    def baseline(self):
        return json.loads(r.MANIFEST.read_text("utf-8"))

    def variant(self,modify):
        data=self.baseline()
        modify(data)
        tmp=tempfile.TemporaryDirectory()
        path=Path(tmp.name)/"deployment.json"
        path.write_text(json.dumps(data),encoding="utf-8")
        return tmp,path

    def test_default_has_23_pending_and_no_deployment(self):
        with redirect_stdout(StringIO()) as out:
            data=r.validate_manifest()
        self.assertEqual(data["deployment_authorization"],"NOT_GRANTED")
        self.assertEqual(len(data["independent_prerequisites"]),8)
        self.assertEqual(len(data["linked_approvals"]),23)
        self.assertEqual(len(data["reviewed_rollback"]),9)
        self.assertEqual(data["remote_acceptance"]["executed_case_count"],0)
        self.assertIn("DB_R31_11_4R_LINKED_APPROVALS=23_OF_23_PENDING",out.getvalue())
        self.assertIn("DB_R31_11_4R_REMOTE_ACCEPTANCE=0_OF_22_TESTED",out.getvalue())

    def test_reject_forged_approvals_route_publication_and_write_access(self):
        changes=[
            lambda d:d.update({"deployment_authorization":"GRANTED"}),
            lambda d:d.update({"release_decision":"DEPLOY_ALLOWED"}),
            lambda d:d.update({"approved_qa_fqdn":"qa.example.org"}),
            lambda d:d.update({"independent_owner_and_security_approval":"VERIFIED"}),
            lambda d:d.update({"mode":"DEPLOY"}),
            lambda d:d["policy_constraints"].update({"qa_ingress":"DEPLOYED"}),
            lambda d:d["policy_constraints"].update({"public_caddy_change":"ALLOWED"}),
            lambda d:d["policy_constraints"].update({"qa_to_production_finance":"ALLOWED"}),
            lambda d:d["policy_constraints"].update({"qa_proxy_to_docker_socket":"ALLOWED"}),
            lambda d:d["policy_constraints"].update({"qa_postgres_public_port":"EXPOSED"}),
            lambda d:d["policy_constraints"].update({"financial_apply":"ENABLED"}),
            lambda d:d["independent_prerequisites"][0].update({"state":"APPROVED"}),
            lambda d:d["linked_approvals"][0].update({"state":"APPROVED"}),
            lambda d:d["linked_approvals"].append({"field":"new","state":"PENDING"}),
            lambda d:d["reviewed_rollback"][0].update({"state":"EXECUTED"}),
            lambda d:d["remote_acceptance"].update({"executed_case_count":22}),
            lambda d:d["remote_acceptance"].update({"external_https_mtls":"PASS"}),
            lambda d:d.update({"financial_apply":"ENABLED"}),
            lambda d:d.update({"production_release":"APPROVED"}),
            lambda d:d.update({"secret":"PASSWORD_PRIVATE_KEY"}),
        ]
        for i,modify in enumerate(changes):
            with self.subTest(case=i):
                tmp,path=self.variant(modify)
                with tmp,self.assertRaises(r.DeploymentBlocked):
                    r.validate_manifest(path)

    def test_reject_untrusted_symlink_and_missing_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=Path(tmp)/"manifest.json"
            link.symlink_to(r.MANIFEST)
            with self.assertRaises(r.DeploymentBlocked):
                r.validate_manifest(link)
        t,path=self.variant(lambda d:d.update({"statement":"APPROVED"}))
        with t,self.assertRaises(r.DeploymentBlocked):
            r.validate_manifest(path)

    def test_original_4k_and_4m_approval_packet_must_remain_pending(self):
        with (patch.object(r.q,"check_approvals") as check,
              redirect_stdout(StringIO()) as out):
            r.validate_real_approval_sources(r.q.k.TEMPLATE_PACKET,r.q.m.REGISTER)
        check.assert_called_once_with(r.q.k.TEMPLATE_PACKET,r.q.m.REGISTER)
        self.assertIn("DB_R31_11_4R_DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS",out.getvalue())
        self.assertIn("DB_R31_11_4R_REAL_OWNER_SECURITY_SIGNOFF=NOT_VERIFIED",out.getvalue())

    def test_combined_checks_actual_previous_source_and_caddy_pg(self):
        with (
            patch.object(r.q,"check_approvals"),
            patch.object(r.q,"full_combined_preflight") as preceding,
            patch.object(r.g,"caddy_preflight",
                         return_value=r.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(r.g,"check_database_isolation") as pg,
            patch.object(r.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            result=r.main(["--source-sha",SHA])
        self.assertEqual(result,0,out.getvalue())
        preceding.assert_called_once_with(
            SHA,r.q.FILE,r.q.k.TEMPLATE_PACKET,r.q.m.REGISTER)
        caddy.assert_called_once()
        pg.assert_called_once()
        cleanup.assert_called_once()
        text=out.getvalue()
        for line in (
            "DB_R31_11_4R_GATE_MANIFEST=PASS_NONDEPLOYABLE_SCHEMA",
            "DB_R31_11_4R_INDEPENDENT_PREREQUISITES=8_OF_8_UNVERIFIED",
            "DB_R31_11_4R_LINKED_APPROVALS=23_OF_23_PENDING",
            "DB_R31_11_4R_DEPLOYMENT_GATE=BLOCKED_MISSING_APPROVALS",
            "DB_R31_11_4R_4Q_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY",
            "DB_R31_11_4R_AFTER_COMBINED_CADDY_AND_PG=PASS_UNCHANGED",
            "DB_R31_11_4R_APPROVAL_PREFLIGHT=PASS_READONLY_RELEASE_BLOCKED",
            "DB_R31_11_4R_EXTERNAL_HTTPS_MTLS=NOT_TESTED",
            "DB_R31_11_4R_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4R_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(line,text)

    def test_hash_drift_halts_postcheck(self):
        with (
            patch.object(r.q,"check_approvals"),
            patch.object(r.q,"full_combined_preflight"),
            patch.object(r.g,"caddy_preflight",return_value="0"*64),
            patch.object(r.g,"check_database_isolation") as pg,
            redirect_stdout(StringIO()) as out,
        ):
            result=r.main(["--source-sha",SHA])
        self.assertEqual(result,2)
        pg.assert_not_called()
        self.assertIn("DB_R31_11_4R_BLOCK_REASON=R_PUBLIC_CADDY_FINGERPRINT_DRIFT",
                      out.getvalue())
        self.assertNotIn("APPROVAL_PREFLIGHT=PASS",out.getvalue())

    def test_upstream_secret_error_suppressed_and_gate_locked(self):
        with (
            patch.object(r.q,"check_approvals"),
            patch.object(r.q,"full_combined_preflight",
                         side_effect=RuntimeError("PRIVATE_FIREBASE_COOKIE_SECRET")),
            redirect_stdout(StringIO()) as out,
        ):
            status=r.main(["--source-sha",SHA])
        self.assertEqual(status,2)
        self.assertNotIn("PRIVATE_FIREBASE_COOKIE_SECRET",out.getvalue())
        self.assertIn("STOP=DB_R31_11_4R_SOURCE_OR_INFRA_SECURITY_REVIEW_REQUIRED",
                      out.getvalue())
        self.assertIn("DB_R31_11_4R_FINANCIAL_APPLY=LOCKED",out.getvalue())


if __name__=="__main__":
    unittest.main()
