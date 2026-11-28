"""Only offline tests for R31 existing-host RLS route metadata checker."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("rls_route_preflight",HERE/"verify_existing_rls_route_metadata_readonly.py")
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class RouteTests(unittest.TestCase):
    def test_canonical_existing_sslip_host(self):
        self.assertEqual(m.URL,"https://sbi-preview.13-232-241-221.sslip.io")
        self.assertEqual(m.ROUTE,"/api/r31-private-qa/tenant-rls-source-r3114")

    def test_private_flags_require_exact_expected_values(self):
        self.assertEqual(m.FLAGS["SBI_R31_11_4_RUNTIME_ENABLED"],
                         "private-firebase-rls-auth-acceptance-v1")
        self.assertEqual(m.FLAGS["SBI_R31_PRIVATE_STAGING_ENABLED"],
                         "isolated-ownerqa-firebase-csrf-v1")

    def test_anonymous_probe_returns_only_status(self):
        with patch.object(m,"process",return_value=(0,"401 0")):
            self.assertEqual(m.anonymous_probe(),"HTTP_401")
        with patch.object(m,"process",return_value=(0,"200 0")):
            self.assertEqual(m.anonymous_probe(),"HTTP_200")

    def test_tls_failure_never_claims_verified(self):
        for result in ((60,"000 60"),(0,"200 19"),(0,"invalid"),(7,"")):
            with self.subTest(result=result):
                with patch.object(m,"process",return_value=result):
                    self.assertEqual(m.anonymous_probe(),"NOT_VERIFIED")

    def test_no_registered_api_claim_from_anonymous_status(self):
        from inspect import getsource
        self.assertIn("R31_ROUTE_ANONYMOUS_STATUS_PROVES_REGISTRATION=NO",
                      getsource(m.main))
        self.assertIn("R31_ROUTE_REAL_TWO_OWNER_RLS_HTTPS=NOT_TESTED",
                      getsource(m.main))

if __name__=="__main__":
    unittest.main()
