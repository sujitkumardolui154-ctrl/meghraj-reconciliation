"""R31.11.4E source contract: simulated Firebase sessions, no live tokens.

The test exercises the actual install_sessions() middleware and private route,
but the Firebase SDK calls and DB read are MOCKED. It must never be presented
as real two-user AWS end-to-end authentication acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboard_source"))
import dashboard_sessions as sessions
import r31_11_4_runtime_rls_blueprint as route

FLAGS = {
    "SBI_R31_PRIVATE_STAGING_ENABLED": "isolated-ownerqa-firebase-csrf-v1",
    "SBI_R31_11_4_RUNTIME_ENABLED": "private-firebase-rls-auth-acceptance-v1",
}
PATH = "/api/r31-private-qa/tenant-rls-source-r3114?limit=3"
USERS = {
    "synthetic-ci-a": SimpleNamespace(
        uid="synthetic-ci-a", disabled=False, email_verified=True,
        custom_claims={"dil_dashboard": True, "dil_admin": False}),
    "synthetic-ci-b": SimpleNamespace(
        uid="synthetic-ci-b", disabled=False, email_verified=True,
        custom_claims={"dil_dashboard": True, "dil_admin": False}),
}


class SessionContract(unittest.TestCase):
    def setUp(self):
        self.app = Flask("r3114e-contract")
        sessions.install_sessions(self.app)
        self.app.register_blueprint(route.runtime_tenant_rls)
        self.app.testing = True

    def request(self, cookie=None, *, uid_override=None, fake_claims=None,
                disabled=False, flags=None, method="GET"):
        verified=[]
        looked_up=[]
        database=[]
        def verify(value, **kw):
            verified.append((value,kw.get("check_revoked")))
            if value not in {"cookie-ci-a","cookie-ci-b"}:
                raise sessions.auth.InvalidSessionCookieError("bad synthetic cookie")
            return {"uid": "synthetic-ci-a" if value=="cookie-ci-a" else "synthetic-ci-b"}
        def get_user(uid, **kw):
            looked_up.append(uid)
            source=USERS[uid]
            return SimpleNamespace(
                uid=uid_override or source.uid, disabled=disabled,
                email_verified=True,
                custom_claims=(source.custom_claims if fake_claims is None else fake_claims))
        def db_read(user, limit=20):
            database.append((user.uid,limit))
            return [{"source_row_number":4,"raw_sol":"000001",
                     "source_status":"NOT_CALCULATED","credit_paise":123}]
        with (patch.dict(os.environ, FLAGS if flags is None else flags,clear=False),
              patch.object(sessions,"firebase_app",return_value=object()),
              patch.object(sessions.auth,"verify_session_cookie",side_effect=verify),
              patch.object(sessions.auth,"get_user",side_effect=get_user),
              patch.object(route,"read_tenant_source_only",side_effect=db_read)):
            with self.app.test_client() as c:
                if cookie is not None:
                    c.set_cookie(sessions.SESSION_COOKIE,cookie,secure=True)
                response=c.open(PATH + "&owner_uid=synthetic-ci-b",
                                method=method,
                                headers={"X-Owner-Uid":"synthetic-ci-b",
                                         "X-Pg-Role":"r3113_login_b"},
                                base_url="https://localhost")
        return response,verified,looked_up,database

    def test_real_session_middleware_source_selects_exact_two_distinct_owners(self):
        for cookie,expected in (("cookie-ci-a","synthetic-ci-a"),
                                ("cookie-ci-b","synthetic-ci-b")):
            response,verified,looked_up,database=self.request(cookie)
            self.assertEqual(response.status_code,200)
            self.assertEqual(verified,[(cookie,True)])
            self.assertEqual(looked_up,[expected])
            self.assertEqual(database,[(expected,3)])
            self.assertEqual(response.json["reconciliation_status"],"NOT_CALCULATED")
            self.assertFalse(response.json["financial_execution_enabled"])
            self.assertFalse(response.json["production_financial_writes"])
            self.assertFalse(response.json["invoice_generation_enabled"])

    def test_anonymous_and_invalid_cookies_rejected_without_database_access(self):
        for cookie in (None,"invalid"):
            response,_,_,database=self.request(cookie)
            self.assertEqual(response.status_code,401)
            self.assertEqual(database,[])

    def test_disabled_and_removed_claims_fail_before_database_access(self):
        for kwargs,code in (({"disabled":True},403),
                            ({"fake_claims":{"dil_dashboard":False}},403)):
            response,verified,looked_up,database=self.request("cookie-ci-b",**kwargs)
            self.assertEqual(response.status_code,code)
            self.assertEqual(len(verified),1)
            self.assertEqual(len(looked_up),1)
            self.assertEqual(database,[])

    def test_runtime_feature_disabled(self):
        flags=dict(FLAGS)
        flags["SBI_R31_11_4_RUNTIME_ENABLED"]="OFF"
        response,verified,looked_up,database=self.request("cookie-ci-a",flags=flags)
        self.assertEqual(response.status_code,503)
        self.assertEqual(len(verified),1)
        self.assertEqual(len(looked_up),1)
        self.assertEqual(database,[])

    def test_post_disallowed_and_no_financial_route(self):
        response,_,_,database=self.request("cookie-ci-a",method="POST")
        self.assertIn(response.status_code,(403,405))
        self.assertEqual(database,[])


if __name__ == "__main__":
    unittest.main()
