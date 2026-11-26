"""DB-R31.11.4B: narrow offline non-destructive migration gate tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

import r31_11_4b_schema_only_runner as target
import r31_11_4_private_runtime_readiness as readiness


def state(empty=False):
    if empty:
        return {
            "db":target.DB,"schema_count":0,"source_tables":0,
            "forced_rls":0,"policies":0,"groups":0,"logins":0,
            "map_table_exists":False,"invoker_view":False,"user_data":0,
        }
    return {
        "db":target.DB,"schema_count":2,"source_tables":4,
        "forced_rls":4,"policies":4,"groups":2,"logins":0,
        "map_table_exists":True,"invoker_view":True,"user_data":0,
    }


class SchemaOnlySafety(TestCase):
    def test_preconditions_reject_any_existing_structure(self):
        self.assertTrue(target._is_empty(state(True)))
        self.assertTrue(target._is_schema_only(state()))
        for key in ("schema_count","source_tables","forced_rls","policies",
                    "groups","logins","user_data"):
            with self.subTest(field=key):
                changed=state(True);changed[key]=1
                self.assertFalse(target._is_empty(changed))
        for key in ("source_tables","forced_rls","policies","groups",
                    "logins","user_data"):
            with self.subTest(field=key):
                changed=state();changed[key]+=1
                self.assertFalse(target._is_schema_only(changed))
        changed=state();changed["map_table_exists"]=False
        self.assertFalse(target._is_schema_only(changed))

    def test_readonly_default_never_connects_for_writes(self):
        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",return_value=state(True)),
              patch.object(target,"_sql_source",return_value=("SQL","abc123")),
              patch.object(target,"_psql") as psql,
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main([]),0)
            psql.assert_not_called()
        self.assertIn("MODE=READONLY_PLAN_ONLY_NO_CHANGES",output.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",output.getvalue())

    def test_already_present_prevents_apply_even_with_approval(self):
        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",return_value=state()),
              patch.object(target,"_sql_source") as source,
              patch.object(target,"_psql") as psql,
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main([
                "--apply","--approve",target.APPROVE]),2)
            source.assert_not_called()
            psql.assert_not_called()
        self.assertIn("DATABASE_ALREADY_POPULATED_OR_MIGRATED=REVIEW_ONLY",
                      output.getvalue())

    def test_unapproved_apply_refuses_before_sql(self):
        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",return_value=state(True)),
              patch.object(target,"_sql_source",return_value=("SQL","abc123")),
              patch.object(target,"_psql") as psql,
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main(["--apply"]),2)
            psql.assert_not_called()
        self.assertIn("STOP=DB_R31_11_4B_GUARDED_SCHEMA",output.getvalue())

    def test_success_requires_sql_receipt_exact_shape_and_zero_data(self):
        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",side_effect=[state(True),state()]),
              patch.object(target,"_sql_source",return_value=("SQL","digest")),
              patch.object(target,"_psql",return_value=
                           "DB_R31_11_4B_SCHEMA_RLS_BOOTSTRAP=PASS_NO_REAL_USERS") as psql,
              patch.object(target,"_all_new_source_tables_empty",return_value=True),
              patch.object(target.infra,"caddy_fingerprint",return_value="caddysha"),
              patch.object(target.infra,"preflight"),
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main(["--apply","--approve",target.APPROVE]),0)
            psql.assert_called_once_with("SQL")
        self.assertIn("SCHEMA_ONLY=PASS_PRIVATE_QA",output.getvalue())
        self.assertIn("LOGIN_ROLES=NONE_PROVISIONED",output.getvalue())
        self.assertIn("PRODUCTION_BLOCKED",output.getvalue())

    def test_wrong_ack_or_nonempty_data_fails_closed(self):
        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",side_effect=[state(True),state()]),
              patch.object(target,"_sql_source",return_value=("SQL","digest")),
              patch.object(target,"_psql",return_value="WRONG_ACK"),
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main(["--apply","--approve",target.APPROVE]),2)
        self.assertIn("STOP=",output.getvalue())

        with (patch.object(target,"_guarded_preflight",return_value="caddysha"),
              patch.object(target,"_state",side_effect=[state(True),state()]),
              patch.object(target,"_sql_source",return_value=("SQL","digest")),
              patch.object(target,"_psql",return_value=
                           "DB_R31_11_4B_SCHEMA_RLS_BOOTSTRAP=PASS_NO_REAL_USERS"),
              patch.object(target,"_all_new_source_tables_empty",return_value=False),
              redirect_stdout(StringIO()) as output):
            self.assertEqual(target.main(["--apply","--approve",target.APPROVE]),2)
        self.assertIn("STOP=",output.getvalue())

    def test_readiness_distinguishes_expected_empty_owner_login_phase(self):
        role_state={
            "login_roles":0, "membership_pairs":0,
            "all_memberships":0,"group_roles":2,
            "distinct_owner_mappings":0,"raw_mapping_readers":0,
            "forced_rls":4,"invoker_view":1,"writer_grants":0,
        }
        self.assertTrue(readiness._schema_only_login_pending(role_state))
        self.assertFalse(readiness._restricted_roles_complete(role_state))
        unsafe=dict(role_state);unsafe["writer_grants"]=1
        self.assertFalse(readiness._schema_only_login_pending(unsafe))

    def test_no_login_password_user_insertion_or_financial_apis_in_sql(self):
        sql,_=target._sql_source()
        self.assertNotIn("CREATE ROLE r3113_login_a",sql)
        self.assertNotIn("CREATE ROLE r3113_login_b",sql)
        self.assertNotIn("INSERT INTO r311_auth.role_owner_map",sql)
        self.assertNotIn("GRANT INSERT",sql)
        self.assertNotIn("GRANT UPDATE",sql)
        self.assertNotIn("GRANT DELETE",sql)
        self.assertNotIn("sbi_reconciliation_main",sql)
        self.assertNotIn("sbi_r31_11_tenant_clone_20261125",sql)
        self.assertIn("FORCE ROW LEVEL SECURITY",sql)
        self.assertIn("security_invoker=true",sql)
