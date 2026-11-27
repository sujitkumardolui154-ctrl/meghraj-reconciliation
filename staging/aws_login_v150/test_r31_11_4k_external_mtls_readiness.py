"""R31.11.4K offline approval and AWS-readonly guard tests. No AWS network."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4k_external_mtls_readiness as k

SHA="b"*40

class R3114KApprovalTests(unittest.TestCase):
    def packet(self):
        return k.read_packet(k.TEMPLATE_PACKET)

    def complete(self):
        obj=self.packet()
        for field in k.APPROVAL_FIELDS:
            obj[field]=True
        obj.update({
          "workflow_status":"REVIEW_ONLY",
          "change_ticket":"QA-REVIEW-123",
          "qa_fqdn":"qa.example.org",
          "approved_source_cidrs":"198.51.100.0/24",
          "server_certificate_provider":"approved-review-only",
          "client_ca_metadata_reference":"approved-qa-ca-review-reference",
          "rollback_ticket":"QA-ROLLBACK-123",
          "external_test_owner":"approved-reviewer",
        })
        return obj

    def test_template_is_all_unapproved_and_schema_strict(self):
        p=self.packet()
        self.assertEqual(p["workflow_status"],"PENDING_APPROVAL")
        self.assertTrue(all(p[x] is False for x in k.APPROVAL_FIELDS))
        self.assertTrue(all(p[x]=="PENDING" for x in k.TEXT_FIELDS))
        with redirect_stdout(StringIO()) as out:
            missing=k.review_packet(p)
        self.assertEqual(set(missing),set(k.APPROVAL_FIELDS)|set(k.TEXT_FIELDS))
        self.assertIn("DB_R31_11_4K_APPROVAL_PACKET=INCOMPLETE",out.getvalue())

    def test_reviewer_declared_complete_is_never_automatic_deployment(self):
        p=self.complete()
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(k.review_packet(p),[])
        self.assertIn("DECLARED_COMPLETE_REVIEW_ONLY",out.getvalue())

    def test_reject_unknown_fields_secrets_and_type_confusion(self):
        p=self.complete()
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"packet.json"
            for change in (
                {"UNEXPECTED_FIELD":"yes"},
                {"qa_client_ca_owner_approved":"yes"},
                {"change_ticket":"-----BEGIN PRIVATE KEY-----"},
                {"workflow_status":"DEPLOY"},
            ):
                variant=dict(p,**change)
                f.write_text(json.dumps(variant))
                with self.subTest(change=change),self.assertRaises(k.GateBlocked):
                    k.read_packet(f)

    def test_reject_unscoped_firewall_temporary_hostnames_and_bad_cidrs(self):
        p=self.complete()
        for hostname in ("qa.example.invalid","localhost","qa.127.0.0.1.sslip.io",
                         "qa.example.internal"):
            with self.subTest(hostname=hostname):
                q=dict(p,qa_fqdn=hostname)
                with self.assertRaises(k.GateBlocked):
                    k.review_packet(q)
        for cidrs in ("0.0.0.0/0","::/0","198.51.100.1/24","198.51.100.0/24,garbage"):
            with self.subTest(cidrs=cidrs):
                q=dict(p,approved_source_cidrs=cidrs)
                with self.assertRaises(k.GateBlocked):
                    k.review_packet(q)

    def test_caddy_template_fails_closed_with_no_upstream(self):
        with redirect_stdout(StringIO()) as out:
            k.inspect_inactive_caddy_template()
        self.assertIn("PASS_503_NO_UPSTREAM",out.getvalue())
        evil=k.TEMPLATE_CADDY.read_text()+"\nreverse_proxy production-api:8080\n"
        with (patch.object(Path,"read_text",return_value=evil),
              self.assertRaises(k.GateBlocked)):
            k.inspect_inactive_caddy_template()

    def test_default_audit_never_deploys_and_rechecks_pg_caddy(self):
        with (
          patch.object(k,"audit_live_readonly") as live,
          patch.object(k.g,"caddy_preflight",
                       return_value=k.h.EXPECTED_4G_CADDY_SHA256) as caddy,
          patch.object(k.g,"check_database_isolation") as db,
          patch.object(k.g,"ephemeral_cleanup") as clean,
          redirect_stdout(StringIO()) as out,
        ):
            rc=k.main(["--source-sha",SHA])
        self.assertEqual(rc,0)
        live.assert_called_once_with(SHA)
        caddy.assert_called_once()
        db.assert_called_once()
        clean.assert_called_once()
        text=out.getvalue()
        self.assertIn("DB_R31_11_4K_READINESS_AUDIT=PASS_PREPARATION_ONLY",text)
        self.assertIn("DB_R31_11_4K_APPROVAL_PACKET=INCOMPLETE",text)
        self.assertIn("DB_R31_11_4K_EXTERNAL_HTTPS_MTLS=NOT_TESTED",text)
        self.assertIn("DB_R31_11_4K_FINANCIAL_APPLY=LOCKED",text)

    def test_even_complete_packet_does_not_release_production(self):
        p=self.complete()
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"packet.json"
            f.write_text(json.dumps(p))
            with (
              patch.object(k,"audit_live_readonly"),
              patch.object(k.g,"caddy_preflight",
                           return_value=k.h.EXPECTED_4G_CADDY_SHA256),
              patch.object(k.g,"check_database_isolation"),
              patch.object(k.g,"ephemeral_cleanup"),
              redirect_stdout(StringIO()) as out,
            ):
                rc=k.main(["--source-sha",SHA,"--mode","packet-review",
                           "--packet",str(f)])
        self.assertEqual(rc,0)
        text=out.getvalue()
        self.assertIn("DECLARED_COMPLETE_REVIEW_ONLY",text)
        self.assertIn("DB_R31_11_4K_RELEASE_REVIEW=NO_DEPLOYMENT_AUTHORIZATION",text)
        self.assertIn("DB_R31_11_4K_PRODUCTION_RELEASE=BLOCKED",text)

    def test_caddy_drift_blocks_and_suppresses_secret_errors(self):
        with (
          patch.object(k,"audit_live_readonly"),
          patch.object(k.g,"caddy_preflight",return_value="0"*64),
          patch.object(k.g,"check_database_isolation") as pg,
          redirect_stdout(StringIO()) as out,
        ):
            rc=k.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        pg.assert_not_called()
        self.assertIn("STOP=DB_R31_11_4K_READINESS_REVIEW_REQUIRED",out.getvalue())
        with (
          patch.object(k,"audit_live_readonly",
                       side_effect=RuntimeError("SENSITIVE_FIREBASE_TOKEN")),
          redirect_stdout(StringIO()) as out2,
        ):
            rc=k.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        self.assertNotIn("SENSITIVE_FIREBASE_TOKEN",out2.getvalue())

if __name__=="__main__":
    unittest.main()
