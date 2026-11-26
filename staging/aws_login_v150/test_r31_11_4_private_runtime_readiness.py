"""DB-R31.11.4 focused, offline private provisioning readiness tests.

No Docker, AWS, Firebase credentials or database is accessed here.
"""
from __future__ import annotations
import ast
import contextlib
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

import r31_11_4_private_runtime_readiness as gate

SOURCE=(Path(__file__).resolve().parent/
        "r31_11_4_private_runtime_readiness.py").read_text("utf-8")


class PrivateReadinessTests(unittest.TestCase):
    def test_syntax_and_command_allowlist(self):
        ast.parse(SOURCE)
        for disallowed in (
            '"createdb"', '"dropdb"', '"pg_dump"', '"pg_restore"',
            '"ALTER ROLE"', '"CREATE ROLE"', '"DROP ROLE"',
            '"INSERT INTO"', '"UPDATE sbi."', '"DELETE FROM"',
            '"docker","run"', '"docker","build"', '"docker","network","connect"',
            '"caddy","reload"', "set_custom_user_claims", "auth.create_user",
            "password=",
        ):
            self.assertNotIn(disallowed, SOURCE)
        self.assertIn("FINANCIAL_APPLY=LOCKED", SOURCE)
        self.assertIn("R3112_FINANCIAL_INTEGRATION=QUARANTINED", SOURCE)

    def test_separate_candidate_topology_required(self):
        good_info={
            "Config":{"Image":"postgres:16"},
            "State":{"Running":True},
            "HostConfig":{"Privileged":False,"PortBindings":{}},
            "NetworkSettings":{"Networks":{gate.NEW_NET:{}}},
            "Mounts":[{"Destination":"/var/lib/postgresql/data"}],
        }
        good_net={"Internal":True,"Attachable":False}
        self.assertTrue(gate._candidate_isolated(good_info,good_net))
        cases=[
            lambda i,n:i["HostConfig"].update(Privileged=True),
            lambda i,n:i["HostConfig"].update(PortBindings={"5432/tcp":[{"HostPort":"5432"}]}),
            lambda i,n:i["NetworkSettings"].update(Networks={"bridge":{}}),
            lambda i,n:n.update(Internal=False),
            lambda i,n:n.update(Attachable=True),
            lambda i,n:i["Mounts"].append({"Destination":"/var/run/docker.sock"}),
        ]
        import copy
        for update in cases:
            with self.subTest(update=str(update)):
                i,n=copy.deepcopy(good_info),copy.deepcopy(good_net)
                update(i,n)
                self.assertFalse(gate._candidate_isolated(i,n))

    def test_missing_candidate_never_creates_one(self):
        with (patch.object(gate,"preflight") as preflight,
              patch.object(gate,"_public_route_absent",return_value=True),
              patch.object(gate,"_inspect",return_value=None) as inspection,
              patch.object(gate,"_safe_catalog_state") as catalog,
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertFalse(gate.audit())
        preflight.assert_called_once()
        inspection.assert_called_once_with(gate.NEW_PG,allow_absent=True)
        catalog.assert_not_called()
        self.assertIn("SEPARATE_AUTH_POSTGRES=NOT_PROVISIONED",output.getvalue())

    def test_roles_fail_closed(self):
        complete={
            "login_roles":2,"membership_pairs":2,"all_memberships":2,
            "group_roles":2,"distinct_owner_mappings":2,
            "raw_mapping_readers":0,
            "forced_rls":4,"invoker_view":1,"writer_grants":0,
        }
        self.assertTrue(gate._restricted_roles_complete(complete))
        for k,v in complete.items():
            bad=dict(complete);bad[k]=v+1
            self.assertFalse(gate._restricted_roles_complete(bad))
        with self.assertRaises(KeyError):
            gate._restricted_roles_complete({"login_roles":2})

    def test_no_candidate_database_and_forbidden_db(self):
        info={"some":"metadata"}
        with (patch.object(gate,"preflight"),
              patch.object(gate,"_public_route_absent",return_value=True),
              patch.object(gate,"_inspect",return_value=info),
              patch.object(gate,"_docker",return_value='[{"Internal":true,"Attachable":false}]'),
              patch.object(gate,"_candidate_isolated",return_value=True),
              patch.object(gate,"_restricted_role_state") as roles,
              patch.object(gate,"_safe_catalog_state",
                           return_value={"new_db":0,"forbidden_dbs":0}),
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertFalse(gate.audit())
            roles.assert_not_called()
        self.assertIn("AUTH_DATABASE=NOT_PROVISIONED",output.getvalue())

        with (patch.object(gate,"preflight"),
              patch.object(gate,"_public_route_absent",return_value=True),
              patch.object(gate,"_inspect",return_value=info),
              patch.object(gate,"_docker",return_value='[{"Internal":true,"Attachable":false}]'),
              patch.object(gate,"_candidate_isolated",return_value=True),
              patch.object(gate,"_safe_catalog_state",
                           return_value={"new_db":1,"forbidden_dbs":1}),
              contextlib.redirect_stdout(StringIO())):
            with self.assertRaises(gate.AuditBlocked):
                gate.audit()

    def test_existing_clone_not_targeted_and_final_release_stays_blocked(self):
        self.assertNotEqual(gate.NEW_PG,gate.PG)
        self.assertNotEqual(gate.NEW_DB,gate.PREVIOUS_DB)
        with (patch.object(gate,"audit",return_value=False),
              contextlib.redirect_stdout(StringIO()) as output):
            code=gate.main()
        self.assertEqual(code,2)
        s=output.getvalue()
        self.assertIn("FIREBASE_TWO_USERS=PENDING_SECOND_APPROVED_ACCOUNT",s)
        self.assertIn("FIREBASE_TO_DB_ACCEPTANCE=NOT_EXECUTED",s)
        self.assertIn("EXTERNAL_MTLS_HTTPS=NOT_APPROVED",s)
        self.assertIn("PRODUCTION_WRITES=NONE_BY_AUDIT",s)
        self.assertIn("RELEASE=PRODUCTION_BLOCKED",s)

    def test_caddy_guard_rejects_unapproved_qa_service(self):
        with patch.object(gate,"_docker",return_value=
                          "reverse_proxy sbi-r3114-private-api:8080"):
            with self.assertRaises(gate.AuditBlocked):
                gate._public_route_absent()
        with patch.object(gate,"_docker",return_value=
                          "example.invalid { respond 404 }"):
            self.assertTrue(gate._public_route_absent())


if __name__=="__main__":
    unittest.main()
