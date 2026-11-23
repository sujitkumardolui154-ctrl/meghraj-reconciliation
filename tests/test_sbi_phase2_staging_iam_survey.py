"""Synthetic tests of anonymous project-only staging IAM survey."""
import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "staging/gcp_owner_private"
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("staging_iam_survey", ROOT / "assess_stage_iam_readonly.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from collect_phase2_readiness import render

SA = [
    {"email": "production-service@example.com"},
    {"email": "sbi-stage-readonly@example.com"},
    {"email": "private-canary@example.com"},
]
POLICY = {"bindings": [
    {"role": "roles/logging.logWriter",
     "members": ["serviceAccount:sbi-stage-readonly@example.com"]},
    {"role": "roles/datastore.user",
     "members": ["serviceAccount:private-canary@example.com"]},
    {"role": "roles/editor", "members": ["group:admins@example.com"]},
]}


class StageIAMSurveyTests(TestCase):
    def test_01_names_turned_to_counts_only(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["staging_name_candidates"],2)
        output=render(result)
        for private in ["sbi-stage-readonly@", "private-canary@", "production-service@","example.com"]:
            self.assertNotIn(private,output)

    def test_02_low_priv_role_without_finance_marked_neutral(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["candidates"][1]["potential_finance_or_privilege_bindings_count"],0)

    def test_03_datastore_user_flagged(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["candidates"][0]["potential_finance_or_privilege_bindings_count"],1)

    def test_04_group_binding_does_not_falsely_become_direct(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["candidates"][0]["direct_project_bindings_count"],1)
        self.assertEqual(result["candidates"][1]["direct_project_bindings_count"],1)

    def test_05_missing_policy_is_unknown(self):
        result=m.summarize(SA,None)
        self.assertFalse(result["project_iam_policy_read"])
        self.assertTrue(all(c["direct_project_bindings_count"]=="NOT_VERIFIED"
                            for c in result["candidates"]))

    def test_06_resource_inherited_permissions_never_claimed_absent(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["effective_firestore_financial_write_denial"],"NOT_VERIFIED")
        self.assertEqual(result["inherited_folder_org_resource_grants"],"NOT_VERIFIED")
        self.assertEqual(result["stage_iam_release"],"BLOCKED_PENDING_EFFECTIVE_PERMISSIONS")

    def test_07_candidate_stage_never_authorized(self):
        result=m.summarize(SA,POLICY)
        self.assertTrue(all(not c["stage_identity_approved_for_deploy"] for c in result["candidates"]))

    def test_08_changed_email_not_leaked(self):
        result=m.summarize([{"email":"secret-finance-preview@example.org"}],{"bindings":[]})
        self.assertNotIn("secret-finance",render(result))

    def test_09_unrecognized_role_remains_not_allowlisted(self):
        result=m.summarize(
            [SA[1]],{"bindings":[{"role":"projects/demo/roles/custom", "members":[
                "serviceAccount:sbi-stage-readonly@example.com"
            ]}]})
        self.assertEqual(result["candidates"][0]["not_in_narrow_readonly_allowlist_count"],1)
        self.assertFalse(result["candidates"][0]["stage_identity_approved_for_deploy"])

    def test_10_conditional_binding_treated_as_conditional_not_denied(self):
        result=m.summarize([SA[1]],{"bindings":[{"role":"roles/datastore.user","condition":{"title":"condition"},"members":[
            "serviceAccount:sbi-stage-readonly@example.com"
        ]}]})
        self.assertEqual(result["candidates"][0]["conditional_bindings_count"],1)
        self.assertEqual(result["candidates"][0]["potential_finance_or_privilege_bindings_count"],1)

    def test_11_service_account_listing_denied_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"SERVICE_ACCOUNT_LIST_NOT_VERIFIED"):
            m.summarize(None,POLICY)

    def test_12_no_upload_gcp_iam_content(self):
        result=m.summarize(SA,POLICY)
        self.assertEqual(result["financial_database_writes"],0)
        self.assertEqual(result["prod_traffic_or_iam_mutations"],0)
        self.assertEqual(result["production_release"],"BLOCKED")


if __name__ == "__main__":
    main()
