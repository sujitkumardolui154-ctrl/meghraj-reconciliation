"""R31.11.4L offline design/approval gate tests. No network or cloud access."""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

import r31_11_4l_combined_design_gate as stage

SHA="b"*40


class DesignGateTests(TestCase):
    def test_manifest_exact_design_all_external_cases_pending(self):
        document=stage.inspect_design()
        self.assertEqual(len(document["exact_candidate_routes"]),5)
        self.assertEqual(len(document["rollback_review_steps"]),9)
        self.assertEqual(len(document["external_acceptance_cases"]),22)
        self.assertTrue(all(x["status"]=="NOT_TESTED_EXTERNAL"
                            for x in document["external_acceptance_cases"]))
        self.assertEqual(document["deployment_authorization"],"NOT_GRANTED")

    def write_variant(self, change):
        original=json.loads(stage.DESIGN.read_text())
        change(original)
        tmp=tempfile.TemporaryDirectory()
        p=Path(tmp.name)/"test.json"
        p.write_text(json.dumps(original))
        return tmp,p

    def test_rejects_broader_financial_route_or_new_method(self):
        cases=[
            lambda d:d["exact_candidate_routes"].append("POST /api/payment-evidence"),
            lambda d:d["exact_candidate_routes"].append("GET /api/financial"),
            lambda d:d["forbidden_route_prefixes"].remove("/api/gst"),
            lambda d:d["isolation"].update({"financial_apply":"ENABLED"}),
            lambda d:d["isolation"].update({"qa_proxy_direct_database_access":"ALLOWED"}),
            lambda d:d.update({"deployment_authorization":"GRANTED"}),
            lambda d:d["rollback_review_steps"].pop(),
            lambda d:d["external_acceptance_cases"][0].update({"status":"PASS"}),
        ]
        for n,change in enumerate(cases):
            with self.subTest(case=n):
                tmp,p=self.write_variant(change)
                with tmp,self.assertRaises(stage.Blocked):
                    stage.inspect_design(p)

    def test_packet_remains_pending_with_no_fake_approvals(self):
        with redirect_stdout(StringIO()) as out:
            missing=stage.packet_review(stage.k.TEMPLATE_PACKET)
        self.assertEqual(len(missing),23)
        self.assertIn("DB_R31_11_4L_DEPLOYMENT_APPROVALS=23_OF_23_STILL_PENDING",
                      out.getvalue())
        self.assertIn("DB_R31_11_4L_APPROVAL_STATUS=DECLARATIONS_ONLY_NOT_AUTHORIZED",
                      out.getvalue())

    def test_combined_default_rechecks_original_caddy_pg_no_mutations(self):
        with (
            patch.object(stage.k,"audit_live_readonly") as preflight,
            patch.object(stage.g,"caddy_preflight",
                         return_value=stage.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(stage.g,"check_database_isolation") as pg,
            patch.object(stage.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            exitcode=stage.main(["--source-sha",SHA])
        self.assertEqual(exitcode,0)
        preflight.assert_called_once_with(SHA)
        caddy.assert_called_once()
        pg.assert_called_once()
        cleanup.assert_called_once()
        lines=out.getvalue()
        self.assertIn("DB_R31_11_4L_DESIGN_REVIEW=PASS_PREPARATION_ONLY",lines)
        self.assertIn("DB_R31_11_4L_EXTERNAL_HTTPS_MTLS=NOT_TESTED",lines)
        self.assertIn("DB_R31_11_4L_FINANCIAL_APPLY=LOCKED",lines)
        self.assertIn("DB_R31_11_4L_PRODUCTION_RELEASE=BLOCKED",lines)

    def test_even_fully_declared_packet_never_unlocks(self):
        p=stage.k.read_packet(stage.k.TEMPLATE_PACKET)
        for key in stage.k.APPROVAL_FIELDS:
            p[key]=True
        p.update({
            "workflow_status":"REVIEW_ONLY",
            "qa_fqdn":"qa.example.org",
            "change_ticket":"QA-123",
            "approved_source_cidrs":"198.51.100.0/24",
            "server_certificate_provider":"manual-external-approval",
            "client_ca_metadata_reference":"test-ca-review-only",
            "rollback_ticket":"ROLLBACK-123",
            "external_test_owner":"test-reviser",
        })
        with tempfile.TemporaryDirectory() as d:
            packet=Path(d)/"packet.json"
            packet.write_text(json.dumps(p))
            with (
                patch.object(stage.k,"audit_live_readonly"),
                patch.object(stage.g,"caddy_preflight",
                             return_value=stage.h.EXPECTED_4G_CADDY_SHA256),
                patch.object(stage.g,"check_database_isolation"),
                patch.object(stage.g,"ephemeral_cleanup"),
                redirect_stdout(StringIO()) as out,
            ):
                rc=stage.main(["--source-sha",SHA,"--packet",str(packet)])
        self.assertEqual(rc,0)
        output=out.getvalue()
        self.assertIn("DB_R31_11_4L_DEPLOYMENT_APPROVALS=0_OF_23_STILL_PENDING",output)
        self.assertIn("DB_R31_11_4L_APPROVAL_STATUS=DECLARATIONS_ONLY_NOT_AUTHORIZED",
                      output)
        self.assertIn("DB_R31_11_4L_PRODUCTION_RELEASE=BLOCKED",output)

    def test_caddy_drift_stops_and_no_further_database_actions(self):
        with (
            patch.object(stage.k,"audit_live_readonly"),
            patch.object(stage.g,"caddy_preflight",return_value="0"*64),
            patch.object(stage.g,"check_database_isolation") as pg,
            redirect_stdout(StringIO()) as out,
        ):
            rc=stage.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        pg.assert_not_called()
        self.assertIn("DB_R31_11_4L_BLOCK_REASON=CADDY_FINGERPRINT_DRIFT",
                      out.getvalue())
        self.assertNotIn("DESIGN_REVIEW=PASS",out.getvalue())

    def test_untrusted_error_does_not_expose_secrets(self):
        with (
            patch.object(stage.k,"audit_live_readonly",
                         side_effect=RuntimeError("PRIVATE_FIREBASE_PASSWORD_abc")),
            redirect_stdout(StringIO()) as out,
        ):
            rc=stage.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        self.assertIn("STOP=DB_R31_11_4L_COMBINED_REVIEW_REQUIRED",out.getvalue())
        self.assertNotIn("PRIVATE_FIREBASE_PASSWORD_abc",out.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",out.getvalue())

if __name__=="__main__":
    main()
