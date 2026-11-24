"""DB-R31 staging-only Flask PostgreSQL reporting overlay contract QA."""
from contextlib import contextmanager
from dataclasses import dataclass
import csv
import io
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, Blueprint, g
sys.path.insert(0,str(Path(__file__).parent))
import db_r31_pg_report_private_wsgi as overlay

STAGE_ENV={
    "SBI_R31_PG_REPORT_STAGING_ENABLED":"true",
    "SBI_FINANCIAL_APPLY":"LOCKED",
    "PGDATABASE":"sbi_ft04g_clean_0e858f93",
    "PGUSER":"sbi_ft04q_report",
    "SBI_R31_REPORT_DSN":"SYNTHETIC_ONLY_FAKE_CONNECTION_NOT_REAL",
}


class FakeConnection:
    def close(self):pass


def pretend_app(*,allow=False,viewer=True,identity_uid="synthetic-owner"):
    app=Flask(__name__)
    report=Blueprint("sbi_payment_received_reports",__name__)
    @report.get("/api/payment-received/sol-report")
    def sol_payment_report():
        return {"source":"UNSAFE_OLD_SQLITE"}
    @report.get("/api/payment-received/sol-report.csv")
    def export_sol_payment_csv():
        return {"source":"UNSAFE_OLD_SQLITE"}
    @report.get("/api/payment-received/payment-details.csv")
    def export_payment_details_csv():
        return {"source":"UNSAFE_OLD_SQLITE"}
    app.register_blueprint(report)
    @app.before_request
    def simulated_verified_firebase_session():
        # This intentionally tests overlay consumer side. It does NOT prove
        # real Firebase cookie/CSRF validation; actual app install_sessions
        # must be verified in a separate AWS private owner staging UAT.
        if allow:
            g.dil_user=SimpleNamespace(
                uid="synthetic-owner",disabled=False,
                custom_claims={"dil_dashboard":True,
                               "sbi_report_viewer":viewer},
                email="qa@example.invalid")
            g.dil_identity={"uid":identity_uid}
    app.testing=True
    return app


def example_summary():
    return {
        "records":[
            {"sol_id":"1505","branch_name":"SYNTHETIC APPROVED BRANCH",
             "payment_rows":3,"credit_paise":13000,"excluded":1,
             "not_calculated":2,"held_for_review":1,
             "available_for_future_matching":1,"matched":None},
            {"sol_id":"99922","branch_name":"PENDING_SOL_MASTER_REVIEW",
             "payment_rows":1,"credit_paise":2000,"excluded":0,
             "not_calculated":1,"held_for_review":1,
             "available_for_future_matching":0,"matched":None},
        ],
        "page_totals":{"payment_rows":4,"credit_paise":15000,
                       "not_calculated":3,"excluded":1,
                       "held_for_review":2,"matched":None},
        "limit":100,"offset":0,
    }


class R31PrivateFlaskReportTests(unittest.TestCase):
    def setUp(self):
        self.environment=patch.dict(os.environ,STAGE_ENV)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _mock_report(self,*,allow=True,viewer=True,uid="synthetic-owner"):
        app=pretend_app(allow=allow,viewer=viewer,identity_uid=uid)
        endpoints=overlay.attach_private_stage_report(app)
        self.assertEqual(len(endpoints),3)
        return app

    def test_01_refuse_live_central_database_target(self):
        with patch.dict(os.environ,{"PGDATABASE":"sbi_reconciliation_main"}):
            with self.assertRaisesRegex(overlay.PrivateStageRefusal,
                                        "QA_REPORT_STAGE_NOT_CONFIGURED"):
                overlay.attach_private_stage_report(pretend_app())

    def test_02_refuse_live_financial_apply(self):
        with patch.dict(os.environ,{"SBI_FINANCIAL_APPLY":"ENABLED"}):
            with self.assertRaises(overlay.PrivateStageRefusal):
                overlay.attach_private_stage_report(pretend_app())

    def test_03_replacing_existing_routes_only(self):
        app=self._mock_report()
        paths={r.rule for r in app.url_map.iter_rules()}
        self.assertEqual(len(paths),4)  # 3 report routes + static
        self.assertFalse(any("new-public" in p for p in paths))

    def test_04_double_registration_denied(self):
        app=self._mock_report()
        with self.assertRaisesRegex(overlay.PrivateStageRefusal,
                                    "QA_REPORT_STAGE_ALREADY_INSTALLED"):
            overlay.attach_private_stage_report(app)

    def test_05_refuse_app_missing_exact_legacy_routes(self):
        with self.assertRaises(overlay.PrivateStageRefusal):
            overlay.attach_private_stage_report(Flask(__name__))

    def test_06_without_firebase_identity_forbidden(self):
        app=self._mock_report(allow=False)
        c=app.test_client()
        self.assertEqual(c.get("/api/payment-received/sol-report").status_code,403)

    def test_07_dashboard_only_not_a_bank_report_permission(self):
        app=self._mock_report(viewer=False)
        self.assertEqual(app.test_client().get(
            "/api/payment-received/sol-report").status_code,403)

    def test_08_uid_conflict_denies_report(self):
        app=self._mock_report(uid="other-user")
        self.assertEqual(app.test_client().get(
            "/api/payment-received/sol-report").status_code,403)

    def test_09_correct_identity_maps_summary_without_sqlite(self):
        app=self._mock_report()
        with patch.object(overlay,"_pg",return_value=FakeConnection()),\
             patch.object(overlay,"sol_summary",return_value=example_summary()) as query:
            c=app.test_client()
            r=c.get("/api/payment-received/sol-report")
            self.assertEqual(r.status_code,200,r.get_data(as_text=True))
            self.assertEqual(r.json["source"],"CENTRAL_POSTGRESQL_PAYMENT_SOURCE_VIEW")
            self.assertEqual(r.json["sol_groups"][0]["credit_total"],"130.00")
            self.assertEqual(r.json["sol_groups"][1]["credit_total"],"20.00")
            self.assertEqual(r.json["totals"]["not_calculated"],3)
            self.assertEqual(r.json["totals"]["excluded"],1)
            self.assertEqual(r.json["totals"]["matched"],0)
            self.assertFalse(r.json["reconciliation_executed"])
            self.assertFalse(r.json["financial_writes"])
            self.assertEqual(r.json["report_totals_scope"],"CURRENT_PAGE_ONLY")
            query.assert_called_once()
            self.assertEqual(query.call_args.kwargs["trusted_owner_uid"],
                             "synthetic-owner")

    def test_10_unconfigured_report_is_503_not_fallback_sqlite(self):
        app=self._mock_report()
        with patch.dict(os.environ,{"SBI_R31_PG_REPORT_STAGING_ENABLED":"false"}):
            r=app.test_client().get("/api/payment-received/sol-report")
            self.assertEqual(r.status_code,503)
            self.assertNotIn("UNSAFE_OLD_SQLITE",r.get_data(as_text=True))

    def test_11_invalid_pagination_denied(self):
        app=self._mock_report()
        r=app.test_client().get("/api/payment-received/sol-report?limit=100000")
        self.assertEqual(r.status_code,422)

    def test_12_csrf_origin_not_bypassed_by_overlay(self):
        # The overlay does not add route-level bypasses or public paths;
        # existing app.before_request identity is still the authority.
        app=self._mock_report()
        before_names=[f.__name__ for f in app.before_request_funcs[None]]
        self.assertIn("simulated_verified_firebase_session",before_names)
        self.assertEqual(len(app.before_request_funcs[None]),1)

    def test_13_fake_response_handles_pg_driver_failure_without_secrets(self):
        app=self._mock_report()
        with patch.object(overlay,"_pg",side_effect=RuntimeError("LEAK_DSN_SECRET")):
            r=app.test_client().get("/api/payment-received/sol-report")
            self.assertEqual(r.status_code,503)
            self.assertNotIn("LEAK_DSN_SECRET",r.get_data(as_text=True))

    def test_14_private_summary_csv_only_approved_fields(self):
        app=self._mock_report()
        with patch.object(overlay,"_pg",return_value=FakeConnection()),\
             patch.object(overlay,"sol_summary",return_value=example_summary()):
            r=app.test_client().get("/api/payment-received/sol-report.csv")
            self.assertEqual(r.status_code,200)
            self.assertIn("1505",r.get_data(as_text=True))
            self.assertEqual(r.headers["X-Reconciliation-Engine"],
                             "NOT_CONNECTED")

    def test_15_detail_csv_formula_escaped(self):
        app=self._mock_report()
        from db_r31_pg_sol_report_readonly import DETAIL_FIELDS
        record={k:"" for k in DETAIL_FIELDS}
        record.update(description="=HYPERLINK('bad')",raw_sol="001505")
        with patch.object(overlay,"_pg",return_value=FakeConnection()),\
             patch.object(overlay,"payment_details",return_value={"records":[record]}):
            r=app.test_client().get("/api/payment-received/payment-details.csv")
            self.assertEqual(r.status_code,200)
            rows=list(csv.reader(io.StringIO(r.get_data(as_text=True).lstrip("\ufeff"))))
            self.assertTrue(rows[1][4].startswith("'="))
            self.assertEqual(rows[1][5],"001505")

    def test_16_no_get_report_can_write_financial_db(self):
        app=self._mock_report()
        with patch.object(overlay,"_pg",return_value=FakeConnection()),\
             patch.object(overlay,"sol_summary",return_value=example_summary()):
            r=app.test_client().get("/api/payment-received/sol-report")
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers["X-Financial-Apply"],"LOCKED")
            self.assertFalse(r.json["automatic_invoice_matching_enabled"])


if __name__=="__main__":
    unittest.main()
