"""Synthetic-only, zero-cloud security regression tests."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "dashboard_source"))
sys.path.insert(0, os.path.join(ROOT, "backend_source"))
from sbi_report_access import can_import_invoice
from invoice_import_security import authorized_import_caller

AUD = "https://private-backend.example.run.app"
EMAIL = "sbi-dashboard@example.iam.gserviceaccount.com"


class ImportPermissionsTests(unittest.TestCase):
    def user(self, **extra):
        claims = {"dil_dashboard": True, "sbi_invoice_importer": True}
        claims.update(extra)
        return SimpleNamespace(uid="user-1", disabled=False, custom_claims=claims)

    def test_missing_session_denied(self):
        self.assertFalse(can_import_invoice(None, {"uid": "user-1"}))

    def test_admin_or_report_permission_not_enough(self):
        user = self.user(sbi_invoice_importer=False, dil_admin=True, sbi_report_viewer=True)
        self.assertFalse(can_import_invoice(user, {"uid": "user-1"}))

    def test_identity_mismatch_denied(self):
        self.assertFalse(can_import_invoice(self.user(), {"uid": "user-2"}))

    def test_disabled_denied(self):
        user = self.user()
        user.disabled = True
        self.assertFalse(can_import_invoice(user, {"uid": "user-1"}))

    def test_explicit_import_claim_allowed(self):
        self.assertTrue(can_import_invoice(self.user(), {"uid": "user-1"}))

    def test_import_claim_does_not_override_missing_dashboard_entitlement(self):
        self.assertFalse(can_import_invoice(self.user(dil_dashboard=False), {"uid": "user-1"}))

    def test_non_boolean_import_claim_denied(self):
        self.assertFalse(can_import_invoice(self.user(sbi_invoice_importer="true"), {"uid": "user-1"}))

    def test_missing_claims_denied(self):
        user = self.user()
        user.custom_claims = None
        self.assertFalse(can_import_invoice(user, {"uid": "user-1"}))


class BackendServiceIdentityTests(unittest.TestCase):
    def req(self, token="abc"):
        return SimpleNamespace(headers={"Authorization": "Bearer " + token})

    def verifier(self, token, audience):
        return {"aud": audience, "email": EMAIL, "email_verified": True,
                "iss": "https://accounts.google.com"}

    def check(self, request=None, verifier=None, audience=AUD, caller_email=EMAIL):
        return authorized_import_caller(
            request or self.req(), verifier=verifier or self.verifier,
            audience=audience, caller_email=caller_email)

    def test_missing_backend_configuration_denies(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(authorized_import_caller(self.req(), verifier=self.verifier))

    def test_missing_bearer_denies_without_verifier(self):
        def forbidden(*args):
            raise AssertionError("Verifier unexpectedly called")
        request = SimpleNamespace(headers={})
        self.assertFalse(self.check(request=request, verifier=forbidden))

    def test_malformed_bearer_token_rejected_before_verification(self):
        def forbidden(*args):
            raise AssertionError("Malformed token reached verifier")
        for token in ("", "abc def", "abc\tdef", "abc\ndef", "abc\rdef", "abc\x00def", "abc\x7fdef"):
            with self.subTest(token=repr(token)):
                self.assertFalse(self.check(request=self.req(token), verifier=forbidden))

    def test_oversized_bearer_rejected_before_verification(self):
        def forbidden(*args):
            raise AssertionError("Oversized token reached verifier")
        self.assertFalse(self.check(request=self.req("x" * 12000), verifier=forbidden))

    def test_invalid_backend_identity_configuration_denied_before_verification(self):
        def forbidden(*args):
            raise AssertionError("Invalid configuration reached verifier")
        for audience, email in (
            ("http://private-backend.example.run.app", EMAIL),
            (AUD, "person@example.com"),
            ("", EMAIL),
            (AUD, ""),
        ):
            with self.subTest(audience=audience, email=email):
                self.assertFalse(self.check(
                    audience=audience, caller_email=email, verifier=forbidden))

    def test_exact_service_identity_allows(self):
        self.assertTrue(self.check())

    def test_wrong_audience_denied(self):
        self.assertFalse(self.check(verifier=lambda t, a: {
            **self.verifier(t, a), "aud": "https://wrong"}))

    def test_unverified_email_denied(self):
        self.assertFalse(self.check(verifier=lambda t, a: {
            **self.verifier(t, a), "email_verified": False}))

    def test_claimed_email_must_match_exactly(self):
        self.assertFalse(self.check(verifier=lambda t, a: {
            **self.verifier(t, a), "email": "other@example.iam.gserviceaccount.com"}))

    def test_non_boolean_email_verified_denied(self):
        self.assertFalse(self.check(verifier=lambda t, a: {
            **self.verifier(t, a), "email_verified": "true"}))

    def test_wrong_caller_denied(self):
        self.assertFalse(self.check(caller_email="other@example.iam.gserviceaccount.com"))

    def test_bad_issuer_denied(self):
        self.assertFalse(self.check(verifier=lambda t, a: {
            **self.verifier(t, a), "iss": "untrusted"}))

    def test_verifier_failure_denied(self):
        def broken(*args):
            raise RuntimeError("No token verifier")
        self.assertFalse(self.check(verifier=broken))


if __name__ == "__main__":
    unittest.main()
