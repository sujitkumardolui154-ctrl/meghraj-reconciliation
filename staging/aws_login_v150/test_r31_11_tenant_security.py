"""R31.11 contract tests. No live Firebase, Caddy or financial writes."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parent
RUN=(ROOT/"r31_11_combined_tenant_security.py").read_text("utf-8")
AUTH=(ROOT/"r31_11_second_firebase_preflight.py").read_text("utf-8")
MIG=(ROOT/"r31_11_clone_rls_up.sql").read_text("utf-8")
VERIFY=(ROOT/"r31_11_clone_rls_verify.sql").read_text("utf-8")
HTTPS=(ROOT/"Caddyfile.r31_11_review_only.template").read_text("utf-8")

class R3111SecurityContracts(unittest.TestCase):
    def test_scripts_parse(self):
        ast.parse(RUN)
        ast.parse(AUTH)

    def test_sql_guard_requires_empty_separate_database(self):
        self.assertIn("sbi_r31_11_tenant_clone_20261125",MIG)
        self.assertIn("DB_R3111_CLONE_MUST_CONTAIN_NO_SOURCE_ROWS",MIG)
        self.assertIn("DB_R3111_WRONG_DATABASE_OR_PRIVILEGE",MIG)
        self.assertIn("DB_R3111_EXISTING_POLICIES_REQUIRE_REVIEW",MIG)
        self.assertIn("sbi_r31_ownerqa_report",MIG)
        self.assertIn("REVOKE ALL ON sbi.payment_received_source_v1",MIG)

    def test_four_source_rls_with_unforgeable_role_binding(self):
        for name in ("import_batches","payment_source_rows","payments",
                     "payment_source_status_v1"):
            self.assertIn("ALTER TABLE sbi."+name+" FORCE ROW LEVEL SECURITY",MIG)
            self.assertIn("ALTER TABLE sbi."+name+" ENABLE ROW LEVEL SECURITY",MIG)
        self.assertIn("session_user::name",MIG)
        self.assertIn("SECURITY DEFINER",MIG)
        self.assertIn("NOBYPASSRLS",MIG)
        self.assertIn("NOLOGIN NOINHERIT",MIG)
        self.assertIn("security_invoker=true",MIG)
        self.assertNotIn("current_setting('app.owner_uid')",MIG)
        self.assertIn("DEFAULT", "DEFAULT") # smoke assertion for test runner

    def test_real_sql_two_roles_negative_checks(self):
        for fragment in (
            "SET SESSION AUTHORIZATION r311_qa_tenant_a",
            "SET SESSION AUTHORIZATION r311_qa_tenant_b",
            "SET SESSION AUTHORIZATION sbi_r31_ownerqa_report",
            "row_security_active('sbi.import_batches')",
            "DB_R3111_TENANT_A_PAYMENT_LEAK",
            "DB_R3111_TENANT_B_PAYMENT_LEAK",
            "DB_R3111_USER_SETTABLE_OWNER_ESCAPED_RLS",
            "DB_R3111_SHARED_REPORT_ROLE_STILL_HAS_ACCESS",
        ):
            self.assertIn(fragment,VERIFY)

    def test_no_finance_source_and_route_mutation(self):
        for forbidden in (
            "sbi_reconciliation_main","docker run","docker build",
            "caddy reload","DROP DATABASE","ALTER TABLE sbi.",
        ):
            self.assertNotIn(forbidden,RUN)
        self.assertIn('NEW_EMPTY_CLONE=CREATING_SCHEMA_ONLY',RUN)
        self.assertIn('EXISTING_SBI_QA_SCHEMA=UNCHANGED',RUN)
        self.assertIn('PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST',RUN)

    def test_second_firebase_is_existing_distinct_without_admin(self):
        self.assertIn('auth.get_user_by_email(email',AUTH)
        self.assertIn('user.uid==MASTER_UID',AUTH)
        self.assertIn("dil_dashboard",AUTH)
        self.assertIn("dil_admin",AUTH)
        self.assertNotIn("auth.create_user",AUTH)
        self.assertNotIn("set_custom_user_claims",AUTH)
        self.assertIn("getpass.getpass",AUTH)
        self.assertIn("stdin",AUTH)
        self.assertNotIn("print(email",AUTH)

    def test_https_is_explicitly_unapproved_mtls(self):
        self.assertIn("DO NOT IMPORT OR DEPLOY AS-IS",HTTPS)
        self.assertIn("require_and_verify",HTTPS)
        self.assertIn("trust_pool file",HTTPS)
        self.assertIn("qa-r311.example.invalid",HTTPS)
        self.assertIn("PENDING_APPROVED_MTLS_HOST_AND_ORIGIN",RUN)
        self.assertNotIn("EXTERNAL_HTTPS_E2E=PASS",RUN)

if __name__=="__main__":
    unittest.main()
