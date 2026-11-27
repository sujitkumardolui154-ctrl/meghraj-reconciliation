"""Offline-only R31.11.4I tests. No real Docker, Firebase, AWS or SQL."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4i_combined_auth_mtls as s

SHA = "a" * 40
VERSION = "v2.10.1 h1:fake-ci-version"
MTLS_SAMPLE = (
    "# R31.11 DESIGN CANDIDATE ONLY. DO NOT IMPORT OR DEPLOY AS-IS.\n"
    "https://qa-r311.example.invalid {\n"
    "  tls {\n"
    "    client_auth {\n"
    "      mode require_and_verify\n"
    "      trust_pool file /etc/caddy/r311-approved-client-ca.pem\n"
    "    }\n"
    "  }\n"
    "}\n"
)


class CombinedIQA(unittest.TestCase):
    def fake_mtls(self):
        return (
            patch.object(s.g.PLACEHOLDER.__class__, "read_text", return_value=MTLS_SAMPLE),
            patch.object(s.g, "docker", return_value=VERSION),
            patch.object(s.g, "caddy_preflight",
                         return_value=s.h.EXPECTED_4G_CADDY_SHA256),
        )

    def test_audit_combines_4h_and_mtls_but_never_signs_in(self):
        mtls=self.fake_mtls()
        with (
            patch.object(s.h,"run_combined") as combined,
            patch.object(s.f,"main") as firebase,
            patch.object(s.f,"execute") as execute,
            patch.object(s,"audit_local_receipt") as receipt,
            mtls[0], mtls[1], mtls[2],
            redirect_stdout(StringIO()) as output,
        ):
            self.assertEqual(s.main(["--source-sha",SHA]),0,output.getvalue())
        combined.assert_called_once_with(SHA)
        receipt.assert_called_once_with(SHA)
        firebase.assert_not_called()
        execute.assert_not_called()
        output=output.getvalue()
        self.assertIn("DB_R31_11_4I_COMBINED_READONLY=PASS",output)
        self.assertIn("DB_R31_11_4I_PRIOR_4F_SESSION_RECEIPT=NOT_PROVIDED",output)
        self.assertIn("DB_R31_11_4I_NEW_REAL_SESSIONS=NOT_TESTED_IN_AUDIT_MODE",output)
        self.assertIn("DB_R31_11_4I_EXTERNAL_MTLS_HTTPS=NOT_TESTED",output)
        self.assertIn("DB_R31_11_4I_FINANCIAL_APPLY=LOCKED",output)

    def test_private_auth_rejected_without_exact_explicit_approval(self):
        with (
            patch.object(s.h,"run_combined") as combined,
            patch.object(s.f,"main") as private,
            redirect_stdout(StringIO()) as output,
        ):
            self.assertEqual(
                s.main(["--source-sha",SHA,"--mode","private-auth"]),2)
        combined.assert_not_called()
        private.assert_not_called()
        self.assertIn("DB_R31_11_4I_BLOCK_REASON=QA_EXPLICIT_APPROVAL_MISSING",
                      output.getvalue())

    def test_genuine_test_result_receipt_only_has_fixed_status_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/"private"
            p=tmp/"qa.json"
            lines=sorted(s.REQUIRED_4F)
            def emit_only_expected(argv):
                self.assertIn("--approve",argv)
                self.assertIn(s.f.EXACT_APPROVAL,argv)
                for line in lines:
                    print(line)
                print("THIS IS A SECRET TOKEN NOT TO BE EXPOSED")
                return 0
            mtls=self.fake_mtls()
            with (
                patch.object(s,"RECEIPT_DIR",tmp),
                patch.object(s,"RECEIPT",p),
                patch.object(s.sys.stdin,"isatty",return_value=True),
                patch.object(s.f,"baseline"),
                patch.object(s.f,"no_preexisting_resources"),
                patch.object(s.f,"main",side_effect=emit_only_expected) as private,
                patch.object(s.h,"run_combined") as combined,
                mtls[0],mtls[1],mtls[2],
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(
                    s.main(["--source-sha",SHA,"--mode","private-auth",
                            "--approve",s.APPROVAL]),0)
            private.assert_called_once()
            self.assertEqual(combined.call_count,2)
            output=output.getvalue()
            self.assertNotIn("THIS IS A SECRET TOKEN",output)
            self.assertIn("DB_R31_11_4I_NEW_REAL_SESSIONS=PASS_TWO_OWNERS_PRIVATE_PG_ONLY",output)
            self.assertIn("DB_R31_11_4I_NEW_AUTH_RECEIPT=PASS_LOCAL_MODE0600_NO_SECRETS",output)
            self.assertEqual(stat.S_IMODE(tmp.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            data=json.loads(p.read_text())
            self.assertEqual(data["verified_results"],lines)
            self.assertEqual(data["source_sha"],SHA)
            self.assertNotIn("THIS IS A SECRET TOKEN",p.read_text())
            self.assertNotIn("idToken",p.read_text())
            self.assertEqual(data["external_mtls"],"NOT_TESTED")
            self.assertEqual(data["financial_apply"],"LOCKED")

    def test_partial_auth_result_must_stop_without_persisting_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"private"
            receipt=folder/"qa.json"
            def missing_one(argv):
                for line in sorted(s.REQUIRED_4F)[:-1]:
                    print(line)
                return 0
            mtls=self.fake_mtls()
            with (
                patch.object(s,"RECEIPT_DIR",folder),
                patch.object(s,"RECEIPT",receipt),
                patch.object(s.sys.stdin,"isatty",return_value=True),
                patch.object(s.f,"baseline"),
                patch.object(s.f,"no_preexisting_resources"),
                patch.object(s.f,"main",side_effect=missing_one),
                patch.object(s.h,"run_combined"),
                mtls[0],mtls[1],mtls[2],
                redirect_stdout(StringIO()) as output,
            ):
                self.assertEqual(
                    s.main(["--source-sha",SHA,"--mode","private-auth",
                            "--approve",s.APPROVAL]),2)
            self.assertFalse(receipt.exists())
            self.assertIn("STOP=DB_R31_11_4I_COMBINED_QA_REVIEW_REQUIRED",output.getvalue())
            self.assertNotIn("NEW_REAL_SESSIONS=PASS",output.getvalue())

    def test_local_receipt_is_recognized_without_claiming_independent_e2e(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"protected"
            file=folder/"qa.json"
            with (patch.object(s,"RECEIPT_DIR",folder),
                  patch.object(s,"RECEIPT",file),
                  redirect_stdout(StringIO()) as out):
                s.audit_local_receipt(SHA)
            self.assertIn("LOCAL_QA_AUTH_RECEIPT=NOT_PRESENT",out.getvalue())
            folder.mkdir(mode=0o700)
            payload={
                "schema":"DB-R31.11.4I-OPERATOR-QA-RECEIPT-V1",
                "classification":"local_operator_execution_not_independent_attestation",
                "status":"PASS_PRIVATE_IN_PROCESS_QA_ONLY",
                "source_sha":SHA,
                "qa_database":s.g.QA_DB,
                "caddy_fingerprint_sha256":s.h.EXPECTED_4G_CADDY_SHA256,
                "verified_results":sorted(s.REQUIRED_4F),
                "external_mtls":"NOT_TESTED",
                "prior_4f_execution":"NOT_ATTESTED",
                "financial_apply":"LOCKED",
                "r3112":"ACTIVE_QA_DESIGN_RELEASE_GATED",
                "production_release":"BLOCKED",
            }
            file.write_text(json.dumps(payload),encoding="utf-8")
            file.chmod(0o600)
            with (patch.object(s,"RECEIPT_DIR",folder),
                  patch.object(s,"RECEIPT",file),
                  redirect_stdout(StringIO()) as out):
                s.audit_local_receipt(SHA)
            self.assertIn("PRESENT_OPERATOR_REPORT_NOT_INDEPENDENT",out.getvalue())
            payload["source_sha"]="b"*40
            file.write_text(json.dumps(payload),encoding="utf-8")
            with (patch.object(s,"RECEIPT_DIR",folder),
                  patch.object(s,"RECEIPT",file)):
                with self.assertRaises(s.Blocked):
                    s.audit_local_receipt(SHA)
            file.chmod(0o644)
            with (patch.object(s,"RECEIPT_DIR",folder),
                  patch.object(s,"RECEIPT",file)):
                with self.assertRaises(s.Blocked):
                    s.audit_local_receipt(SHA)

    def test_existing_receipt_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"private"
            folder.mkdir(mode=0o700)
            receipt=folder/"qa.json"
            receipt.write_text("old",encoding="utf-8")
            with (patch.object(s,"RECEIPT_DIR",folder),
                  patch.object(s,"RECEIPT",receipt)):
                with self.assertRaises(s.Blocked):
                    s.receipt_preflight()
            self.assertEqual(receipt.read_text(),"old")

    def test_mtls_caddy_drift_and_wrong_version_fail_closed(self):
        mtls=self.fake_mtls()
        with (mtls[0],mtls[1],mtls[2]):
            s.verify_mtls_design_only()
        with (mtls[0],
              patch.object(s.g,"docker",return_value="v1.0.0"),
              mtls[2]):
            with self.assertRaises(s.Blocked):
                s.verify_mtls_design_only()
        with (mtls[0],mtls[1],
              patch.object(s.g,"caddy_preflight",return_value="0"*64)):
            with self.assertRaises(s.Blocked):
                s.verify_mtls_design_only()

    def test_filtered_status_output_drops_nonallowlisted_strings(self):
        output=StringIO()
        stream=s.FilteredStatusOutput(output)
        stream.write("hello=secret\n")
        stream.write("DB_R31_11_4F_TEST_A_PASSWORD_SIGNIN=PASS_REAL_FIREBASE\n")
        stream.write("SECRET=FIREBASE-UID-or-TOKEN\n")
        self.assertEqual(output.getvalue(),
           "DB_R31_11_4F_TEST_A_PASSWORD_SIGNIN=PASS_REAL_FIREBASE\n")
        self.assertEqual(stream.seen,{
           "DB_R31_11_4F_TEST_A_PASSWORD_SIGNIN=PASS_REAL_FIREBASE"})


if __name__=="__main__":
    unittest.main()
