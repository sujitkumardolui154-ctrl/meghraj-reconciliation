"""Offline-only tests for existing sslip Firebase HTTPS acceptance harness."""
import importlib.util
import json
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("existing_firebase_acceptance",
    HERE/"verify_firebase_https_acceptance.py")
f=importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

class Cookie:
    def __init__(self, secure=True,path="/",domain_specified=False,rest=None):
        self.name="__Host-dil_session"
        self.secure=secure
        self.path=path
        self.domain_specified=domain_specified
        self._rest=rest if rest is not None else {"HttpOnly":None,"SameSite":"Lax"}

class AcceptanceHarnessTests(TestCase):
    def test_host_exact_not_new_platform(self):
        self.assertEqual(f.ORIGIN,"https://sbi-preview.13-232-241-221.sslip.io")
        self.assertNotIn("ts.net",f.ORIGIN)

    def test_session_cookie_requires_secure_host_only_httponly_lax(self):
        self.assertTrue(f.has_secure_host_cookie([Cookie()],f.SESSION_COOKIE))
        for opts in ({"secure":False},{"path":"/auth"},{"domain_specified":True},
                     {"rest":{"SameSite":"Lax"}},
                     {"rest":{"HttpOnly":None,"SameSite":"None"}}):
            with self.subTest(opts=opts):
                self.assertFalse(f.has_secure_host_cookie([Cookie(**opts)],f.SESSION_COOKIE))

    def test_does_not_accept_duplicate_or_missing_session_cookies(self):
        self.assertFalse(f.has_secure_host_cookie([],f.SESSION_COOKIE))
        self.assertFalse(f.has_secure_host_cookie([Cookie(),Cookie()],f.SESSION_COOKIE))

    def test_origin_preflight_denies_wrong_origin(self):
        with patch.object(f,"client",return_value=(object(),object())), \
             patch.object(f,"csrf_start",return_value="a"*64), \
             patch.object(f,"fetch",side_effect=[(400,b""),(400,b"")]):
            with self.assertRaises(f.Blocked):
                f.csrf_origin_check()

    def test_origin_preflight_rejects_correct_origin_403(self):
        with patch.object(f,"client",return_value=(object(),object())), \
             patch.object(f,"csrf_start",return_value="a"*64), \
             patch.object(f,"fetch",return_value=(403,b"")):
            with self.assertRaises(f.Blocked):
                f.csrf_origin_check()

    def test_origin_preflight_accepts_only_400_403_403(self):
        with patch.object(f,"client",return_value=(object(),object())), \
             patch.object(f,"csrf_start",return_value="a"*64), \
             patch.object(f,"fetch",side_effect=[(400,b""),(403,b""),(403,b"")]):
            self.assertTrue(f.csrf_origin_check())

    def test_release_policy_remains_locked(self):
        p=json.loads((HERE/"existing_preview_target_policy.json").read_text("utf-8"))
        self.assertEqual(p["financial_apply"],"LOCKED")
        self.assertEqual(p["production_release"],"BLOCKED")
        self.assertIs(p["actual_deployment_performed"],False)

if __name__=="__main__":
    main()
