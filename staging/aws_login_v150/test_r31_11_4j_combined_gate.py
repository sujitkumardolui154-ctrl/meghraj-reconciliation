"""R31.11.4J combined security controller tests (all AWS calls mocked)."""
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

import r31_11_4j_combined_mtls_gate as j


SHA="a"*40


class CombinedMTLSTests(unittest.TestCase):
    def mock_all(self):
        return [
            patch.object(j.h,"run_combined"),
            patch.object(j.i,"verify_mtls_design_only"),
            patch.object(j.i.RECEIPT.__class__,"is_file",return_value=True),
            patch.object(j.i.RECEIPT.__class__,"is_symlink",return_value=False),
            patch.object(j.i,"audit_local_receipt"),
            patch.object(j.g,"caddy_preflight",
                         return_value=j.h.EXPECTED_4G_CADDY_SHA256),
            patch.object(j.g,"check_database_isolation"),
            patch.object(j.g,"ephemeral_cleanup"),
            patch.object(j.tls,"run_synthetic"),
        ]

    def test_default_is_all_readonly_not_tls_listener(self):
        checks=self.mock_all()
        with (checks[0] as h,checks[1],checks[2],checks[3],
              checks[4] as receipt,checks[5],checks[6],checks[7],
              checks[8] as synthetic,redirect_stdout(StringIO()) as out):
            code=j.main(["--source-sha",SHA])
        self.assertEqual(code,0)
        h.assert_called_once_with(SHA)
        receipt.assert_called_once_with(j.APPROVED_4I_SOURCE_SHA)
        synthetic.assert_not_called()
        self.assertIn("DB_R31_11_4J_MODE=READONLY_NO_NETWORK_LISTENER",out.getvalue())
        self.assertIn("DB_R31_11_4J_EXTERNAL_MTLS_HTTPS=NOT_TESTED",out.getvalue())
        self.assertIn("DB_R31_11_4J_FINANCIAL_APPLY=LOCKED",out.getvalue())

    def test_explicit_loopback_runs_disposable_tls_then_rechecks_database(self):
        checks=self.mock_all()
        with (checks[0] as h,checks[1],checks[2],checks[3],
              checks[4],checks[5] as caddy,checks[6] as db,
              checks[7] as cleanup,checks[8] as synthetic,
              redirect_stdout(StringIO()) as out):
            code=j.main(["--source-sha",SHA,"--mode","loopback"])
        self.assertEqual(code,0)
        synthetic.assert_called_once()
        self.assertEqual(h.call_count,2)
        self.assertEqual(caddy.call_count,2)
        self.assertEqual(db.call_count,2)
        self.assertEqual(cleanup.call_count,2)
        self.assertIn("MODE=SYNTHETIC_LOOPBACK_ONLY",out.getvalue())
        self.assertIn("POST_LOOPBACK_DB_CADDY=PASS_UNCHANGED",out.getvalue())
        self.assertIn("EXTERNAL_MTLS_HTTPS=NOT_TESTED",out.getvalue())

    def test_missing_local_auth_receipt_denies_synthetic_execution(self):
        checks=self.mock_all()
        with (checks[0],checks[1],
              patch.object(j.i.RECEIPT.__class__,"is_file",return_value=False),
              checks[3],checks[4],checks[5],checks[6],checks[7],
              checks[8] as synthetic,redirect_stdout(StringIO()) as out):
            code=j.main(["--source-sha",SHA,"--mode","loopback"])
        self.assertEqual(code,2)
        synthetic.assert_not_called()
        self.assertIn("STOP=DB_R31_11_4J_SECURITY_ACCEPTANCE_REVIEW_REQUIRED",
                      out.getvalue())
        self.assertIn("PRODUCTION_RELEASE=BLOCKED",out.getvalue())

    def test_caddy_drift_denies_synthetic_execution(self):
        checks=self.mock_all()
        with (checks[0],checks[1],checks[2],checks[3],checks[4],
              patch.object(j.g,"caddy_preflight",return_value="0"*64),
              checks[6],checks[7],checks[8] as synthetic,
              redirect_stdout(StringIO()) as out):
            code=j.main(["--source-sha",SHA,"--mode","loopback"])
        self.assertEqual(code,2)
        synthetic.assert_not_called()
        self.assertNotIn("COMBINED_PREPARATION=PASS",out.getvalue())

    def test_raw_cloud_exception_is_suppressed(self):
        checks=self.mock_all()
        with (patch.object(j.h,"run_combined",
                           side_effect=RuntimeError("PRIVATE_FIREBASE_SECRET_ABC")),
              redirect_stdout(StringIO()) as out):
            code=j.main(["--source-sha",SHA])
        self.assertEqual(code,2)
        self.assertNotIn("PRIVATE_FIREBASE_SECRET_ABC",out.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",out.getvalue())


if __name__=="__main__":
    unittest.main()
