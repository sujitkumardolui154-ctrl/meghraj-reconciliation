"""Targeted offline source-review checks. No AWS, Firebase, SQL or HTTP."""
import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("r31_source_review",HERE/"r31_inplace_source_security_review.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class InplaceSourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=mod.load_sources()
        import json
        cls.policy=json.loads((mod.ROOT/
           "staging/existing_preview_deployment/existing_preview_target_policy.json")
           .read_text("utf-8"))

    def test_review_matches_existing_sources_without_modifying_them(self):
        results=mod.source_checks(self.sources,self.policy)
        self.assertTrue(all(results.values()),results)
        self.assertTrue(results["BROAD_FLAG_ALSO_REGISTERS_WRITE_QA_ROUTE"])

    def test_existing_sslip_target_must_remain(self):
        policy=deepcopy(self.policy)
        policy["user_required_url"]="https://alternative.invalid/login"
        self.assertFalse(mod.source_checks(self.sources,policy)["TARGET_EXACT"])

    def test_release_locks_cannot_be_relaxed(self):
        for key,value in (("financial_apply","UNLOCKED"),
                          ("production_release","APPROVED"),
                          ("actual_deployment_performed",True)):
            p=deepcopy(self.policy)
            p[key]=value
            with self.subTest(key=key):
                self.assertFalse(mod.source_checks(self.sources,p)["RELEASE_LOCKS"])

    def test_detects_missing_server_side_cookie_validation(self):
        sources=deepcopy(self.sources)
        sources["sessions"]=sources["sessions"].replace("check_revoked=True","check_revoked=False")
        self.assertFalse(mod.source_checks(sources,self.policy)["EXISTING_LOGIN_AUTH_CHAIN"])

    def test_detects_missing_readonly_transaction(self):
        sources=deepcopy(self.sources)
        sources["adapter"]=sources["adapter"].replace("SET TRANSACTION READ ONLY","SET TRANSACTION READ WRITE")
        self.assertFalse(mod.source_checks(sources,self.policy)["QA_POSTGRES_FIXED_READ_ONLY"])

    def test_detects_production_database_target_drift(self):
        sources=deepcopy(self.sources)
        sources["adapter"]=sources["adapter"].replace(
            'QA_DB = "sbi_r31_11_4_auth_qa_20261126"',
            'QA_DB = "sbi_reconciliation_main"')
        self.assertFalse(mod.source_checks(sources,self.policy)["QA_POSTGRES_FIXED_READ_ONLY"])

    def test_detects_broad_qa_sync_write_risk(self):
        sources=deepcopy(self.sources)
        sources["stage"]=sources["stage"].replace("persist_qa_source(","disabled_qa_source(")
        self.assertFalse(mod.source_checks(sources,self.policy)[
            "BROAD_FLAG_ALSO_REGISTERS_WRITE_QA_ROUTE"])

    def test_public_baseline_must_not_bundle_restricted_adapter(self):
        sources=deepcopy(self.sources)
        sources["baseline_image"]+="\nCOPY r31_11_4_runtime_rls_adapter.py /app/\n"
        self.assertFalse(mod.source_checks(sources,self.policy)[
            "BASELINE_IMAGE_OMITS_R3114"])

    def test_get_only_source_route_and_existing_api_routing(self):
        checks=mod.source_checks(self.sources,self.policy)
        self.assertTrue(checks["RLS_ENDPOINT_READ_ONLY_BY_SOURCE"])
        self.assertTrue(checks["CADDY_SOURCE_EXISTING_API_PROXY"])
        self.assertTrue(checks["FINANCIAL_CATCHALL_DENY_IN_SOURCE"])

if __name__=="__main__":
    unittest.main()
