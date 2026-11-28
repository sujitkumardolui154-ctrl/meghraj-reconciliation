"""4S acceptance matrix QA: no real external test or AWS mutation in CI."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4s_combined_external_acceptance as s

SHA="a"*40


class R3114SExternalGateTests(unittest.TestCase):

    def copy_variant(self,change):
        document=json.loads(s.MATRIX.read_text(encoding="utf-8"))
        change(document)
        tmp=tempfile.TemporaryDirectory()
        f=Path(tmp.name)/"matrix.json"
        f.write_text(json.dumps(document),encoding="utf-8")
        return tmp,f

    def test_real_4l_original_22_ids_preserved_all_unexecuted(self):
        with redirect_stdout(StringIO()) as out:
            manifest=s.validate_plan()
        ids=[x["id"] for x in manifest["external_cases"]]
        self.assertEqual(len(ids),22)
        self.assertEqual(ids,list(s.l.EXPECTED_ACCEPTANCE_CASES))
        self.assertEqual(len(set(ids)),22)
        self.assertTrue(all(x["status"]=="NOT_TESTED_EXTERNAL" for x in
                            manifest["external_cases"]))
        self.assertEqual(manifest["authorization"],"NOT_GRANTED")
        self.assertEqual(manifest["external_https_endpoint"],"NOT_DEPLOYED")
        self.assertIn("DB_R31_11_4S_EXTERNAL_MATRIX=PASS_22_EXACT_CASES_NOT_TESTED",
                      out.getvalue())

    def test_no_one_can_claim_real_mtls_or_firebase_acceptance(self):
        changes=[
            lambda d:d.update({"authorization":"GRANTED"}),
            lambda d:d.update({"approved_fqdn":"qa.example.org"}),
            lambda d:d.update({"external_https_endpoint":"DEPLOYED"}),
            lambda d:d.update({"remote_test_client":"APPROVED"}),
            lambda d:d.update({"witnessed_execution":"COMPLETE"}),
            lambda d:d.update({"rollback_authorization":"APPROVED"}),
            lambda d:d.update({"approved_network_scope":"0.0.0.0/0"}),
            lambda d:d.update({"financial_apply":"ENABLED"}),
            lambda d:d.update({"production_release":"APPROVED"}),
            lambda d:d["external_cases"][0].update({"status":"PASS"}),
            lambda d:d["external_cases"][4].update({"evidence_ticket":"FAKE-TICKET-123"}),
            lambda d:d["external_cases"][13].update({
                "independent_review_ticket":"NOT-ACTUAL-REVIEW"}),
            lambda d:d["external_cases"][5].update({"expected":"SKIP_REVOCATION"}),
            lambda d:d["external_cases"][17].update({"id":"FINANCE_API_ALLOWED"}),
            lambda d:d["external_cases"].pop(),
            lambda d:d["external_cases"].reverse(),
            lambda d:d["postconditions"].update({"financial_apply":"ENABLED"}),
            lambda d:d.update({"client_private_key":"SHOULD_NOT_BE_HERE"}),
            lambda d:d.update({"notice":"SIGNED OFF"}),
        ]
        for i,change in enumerate(changes):
            with self.subTest(case=i):
                tmp,path=self.copy_variant(change)
                with tmp,self.assertRaises(s.AcceptanceBlocked):
                    s.validate_plan(path)

    def test_no_secret_in_test_description(self):
        tmp,path=self.copy_variant(lambda d:d["external_cases"][0].update({
            "description":"Testing PRIVATE KEY material in an untrusted workflow"
        }))
        with tmp,self.assertRaises(s.AcceptanceBlocked):
            s.validate_plan(path)

    def test_symlinked_matrix_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            symlink=Path(tmp)/"matrix.json"
            symlink.symlink_to(s.MATRIX)
            with self.assertRaises(s.AcceptanceBlocked):
                s.validate_plan(symlink)

    def test_combined_invokes_4r_real_checks_and_post_invariants(self):
        with (
            patch.object(s.r,"full_combined") as predecessor,
            patch.object(s.g,"caddy_preflight",
                         return_value=s.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(s.g,"check_database_isolation") as db,
            patch.object(s.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            result=s.main(["--source-sha",SHA])
        self.assertEqual(result,0,out.getvalue())
        predecessor.assert_called_once_with(
            SHA,s.r.MANIFEST,s.r.q.k.TEMPLATE_PACKET,s.r.q.m.REGISTER)
        caddy.assert_called_once()
        db.assert_called_once()
        cleanup.assert_called_once()
        for receipt in (
            "DB_R31_11_4S_E2E_GATE=DENIED_MISSING_APPROVALS_AND_ENDPOINT",
            "DB_R31_11_4S_4R_THROUGH_4H_SECURITY=PASS_READONLY",
            "DB_R31_11_4S_AFTER_QA_CADDY_POSTGRES=PASS_UNCHANGED",
            "DB_R31_11_4S_COMBINED_READINESS=PASS_NO_LIVE_EXTERNAL_TEST",
            "DB_R31_11_4S_ACTUAL_REMOTE_TESTS=0_OF_22_EXECUTED",
            "DB_R31_11_4S_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4S_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(receipt,out.getvalue())

    def test_caddy_sha_drift_blocks_past_pass(self):
        with (
            patch.object(s.r,"full_combined"),
            patch.object(s.g,"caddy_preflight",return_value="0"*64),
            patch.object(s.g,"check_database_isolation") as db,
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(s.main(["--source-sha",SHA]),2)
        db.assert_not_called()
        self.assertIn("DB_R31_11_4S_BLOCK_REASON=S_PUBLIC_CADDY_FINGERPRINT_DRIFT",
                      out.getvalue())
        self.assertNotIn("DB_R31_11_4S_COMBINED_READINESS=PASS",out.getvalue())

    def test_untrusted_cloud_exception_not_exposed(self):
        with (
            patch.object(s.r,"full_combined",
                         side_effect=RuntimeError("PRIVATE_FIREBASE_TOKEN_ABC")),
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(s.main(["--source-sha",SHA]),2)
        self.assertNotIn("PRIVATE_FIREBASE_TOKEN_ABC",out.getvalue())
        self.assertIn("STOP=DB_R31_11_4S_SOURCE_OR_SECURITY_REVIEW_REQUIRED",
                      out.getvalue())
        self.assertIn("DB_R31_11_4S_FINANCIAL_APPLY=LOCKED",out.getvalue())

    def test_plan_does_not_expose_real_external_probe_actions(self):
        import inspect
        body=inspect.getsource(s)
        for prohibited in (
            "requests.post(","requests.get(","urllib.request.urlopen(",
            "docker run","docker network connect",
            "curl --cert","certbot certonly","socket.create_connection("
        ):
            self.assertNotIn(prohibited,body)

if __name__=="__main__":
    unittest.main()
