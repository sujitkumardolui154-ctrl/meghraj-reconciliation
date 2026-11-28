"""Offline regression for R31.11.4P; all AWS/Firebase/PG calls are mocked."""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4p_combined_pki_preflight as p

SHA="a"*40

class PKIPlanTests(unittest.TestCase):
    def original(self):
        return json.loads(p.PLAN.read_text("utf-8"))

    def variant(self,change):
        doc=self.original()
        change(doc)
        temp=tempfile.TemporaryDirectory()
        f=Path(temp.name)/"plan.json"
        f.write_text(json.dumps(doc),encoding="utf-8")
        return temp,f

    def test_strict_six_pending_and_eight_workflow_steps(self):
        doc=p.read_plan()
        self.assertEqual(len(doc["evidence_requirements"]),6)
        self.assertEqual(len(doc["lifecycle_workflow"]),8)
        self.assertEqual([x["field"] for x in doc["evidence_requirements"]],
                         list(p.PKI_FIELDS))
        self.assertEqual(doc["deployment_authorization"],"NOT_GRANTED")
        self.assertEqual(doc["qa_fqdn"],"PENDING")
        self.assertEqual(doc["status"]["client_revocation"],"NOT_TESTED")

    def test_pki_design_cannot_claim_approved_credentials_or_tls(self):
        changes=[
            lambda d:d.update({"deployment_authorization":"APPROVED"}),
            lambda d:d.update({"qa_fqdn":"live.qa.example.org"}),
            lambda d:d.update({"trusted_client_ca":"ISSUED"}),
            lambda d:d.update({"revocation_enforcement":"PRODUCTION_ENABLED"}),
            lambda d:d["status"].update({"client_revocation":"PASS"}),
            lambda d:d["status"].update({"financial_apply":"ENABLED"}),
            lambda d:d["reference_security_requirements"].update({
                "client_certificate_revocation":"OPTIONAL"}),
            lambda d:d["reference_security_requirements"].pop("unknown_client_ca"),
            lambda d:d["evidence_requirements"][0].update({"state":"APPROVED"}),
            lambda d:d["evidence_requirements"][0].update({"evidence_ticket":"SEC-111"}),
            lambda d:d["evidence_requirements"].reverse(),
            lambda d:d["lifecycle_workflow"][0].update({"status":"DEPLOYED"}),
            lambda d:d["lifecycle_workflow"].pop(),
            lambda d:d.update({"private_key":"DUMMY_TOKEN"}),
            lambda d:d.update({"caveat":"trust approved"})
        ]
        for idx,change in enumerate(changes):
            with self.subTest(idx=idx):
                temp,f=self.variant(change)
                with temp,self.assertRaises(p.PKIBlocked):
                    p.read_plan(f)

    def test_symlinked_certificate_plan_denied(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"plan.json"
            f.symlink_to(p.PLAN)
            with self.assertRaises(p.PKIBlocked):
                p.read_plan(f)

    def test_original_register_and_4k_packet_retain_pki_locks(self):
        with redirect_stdout(StringIO()) as out:
            p.enforce_prior_approval_consistency(p.k.TEMPLATE_PACKET,
                p.m.REGISTER,p.n.INTAKE)
        self.assertIn("PKI_PENDING",out.getvalue())

    def test_conflicting_4k_client_ca_approval_denied(self):
        data=p.k.read_packet(p.k.TEMPLATE_PACKET)
        data["qa_client_ca_owner_approved"]=True
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"fake_packet.json"
            f.write_text(json.dumps(data))
            with self.assertRaises(p.PKIBlocked):
                p.enforce_prior_approval_consistency(f,p.m.REGISTER,p.n.INTAKE)

    def test_synthetic_revoked_expired_wrong_ca_eku_unlisted_are_denied(self):
        now=datetime(2026,11,28,tzinfo=timezone.utc)
        good={"id":"A","issuer":"CA","eku":"clientAuth",
              "not_before":now-timedelta(days=1),
              "not_after":now+timedelta(days=1)}
        def permits(info,revoked=frozenset()):
            return p.simulated_decision(info,trusted_ca="CA",
                      allowed_ids=frozenset({"A"}),revoked_ids=revoked,now=now)
        self.assertTrue(permits(good))
        self.assertFalse(permits(good,frozenset({"A"})))
        for changed in (
            dict(good,issuer="WRONG"),
            dict(good,eku="serverAuth"),
            dict(good,id="UNLISTED"),
            dict(good,not_before=now+timedelta(seconds=1)),
            dict(good,not_after=now),
            dict(good,private_key="INJECTION"),
        ):
            self.assertFalse(permits(changed))
        with redirect_stdout(StringIO()) as out:
            p.simulation()
        self.assertIn("PASS_FAIL_CLOSED_METADATA_ONLY",out.getvalue())
        self.assertIn("REAL_TLS=NOT_TESTED",out.getvalue())

    def test_combined_one_command_rechecks_full_4o_and_pg_caddy(self):
        with (
            patch.object(p.o,"full_combined_preflight") as previous,
            patch.object(p.g,"caddy_preflight",
                         return_value=p.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(p.g,"check_database_isolation") as pg,
            patch.object(p.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            code=p.main(["--source-sha",SHA])
        self.assertEqual(code,0,out.getvalue())
        previous.assert_called_once_with(SHA,p.o.DOSSIER,p.n.INTAKE,
                                          p.m.REGISTER,p.k.TEMPLATE_PACKET)
        caddy.assert_called_once()
        pg.assert_called_once()
        cleanup.assert_called_once()
        s=out.getvalue()
        for text in (
            "DB_R31_11_4P_TRUST_PROFILE=PASS_REFERENCE_DESIGN_ONLY",
            "DB_R31_11_4P_PRIOR_K_M_N_APPROVALS=6_OF_6_PKI_PENDING",
            "DB_R31_11_4P_LIFECYCLE_STEPS=8_NOT_IMPLEMENTED",
            "DB_R31_11_4P_4O_THROUGH_4H_COMBINED_QA=PASS_READONLY",
            "DB_R31_11_4P_COMBINED_PKI_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY",
            "DB_R31_11_4P_REAL_EXTERNAL_MTLS_HTTPS=NOT_TESTED",
            "DB_R31_11_4P_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4P_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(text,s)

    def test_caddy_hash_drift_is_blocking(self):
        with (
            patch.object(p.o,"full_combined_preflight"),
            patch.object(p.g,"caddy_preflight",return_value="0"*64),
            patch.object(p.g,"check_database_isolation") as pg,
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(p.main(["--source-sha",SHA]),2)
        pg.assert_not_called()
        self.assertIn("PKI_CADDY_FINGERPRINT_DRIFT",out.getvalue())
        self.assertNotIn("COMBINED_PKI_READINESS=PASS",out.getvalue())

    def test_secret_containing_exception_suppressed(self):
        with (patch.object(p.o,"full_combined_preflight",
                           side_effect=RuntimeError("FIREBASE_SECRET_ABC")),
              redirect_stdout(StringIO()) as out):
            self.assertEqual(p.main(["--source-sha",SHA]),2)
        self.assertNotIn("FIREBASE_SECRET_ABC",out.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",out.getvalue())

if __name__=="__main__":
    unittest.main()
