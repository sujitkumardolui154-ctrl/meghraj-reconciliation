"""QA policy proof: no false PASS, no duplicate whole-suite rerun.

Offline synthetic evidence only. No AWS, Firestore, bank or GitHub mutations.
"""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError


ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "qa_module_policy",ROOT/"tools/qa_module_policy.py"
)
policy=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
HEAD="a"*40
OTHER="b"*40
RUN_NAME="SBI invoice generation + GST combined QA (isolated)"


def receipt(sha=HEAD,status="completed",conclusion="success",run_id=55,
            name=RUN_NAME):
    return {"id":run_id,"head_sha":sha,"status":status,
            "conclusion":conclusion,"name":name}


class ModulePolicyTests(unittest.TestCase):
    def test_invoice_awb_edit_requires_only_relevant_modules(self):
        groups,reason=policy.select_groups(
            ["dashboard_source/invoice_annexure_intake.py",
             "dashboard_source/invoice_gst_ui.js"])
        self.assertEqual(groups,["invoice_db","invoice_ui"])
        self.assertEqual(reason,["MODULE_SCOPE_SELECTED"])
        self.assertNotIn("credit_note",groups)
        self.assertNotIn("gst",groups)

    def test_credit_note_modules_are_isolated_from_gst_contract(self):
        groups,_=policy.select_groups(
            ["dashboard_source/credit_note_core.py"])
        self.assertEqual(groups,["invoice_db","credit_note","historical"])
        self.assertNotIn("gst",groups)
        self.assertNotIn("branch_master",groups)

    def test_doc_only_requires_no_financial_QA(self):
        groups,reason=policy.select_groups([
            "docs/QA_MODULE_EXECUTION_RULES.md",
            "staging/invoice-gst/APPROVED_INVOICE_UI_V2_IMPLEMENTATION_20261128.md"])
        self.assertEqual(groups,[])
        self.assertEqual(reason,["NO_INVOICE_MODULE_CODE_CHANGED"])

    def test_unmapped_change_fails_closed_full_scope(self):
        groups,reason=policy.select_groups(["backend_source/unknown_new_writer.py"])
        self.assertEqual(groups,list(policy.GROUPS))
        self.assertEqual(reason,["UNMAPPED_CHANGES_REQUIRE_FULL_QA"])

    def test_shared_gateway_and_invoice_schema_trigger_all(self):
        for path in ("dashboard_source/production_gateway.py",
                     "staging/invoice-gst/005_credit_note_registry.sql",
                     ".github/workflows/sbi-invoice-gst-combined-qa.yml"):
            with self.subTest(path=path):
                groups,_=policy.select_groups([path])
                self.assertEqual(groups,list(policy.GROUPS))

    def test_exact_head_success_reused_but_unrelated_not(self):
        past=[receipt(OTHER),receipt()]
        self.assertTrue(policy.prior_success_for_exact_sha(
            past,HEAD,RUN_NAME,current_run_id=99))
        self.assertTrue(policy.prior_success_for_exact_sha(
            past,OTHER,RUN_NAME,current_run_id=12))
        # Never claim a full workflow PASS from another workflow.
        self.assertFalse(policy.prior_success_for_exact_sha(
            [receipt(name="Different workflow")],HEAD,RUN_NAME))
        self.assertFalse(policy.prior_success_for_exact_sha(
            [receipt(conclusion="failure")],HEAD,RUN_NAME))
        self.assertFalse(policy.prior_success_for_exact_sha(
            [receipt(status="in_progress",conclusion=None)],HEAD,RUN_NAME))
        self.assertFalse(policy.prior_success_for_exact_sha(
            [receipt()],HEAD,RUN_NAME,current_run_id=55))

    def test_plan_reuses_only_same_exact_commit_and_workflow(self):
        p=policy.build_plan(
            ["dashboard_source/invoice_gst_ui.js"],head_sha=HEAD,
            github_evidence=[receipt()],workflow_exists=True)
        self.assertEqual(p["decision"],"REUSE_APPROVED_EXACT_SHA_QA")
        self.assertTrue(p["reused"])
        self.assertEqual(p["financial_apply"],"LOCKED")
        self.assertEqual(p["production_deployment"],"NOT_AUTHORIZED")
        p=policy.build_plan(
            ["dashboard_source/invoice_gst_ui.js"],head_sha=HEAD,
            github_evidence=[receipt(OTHER)],workflow_exists=True)
        self.assertEqual(p["decision"],"RUN_SELECTED_QA")
        self.assertFalse(p["reused"])
        self.assertEqual(p["selected_groups"],["invoice_db","invoice_ui"])

    def test_api_unavailable_fails_closed_to_running_required_tests(self):
        p=policy.build_plan(
            ["dashboard_source/invoice_gst_ui.js"],head_sha=HEAD,
            github_evidence=None,workflow_exists=True)
        self.assertEqual(p["decision"],"RUN_SELECTED_QA")
        self.assertIn("GITHUB_EXISTING_QA_NOT_VERIFIED_RUN_REQUIRED",
                      p["reason_codes"])

    def test_release_does_not_reuse_previous_synthetic_pass(self):
        p=policy.build_plan(
            ["dashboard_source/invoice_gst_ui.js"],head_sha=HEAD,
            github_evidence=[receipt()],workflow_exists=True,
            event="production_release")
        self.assertEqual(p["decision"],"RUN_SELECTED_QA")
        self.assertEqual(p["selected_groups"],list(policy.GROUPS))
        self.assertFalse(p["reused"])

    def test_missing_workflow_blocks_not_waives(self):
        p=policy.build_plan(
            ["dashboard_source/invoice_gst_ui.js"],head_sha=HEAD,
            github_evidence=[receipt()],workflow_exists=False)
        self.assertEqual(p["decision"],"BLOCK_REQUIRED_WORKFLOW_MISSING")
        self.assertFalse(p["reused"])

    def test_policy_itself_is_separate_module(self):
        groups,_=policy.select_groups(
            ["tools/qa_module_policy.py","tests/test_qa_module_policy.py"])
        self.assertEqual(groups,[])

    def test_github_request_is_get_only_never_workflow_dispatch(self):
        seen=[]
        def fake_request(url,headers,method):
            seen.append((url,method))
            return object()
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*_):pass
        with patch.object(policy,"Request",side_effect=fake_request), \
             patch.object(policy,"urlopen",return_value=Reply()), \
             patch.object(policy.json,"load",return_value={
                 "workflow_runs":[receipt()]
             }):
            runs=policy.github_runs(
                "sujitkumardolui154-ctrl/meghraj-reconciliation",
                "sbi-invoice-gst-combined-qa.yml",HEAD
            )
        self.assertEqual(runs[0]["head_sha"],HEAD)
        self.assertEqual(seen[0][1],"GET")
        self.assertIn("head_sha="+HEAD,seen[0][0])
        self.assertNotIn("/dispatches",seen[0][0])


if __name__=="__main__":
    unittest.main()
