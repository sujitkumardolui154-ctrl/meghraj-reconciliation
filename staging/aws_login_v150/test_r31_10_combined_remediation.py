"""Offline R31.10 no-secret, fail-closed combined remediation contracts."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parent
RUN = (ROOT/"r31_10_combined_remediation.py").read_text("utf-8")
SQL = (ROOT/"r31_10_shadow_rls.sql").read_text("utf-8")
R319 = (ROOT/"r31_9_combined_incontainer.py").read_text("utf-8")


class CombinedR310SafetyTests(unittest.TestCase):
    def test_runner_syntax_and_combined_calls(self):
        tree = ast.parse(RUN)
        self.assertIsNotNone(tree)
        for call in ("preflight()", "shadow_qa()", "real_two_owner_qa()",
                     "external_https_gate()"):
            self.assertIn(call, RUN)

    def test_private_pinned_pg_db(self):
        self.assertIn('sbi_r31_owner_qa_20261125',RUN)
        self.assertIn('sbi-synthetic-postgres-38-31',RUN)
        self.assertIn('sudo", "-n", "docker", "exec", "-i"',RUN)
        self.assertIn("ON_ERROR_STOP=1",RUN)
        self.assertNotIn("sbi_reconciliation_main",RUN)

    def test_transaction_shadow_rollback_and_role_unforgeability(self):
        self.assertIn("BEGIN;",SQL)
        self.assertIn("ROLLBACK;",SQL)
        self.assertIn("current_database() <> 'sbi_r31_owner_qa_20261125'",SQL)
        self.assertIn("FORCE ROW LEVEL SECURITY",SQL)
        self.assertIn("security_invoker = true",SQL)
        self.assertIn("owner_role = current_user",SQL)
        self.assertIn("SET ROLE r31_10_tenant_a;",SQL)
        self.assertIn("SET ROLE r31_10_tenant_b;",SQL)
        self.assertIn("WHEN insufficient_privilege",SQL)
        self.assertIn("FOREIGN KEY (batch_id, owner_role)",SQL)
        self.assertIn("FOREIGN KEY (source_row_id, owner_role)",SQL)
        self.assertIn("SHADOW_ROLLBACK_INCOMPLETE",SQL)
        self.assertNotIn("ALTER TABLE sbi.",SQL)
        self.assertNotIn("INSERT INTO sbi.",SQL)

    def test_mandatory_original_rls_not_overclaimed(self):
        self.assertIn("EXISTING_SBI_RLS=MIGRATION_NOT_APPLIED",RUN)
        self.assertIn("STAGING_REMEDIATION_INCOMPLETE_PRODUCTION_BLOCKED",RUN)
        self.assertNotIn("PRODUCTION_READY",RUN)

    def test_distinct_firebase_users_required(self):
        self.assertIn("tokens.append(signin(key))",RUN)
        self.assertIn("PASS_DISTINCT_AUTHENTICATED_UIDS",RUN)
        self.assertIn("PASS_BIDIRECTIONAL_404_AND_FILTERING",RUN)
        self.assertIn("NOT_TESTED_SECOND_USER_NOT_READY",RUN)
        self.assertIn("if a[2] == b[2]:",R319)

    def test_https_not_declared_success_without_approved_route(self):
        self.assertIn("BLOCKED_PENDING_APPROVED_MTLS_ROUTE",RUN)
        self.assertIn("UNAPPROVED_CADDY_QA_ROUTE_PRESENT",RUN)
        self.assertNotIn('EXTERNAL_HTTPS_E2E=PASS',RUN)

    def test_no_cloud_identity_or_network_mutations(self):
        for disallowed in (
            "auth.create_user(", "set_custom_user_claims(", "docker network connect",
            "docker run", "docker build", "ALTER ROLE", "CREATE USER",
            "caddy reload", "curl -k", "verify=False"
        ):
            self.assertNotIn(disallowed,RUN)
        self.assertIn("PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST",RUN)


if __name__ == "__main__":
    unittest.main()
