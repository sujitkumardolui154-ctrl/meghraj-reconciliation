"""Owner's D-023 logic-only deployment restriction — synthetic contract QA only."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "logic_only_deploy_gate.py"
spec = importlib.util.spec_from_file_location("logic_only_deploy_gate", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def policy():
    data = dict(mod.REQUIRED)
    data.update({
        "existing_finance_data_paths": [],
        "historical_backfill_jobs": [],
        "financial_database_endpoints": [],
    })
    return data


class OwnerLogicOnlyDeploymentPolicyTests(unittest.TestCase):
    def test_only_fully_blocked_synthetic_manifest_passes(self):
        result = mod.check_logic_only_manifest(policy())
        self.assertEqual(result["status"], "SOURCE_POLICY_CONTRACT_PASS_ONLY")
        self.assertEqual(result["test_source"], "SYNTHETIC_ONLY")
        self.assertFalse(result["production_deployed"])
        self.assertFalse(result["host_isolation_verified"])

    def test_absent_manifest_fails_closed(self):
        with self.assertRaises(mod.LogicOnlyPolicyBlocked):
            mod.check_logic_only_manifest({})

    def test_historical_read_recalculation_mutation_replay_are_forbidden(self):
        for flag in (
            "historical_invoice_reads", "historical_payment_reads",
            "historical_credit_note_reads", "historical_gst_reads",
            "historical_financial_calculations", "reconciliation_replay",
            "automatic_backfill", "database_migration",
            "existing_allocation_mutation", "prior_status_changes",
            "legacy_finance_database_connection", "existing_financial_source_mounts",
            "auto_process_old_evidence", "production_traffic_change",
            "financial_write_permission",
        ):
            with self.subTest(flag=flag):
                data = policy()
                data[flag] = True
                with self.assertRaises(mod.LogicOnlyPolicyBlocked):
                    mod.check_logic_only_manifest(data)

    def test_mounted_data_or_backfill_jobs_forbidden(self):
        for key in ("existing_finance_data_paths",
                    "historical_backfill_jobs", "financial_database_endpoints"):
            with self.subTest(key=key):
                data = policy()
                data[key] = ["PROHIBITED"]
                with self.assertRaises(mod.LogicOnlyPolicyBlocked):
                    mod.check_logic_only_manifest(data)

    def test_real_record_test_source_denied(self):
        data = policy()
        data["test_source"] = "HISTORICAL_WORKBOOK"
        with self.assertRaises(mod.LogicOnlyPolicyBlocked):
            mod.check_logic_only_manifest(data)

    def test_wrong_type_denied_not_truthy(self):
        data = policy()
        data["historical_financial_calculations"] = 0
        with self.assertRaises(mod.LogicOnlyPolicyBlocked):
            mod.check_logic_only_manifest(data)

if __name__ == "__main__":
    unittest.main()
