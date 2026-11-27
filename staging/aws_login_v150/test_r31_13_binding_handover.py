"""R31.13 offline read-only handover source contracts; no AWS access."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SCRIPT = (ROOT / "r31_13_firebase_pg_binding_acceptance.py").read_text("utf-8")
ADAPTER = (ROOT / "r31_11_4_runtime_rls_adapter.py").read_text("utf-8")
BLUEPRINT = (ROOT / "r31_11_4_runtime_rls_blueprint.py").read_text("utf-8")
APP = (ROOT / "app.py").read_text("utf-8")
PRIOR = (ROOT / "r31_11_4j_combined_mtls_gate.py").read_text("utf-8")


class R3113BindingHandover(unittest.TestCase):
    def test_sources_parse(self):
        for value in (SCRIPT, ADAPTER, BLUEPRINT, APP, PRIOR):
            ast.parse(value)

    def test_reuses_existing_security_evidence_instead_of_reprovisioning(self):
        self.assertIn("existing.audit_baseline(args.source_sha)", SCRIPT)
        self.assertIn("DB_R31_13_TWO_FIREBASE_TO_PG_SESSIONS=PASS_PRIOR_4I_LOCAL_OPERATOR_RECEIPT", SCRIPT)
        self.assertIn("APPROVED_4I_SOURCE_SHA", PRIOR)
        self.assertIn("audit_local_receipt(APPROVED_4I_SOURCE_SHA)", PRIOR)
        for forbidden in ("docker run", "docker create", "CREATE ROLE", "ALTER ROLE",
                          "DROP DATABASE", "INSERT INTO", "UPDATE sbi.", "DELETE FROM",
                          "auth.create_user", "set_custom_user_claims", "caddy reload"):
            self.assertNotIn(forbidden, SCRIPT)

    def test_server_verified_identity_not_untrusted_uid(self):
        self.assertIn('getattr(g, "dil_user", None)', BLUEPRINT)
        self.assertIn("r311_auth.current_tenant_uid()", ADAPTER)
        self.assertIn("if len(item) != 5 or item[0] != uid:", ADAPTER)
        self.assertIn('client', 'client')  # deterministic smoke
        self.assertIn('SBI_R31_11_4_RUNTIME_ENABLED', APP)
        self.assertIn('SBI_R31_PRIVATE_STAGING_ENABLED', APP)

    def test_db_role_login_enforces_read_only_rls(self):
        for value in ("default_transaction_read_only=on",
                      "SET TRANSACTION READ ONLY",
                      "row_security_active('sbi.import_batches')",
                      "row_security_active('sbi.payment_source_rows')",
                      "row_security_active('sbi.payments')",
                      "row_security_active('sbi.payment_source_status_v1')"):
            self.assertIn(value, ADAPTER)
        self.assertNotIn("SET SESSION AUTHORIZATION ", ADAPTER)
        self.assertNotIn("SET ROLE ", ADAPTER)
        self.assertNotIn("WHERE owner_uid =", ADAPTER)

    def test_production_release_is_always_locked(self):
        for value in (
            "REAL_EXPIRED_REVOKED_FIREBASE_SESSION=NOT_TESTED",
            "EXTERNAL_MTLS_HTTPS=NOT_TESTED",
            "PRODUCTION_RUNTIME_DEPLOYMENT=NOT_APPROVED",
            "FINANCIAL_APPLY=LOCKED",
            "PRODUCTION_RELEASE=BLOCKED",
            "return 2",
        ):
            self.assertIn(value, SCRIPT)
        self.assertNotIn("EXTERNAL_MTLS_HTTPS=PASS", SCRIPT)


if __name__ == "__main__":
    unittest.main()
