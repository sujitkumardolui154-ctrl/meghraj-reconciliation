"""Pure synthetic tests for approved Firebase role provisioning plan."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "sbi_reporting_role_provision",
    ROOT/"tools"/"sbi_reporting_role_provision.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
UID="synthetic-uid"
EMAIL="synthetic@example.invalid"


def user(**claims):
    return SimpleNamespace(uid=UID,email=EMAIL,disabled=False,custom_claims=claims)


class RoleProvisionTests(unittest.TestCase):
    def test_default_plan_does_not_mutate_user_or_apply(self):
        source=user(dil_dashboard=True,dil_admin=True,custom_key="untouched")
        original,updated=module.plan(source,UID,EMAIL,grant_general=True)
        self.assertEqual(source.custom_claims, original)
        self.assertTrue(updated[module.GENERAL])
        self.assertTrue(updated["dil_admin"])
        self.assertNotIn(module.CHANGES,updated)
        self.assertEqual(len(module.claims_hash(original)),64)

    def test_change_report_requires_general_role(self):
        with self.assertRaises(module.RoleProvisionBlocked):
            module.plan(user(dil_dashboard=True),UID,EMAIL,grant_changes=True)
        before,after=module.plan(user(dil_dashboard=True,sbi_report_viewer=True),
                                 UID,EMAIL,grant_changes=True)
        self.assertTrue(after[module.GENERAL])
        self.assertTrue(after[module.CHANGES])

    def test_no_implicit_access_to_disabled_or_other_users(self):
        sample=user(dil_dashboard=True)
        cases=[
            (sample,"different",EMAIL),
            (sample,UID,"different@example.invalid"),
            (SimpleNamespace(uid=UID,email=EMAIL,disabled=True,custom_claims={"dil_dashboard":True}),UID,EMAIL),
            (user(),UID,EMAIL),
        ]
        for supplied,uid,email in cases:
            with self.subTest(uid=uid,email=email):
                with self.assertRaises(module.RoleProvisionBlocked):
                    module.plan(supplied,uid,email,grant_general=True)

    def test_explicit_role_request_required(self):
        with self.assertRaises(module.RoleProvisionBlocked):
            module.plan(user(dil_dashboard=True),UID,EMAIL)

    def test_claim_hash_is_order_invariant(self):
        self.assertEqual(module.claims_hash({"a":1,"b":2}),
                         module.claims_hash({"b":2,"a":1}))

    def test_no_financial_roles_granted(self):
        source=(ROOT/"tools"/"sbi_reporting_role_provision.py").read_text()
        self.assertIn('parser.add_argument("--apply", action="store_true")',source)
        self.assertIn("INTERACTIVE_CONFIRMATION_REQUIRED",source)
        self.assertIn("SIGNED_IN_HTTP_E2E=STILL_REQUIRED",source)
        for forbidden in ("firestore.Client(", "gcloud run deploy",
                          "firebase_admin.firestore", "dil_admin\"] = True",
                          "database_write\"] = True"):
            self.assertNotIn(forbidden,source)


if __name__=="__main__":
    unittest.main()
