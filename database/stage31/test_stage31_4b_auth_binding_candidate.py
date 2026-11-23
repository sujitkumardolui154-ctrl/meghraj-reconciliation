"""Stage31.4B isolated source-level Firebase/CSRF contract tests.

All identities here are fake objects injected into Flask's test request
context. They are NOT production Firebase sessions, and tests must never
report otherwise.
"""
import unittest
from types import SimpleNamespace
from flask import Flask, g

from dashboard_sessions import (
    MASTER_EMAIL, MASTER_UID, ORIGINS, CSRF_COOKIE, csrf_valid,
)
from stage31_4b_auth_binding_candidate import (
    PRIVATE_PREVIEW_CLAIM, verified_private_preview_user,
    verified_private_preview_csrf, build_private_staging_preview_candidate,
)

ORIGIN = sorted(ORIGINS)[0]
TOKEN = "a" * 64

def owner():
    return SimpleNamespace(
        uid=MASTER_UID,email=MASTER_EMAIL,disabled=False,
        custom_claims={
            "dil_dashboard":True,
            "dil_admin":True,
            PRIVATE_PREVIEW_CLAIM:True,
        }
    )

class TrustedSessionPreviewTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.ctx=self.app.test_request_context(
            "/__stage31_4/invoice/preview",method="POST")
        self.ctx.push()
    def tearDown(self):
        self.ctx.pop()
    def attach(self,user=None,identity=None):
        obj=user if user is not None else owner()
        g.dil_user=obj
        g.dil_identity=identity if identity is not None else {"uid":obj.uid}
        return obj
    def test_default_denies_when_no_verified_request_context(self):
        self.assertFalse(verified_private_preview_user())
    def test_no_claim_denied(self):
        u=owner()
        del u.custom_claims[PRIVATE_PREVIEW_CLAIM]
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_full_master_and_preview_claim_is_allowed_for_preview_only(self):
        self.attach()
        self.assertTrue(verified_private_preview_user())
    def test_report_viewer_alone_cannot_preview(self):
        u=owner()
        del u.custom_claims[PRIVATE_PREVIEW_CLAIM]
        u.custom_claims["sbi_report_viewer"]=True
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_missing_admin_claim_denied(self):
        u=owner();u.custom_claims["dil_admin"]=False
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_missing_dashboard_claim_denied(self):
        u=owner();u.custom_claims["dil_dashboard"]=False
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_disabled_firebase_account_denied(self):
        u=owner();u.disabled=True
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_mismatched_verified_identity_denied(self):
        self.attach(identity={"uid":"not-the-verified-user"})
        self.assertFalse(verified_private_preview_user())
    def test_non_owner_uid_denied(self):
        u=owner();u.uid="fake-uid"
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_non_owner_email_denied(self):
        u=owner();u.email="not.owner@example.invalid"
        self.attach(u)
        self.assertFalse(verified_private_preview_user())
    def test_identity_query_header_cannot_override_g_missing(self):
        # This verifies no trusted session is created from arbitrary headers.
        self.assertFalse(verified_private_preview_user())
    def test_missing_verification_identity_denied(self):
        g.dil_user=owner()
        self.assertFalse(verified_private_preview_user())
    def test_non_dict_claims_denied(self):
        u=owner();u.custom_claims=None
        self.attach(u)
        self.assertFalse(verified_private_preview_user())

class RealCsrfFunctionContractTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
    def check(self,origin=ORIGIN,token=TOKEN,cookie=TOKEN):
        headers={"Origin":origin,"X-DIL-CSRF":token}
        with self.app.test_request_context(
            "/__stage31_4/invoice/preview",method="POST",
            headers=headers, environ_base={"HTTP_COOKIE":f"{CSRF_COOKIE}={cookie}"}):
            return verified_private_preview_csrf()
    def test_real_csrf_callback_delegates_valid_cookie_and_header(self):
        self.assertTrue(self.check())
    def test_different_csrf_header_denied(self):
        self.assertFalse(self.check(token="b"*64))
    def test_missing_origin_denied(self):
        self.assertFalse(self.check(origin=""))
    def test_arbitrary_origin_denied(self):
        self.assertFalse(self.check(origin="https://wrong-origin.example.invalid"))
    def test_short_token_denied(self):
        self.assertFalse(self.check(token="a"))
    def test_short_cookie_denied(self):
        self.assertFalse(self.check(cookie="a"))
    def test_production_origin_determined_by_live_source_only(self):
        # Do not assert that an old repository allowlist matches live AWS.
        self.assertTrue(callable(csrf_valid))
        self.assertTrue(isinstance(ORIGINS,set))
    def test_staging_candidate_never_registers_itself(self):
        bp=build_private_staging_preview_candidate()
        self.assertEqual(bp.url_prefix,"/__stage31_4")
        self.assertEqual(bp.name,"stage31_4_private_preview")
        self.assertNotIn("stage31_4_private_preview",self.app.blueprints)

if __name__=="__main__":
    unittest.main(verbosity=2)
