"""DB-R31.11.4 Firebase-session acceptance contract — MOCK ONLY.

Exercises the real Flask install_sessions middleware + R31.11.3 blueprint with
synthetic users. No Firebase cloud, AWS server, payments or DB writes.
Passing tests do NOT constitute real two-account Firebase acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dashboard_source"))

from flask import Flask
import dashboard_sessions as sessions
import r31_11_3_runtime_rls_blueprint as stage

FLAG_ENV={
    "SBI_R31_PRIVATE_STAGING_ENABLED":"isolated-ownerqa-firebase-csrf-v1",
    "SBI_R31_11_3_RUNTIME_ENABLED":"private-firebase-rls-readonly-v1",
}

class SessionAcceptanceContracts(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        sessions.install_sessions(self.app)
        self.app.register_blueprint(stage.runtime_tenant_rls)
        self.app.testing=True

    def _run(self, account=None, claims=None, supplied=None):
        users={
            "qa-synthetic-a":SimpleNamespace(
                uid="qa-synthetic-a",email="a@example.invalid",
                disabled=False,custom_claims={"dil_dashboard":True}),
            "qa-synthetic-b":SimpleNamespace(
                uid="qa-synthetic-b",email="b@example.invalid",
                disabled=False,custom_claims={"dil_dashboard":True}),
        }
        if claims is not None and account in users:
            users[account].custom_claims=claims
        invocations=[]
        def strict_read(user,limit=20):
            invocations.append((user.uid,limit))
            return [{
                "source_row_number":2,
                "raw_sol":"001505" if user.uid=="qa-synthetic-a" else "001506",
                "source_status":"PENDING_RECONCILIATION",
                "credit_paise":11800 if user.uid=="qa-synthetic-a" else 35700,
            }]
        def verify_cookie(cookie,**_):
            if cookie not in {"cookie-for-a","cookie-for-b"}:
                raise sessions.auth.InvalidSessionCookieError("invalid")
            return {"uid":"qa-synthetic-a" if cookie=="cookie-for-a"
                    else "qa-synthetic-b"}
        with (patch.dict(os.environ,FLAG_ENV),
              patch.object(sessions,"firebase_app",return_value=object()),
              patch.object(sessions.auth,"verify_session_cookie",
                           side_effect=verify_cookie),
              patch.object(sessions.auth,"get_user",
                           side_effect=lambda uid,**_:users[uid]),
              patch.object(stage,"read_tenant_source_only",side_effect=strict_read)):
            with self.app.test_client() as client:
                if account:
                    client.set_cookie(sessions.SESSION_COOKIE,
                        "cookie-for-a" if account=="qa-synthetic-a"
                        else "cookie-for-b", secure=True)
                response=client.get(
                    "/api/r31-private-qa/tenant-rls-source?limit=9"
                    + ("&owner_uid="+supplied if supplied else ""),
                    headers={"X-Owner-Uid":supplied or "fake-foreign-owner"},
                    base_url="https://localhost",
                )
        return response,invocations

    def test_two_distinct_session_objects_bind_to_separate_owner_contexts(self):
        a,called_a=self._run("qa-synthetic-a",supplied="qa-synthetic-b")
        b,called_b=self._run("qa-synthetic-b",supplied="qa-synthetic-a")
        self.assertEqual(a.status_code,200)
        self.assertEqual(b.status_code,200)
        self.assertEqual(called_a,[("qa-synthetic-a",9)])
        self.assertEqual(called_b,[("qa-synthetic-b",9)])
        self.assertNotEqual(a.json["rows"][0]["credit_paise"],
                            b.json["rows"][0]["credit_paise"])
        self.assertFalse(a.json["production_financial_writes"])
        self.assertEqual(a.json["reconciliation_status"],"NOT_CALCULATED")

    def test_no_cookie_denied_by_middleware_before_adapter(self):
        response,called=self._run()
        self.assertEqual(response.status_code,401)
        self.assertEqual(called,[])

    def test_unauthorized_claim_denied_before_adapter(self):
        response,called=self._run("qa-synthetic-b",
                                  claims={"dil_dashboard":False})
        self.assertEqual(response.status_code,403)
        self.assertEqual(called,[])

    def test_get_only_and_feature_disabled(self):
        with patch.dict(os.environ,FLAG_ENV):
            rules=[r for r in self.app.url_map.iter_rules()
                   if r.rule=="/api/r31-private-qa/tenant-rls-source"]
            self.assertEqual(len(rules),1)
            self.assertNotIn("POST",rules[0].methods)
            self.assertNotIn("PUT",rules[0].methods)
            self.assertNotIn("DELETE",rules[0].methods)

        with (patch.dict(os.environ,{
                "SBI_R31_PRIVATE_STAGING_ENABLED":"isolated-ownerqa-firebase-csrf-v1",
                "SBI_R31_11_3_RUNTIME_ENABLED":"OFF",
              }),
              patch.object(sessions,"firebase_app",return_value=object()),
              patch.object(sessions.auth,"verify_session_cookie",
                  return_value={"uid":"qa-synthetic-a"}),
              patch.object(sessions.auth,"get_user",
                  return_value=SimpleNamespace(
                      uid="qa-synthetic-a",disabled=False,
                      custom_claims={"dil_dashboard":True})),
              patch.object(stage,"read_tenant_source_only") as read):
            with self.app.test_client() as client:
                client.set_cookie(sessions.SESSION_COOKIE,
                                  "cookie-for-a",secure=True)
                result=client.get(
                    "/api/r31-private-qa/tenant-rls-source",
                    base_url="https://localhost")
            self.assertEqual(result.status_code,503)
            read.assert_not_called()


if __name__=="__main__":
    unittest.main()
