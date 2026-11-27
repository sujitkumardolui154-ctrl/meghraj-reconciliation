"""Offline-only R31.11.4F in-process auth and private route regression.

Faked Firebase tokens and fake database read only. No real secrets / AWS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dashboard_source"))
sys.path.insert(0,str(ROOT/"staging/aws_login_v150"))

import dashboard_sessions as sessions
import r31_11_4f_private_session_probe as probe
import r31_11_4_runtime_rls_blueprint as blueprint

USERS={
    "ci-a":SimpleNamespace(
        uid="ci-a", email="qa-a@example.invalid", email_verified=True,
        disabled=False, display_name="",
        custom_claims={"dil_dashboard":True,"dil_admin":False}),
    "ci-b":SimpleNamespace(
        uid="ci-b", email="qa-b@example.invalid", email_verified=True,
        disabled=False, display_name="",
        custom_claims={"dil_dashboard":True,"dil_admin":False}),
}


def mock_verify_id_token(token,**_):
    if token not in ("ci-id-a","ci-id-b"):
        raise sessions.auth.InvalidIdTokenError("invalid")
    uid="ci-a" if token=="ci-id-a" else "ci-b"
    return {"uid":uid,"auth_time":__import__("time").time(),
            "firebase":{"sign_in_provider":"password"}}


def mock_verify_session(cookie,**_):
    if cookie not in ("ci-cookie-a","ci-cookie-b"):
        raise sessions.auth.InvalidSessionCookieError("invalid")
    return {"uid":"ci-a" if cookie=="ci-cookie-a" else "ci-b"}


def mock_cookie(token,**_):
    return {"ci-id-a":"ci-cookie-a","ci-id-b":"ci-cookie-b"}[token]


class PrivateProbeTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.db_reads=[]
        def strict_read(user,limit=20):
            self.db_reads.append((user.uid,limit))
            return []
        self.patchers=[
            patch.dict(os.environ,{
                "SBI_R31_PRIVATE_STAGING_ENABLED":probe.STAGING_FLAG,
                "SBI_R31_11_4_RUNTIME_ENABLED":probe.QA_FLAG,
            }),
            patch.object(sessions,"firebase_app",return_value=object()),
            patch.object(sessions.auth,"verify_id_token",
                         side_effect=mock_verify_id_token),
            patch.object(sessions.auth,"verify_session_cookie",
                         side_effect=mock_verify_session),
            patch.object(sessions.auth,"get_user",
                         side_effect=lambda uid,**_:USERS[uid]),
            patch.object(sessions.auth,"create_session_cookie",
                         side_effect=mock_cookie),
            patch.object(blueprint,"read_tenant_source_only",
                         side_effect=strict_read),
        ]
        for p in self.patchers:
            p.start()
        self.app=probe.minimal_private_app()

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()

    def test_two_independent_real_routes_mocked_backend(self):
        self.assertTrue(probe.run_owner(self.app,"ci-id-a","ci-b","a"))
        self.assertTrue(probe.run_owner(self.app,"ci-id-b","ci-a","b"))
        self.assertEqual(self.db_reads,[("ci-a",2),("ci-b",2)])

    def test_anonymous_and_invalid_cookie_denied(self):
        probe.check_anonymous_invalid(self.app)
        self.assertEqual(self.db_reads,[])

    def test_wrong_login_token_rejected(self):
        with self.assertRaises(probe.TestBlocked):
            probe.run_owner(self.app,"ci-id-invalid","ci-b","a")
        self.assertEqual(self.db_reads,[])

    def test_binding_requires_two_known_role_names(self):
        valid={
            "version":1,"database":probe.DB,
            "bindings":[
              {"pg_login_role":"r3113_login_a","firebase_uid":"ci-a"},
              {"pg_login_role":"r3113_login_b","firebase_uid":"ci-b"},
            ]
        }
        import r31_11_4_runtime_rls_adapter as adapter
        with patch.object(adapter,"_secure_file",return_value=json.dumps(valid)):
            self.assertEqual(probe.real_binding(),{
                "r3113_login_a":"ci-a","r3113_login_b":"ci-b"})
        valid["bindings"][1]["firebase_uid"]="ci-a"
        with patch.object(adapter,"_secure_file",return_value=json.dumps(valid)):
            with self.assertRaises(probe.TestBlocked):
                probe.real_binding()


if __name__=="__main__":
    unittest.main()
