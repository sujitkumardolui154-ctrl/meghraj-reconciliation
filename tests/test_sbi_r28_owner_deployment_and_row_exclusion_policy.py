"""Owner decision R28: no certification gate for calculation deployment.

Synthetic only. No real SBI source, bank event, live deployment or DB writes.
"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r28_owner_deployment_and_row_exclusion_policy import (
    ScreenedSourceRecord as R, ScreenedMatch as M,
    OperatorTechnicalChecks as Checks, DeploymentScopeRefusal,
    assess_calculation_deployment, partition_screened_source,
)

SHA="b"*64

def technical(**updates):
    args=dict(source_file_fresh=True,release_code_tests_passed=True,
        access_control_and_role_deny_verified=True,
        immutable_source_and_audit_verified=True,
        production_financial_write_disabled=True)
    args.update(updates)
    return Checks(**args)


def source_records():
    return (
        R("INVOICE",2,"MXP100","PASS"),
        R("INVOICE",3,"MXP101","EXCLUDE",("GST_TOTAL_CONFLICT",)),
        R("INVOICE",4,"MXP102","HOLD",("MASTER_ALIAS_REVIEW",)),
        R("INVOICE",5,"MXP103","PASS"),
        R("PAYMENT",2,"EV-001","PASS"),
        R("PAYMENT",3,"EV-002","EXCLUDE",("BANK_CREDIT_INVALID",)),
        R("PAYMENT",4,"EV-003","HOLD",("BANK_UTR_REVIEW",)),
        R("PAYMENT",5,"EV-004","PASS"),
    )


class DeploymentNoCertTest(unittest.TestCase):
    def refused(self,code,fun,*args,**kw):
        with self.assertRaisesRegex(DeploymentScopeRefusal,code):
            fun(*args,**kw)

    def test_01_deployment_candidate_without_finance_certificate(self):
        x=assess_calculation_deployment(technical())
        self.assertTrue(x["operator_reported_deployment_candidate"])
        self.assertFalse(x["formal_financial_certification_required_for_deployment"])
        self.assertFalse(x["aws_or_production_deployment_performed"])
        self.assertFalse(x["database_financial_writes_authorized"])
        self.assertFalse(x["payment_status_assignment_authorized"])
        self.assertTrue(x["financial_apply_locked"])

    def test_02_missing_certification_is_not_a_blocker(self):
        self.assertFalse(assess_calculation_deployment(
            technical(),formal_financial_certificate=None)[
                "formal_financial_certification_required_for_deployment"])

    def test_03_a_pasted_finance_certificate_cannot_escalate_scope(self):
        self.refused("FINANCIAL_CERTIFICATE_NOT_A_DEPLOYMENT_PERMISSION_TOKEN",
            assess_calculation_deployment,technical(),
            formal_financial_certificate="CERT-OWNER-SELF-SIGNED")

    def test_04_unauthenticated_role_deny_blocks_candidate(self):
        x=assess_calculation_deployment(technical(
            access_control_and_role_deny_verified=False))
        self.assertFalse(x["operator_reported_deployment_candidate"])

    def test_05_unverified_source_blocks_candidate(self):
        x=assess_calculation_deployment(technical(source_file_fresh=False))
        self.assertFalse(x["operator_reported_deployment_candidate"])

    def test_06_failed_technical_tests_blocks_candidate(self):
        x=assess_calculation_deployment(technical(release_code_tests_passed=False))
        self.assertFalse(x["operator_reported_deployment_candidate"])

    def test_07_no_source_audit_blocks_candidate(self):
        x=assess_calculation_deployment(
            technical(immutable_source_and_audit_verified=False))
        self.assertFalse(x["operator_reported_deployment_candidate"])

    def test_08_financial_apply_unlock_rejected(self):
        self.refused("FINANCIAL_APPLY_AND_DB_WRITE_MUST_REMAIN_DISABLED",
            assess_calculation_deployment,technical(),financial_apply="UNLOCKED")

    def test_09_db_write_flag_rejected(self):
        self.refused("FINANCIAL_APPLY_AND_DB_WRITE_MUST_REMAIN_DISABLED",
            assess_calculation_deployment,technical(
                production_financial_write_disabled=False))

    def test_10_deployment_scope_escalation_refused(self):
        self.refused("FINANCIAL_WRITE_DEPLOYMENT_SCOPE_FORBIDDEN",
            assess_calculation_deployment,technical(),scope="SETTLEMENT_WRITE")

    def test_11_technical_claims_not_independently_attested(self):
        self.assertFalse(assess_calculation_deployment(
            technical())["technical_prerequisites_independently_attested_by_module"])


class IndividualExclusionTest(unittest.TestCase):
    def refused(self,code,records,steps=(),**kw):
        with self.assertRaisesRegex(DeploymentScopeRefusal,code):
            partition_screened_source(records,steps,source_sha256=SHA,**kw)

    def test_12_failed_invoice_and_payment_do_not_block_valid_ones(self):
        match=(
            M(2,2,"PASS"),
            M(3,2,"PASS"),
            M(2,3,"PASS"),
            M(4,4,"PASS"),
            M(5,5,"PASS"),
        )
        x=partition_screened_source(source_records(),match,source_sha256=SHA)
        summary=x["summary"]
        self.assertEqual(summary["eligible_invoice_rows"],2)
        self.assertEqual(summary["eligible_payment_rows"],2)
        self.assertEqual(summary["excluded_record_count"],2)
        self.assertEqual(summary["held_record_count"],2)
        self.assertEqual(summary["method_candidate_pair_count"],2)
        self.assertEqual(summary["excluded_pair_count"],2)
        self.assertEqual(summary["held_pair_count"],1)
        self.assertEqual(x["source_rows_deleted"],0)
        self.assertEqual(x["real_bank_allocations"],0)
        self.assertFalse(x["payment_status_column_m_written"])
        self.assertEqual(x["real_database_writes"],0)

    def test_13_unmatched_record_remains_without_being_settled(self):
        x=partition_screened_source(source_records(),(),source_sha256=SHA)
        self.assertEqual(x["summary"]["source_record_count"],8)
        self.assertEqual(len(x["method_candidates"]),0)
        self.assertEqual(x["summary"]["eligible_invoice_rows"],2)
        self.assertTrue(x["financial_apply_locked"])

    def test_14_duplicate_invoice_identity_local_group_excluded(self):
        rec=source_records()+(R("INVOICE",6,"MXP100","PASS"),)
        x=partition_screened_source(rec,(M(2,2,"PASS"),M(5,5,"PASS")),
            source_sha256=SHA)
        self.assertEqual(x["summary"]["excluded_record_count"],4)
        self.assertEqual(x["summary"]["method_candidate_pair_count"],1)
        self.assertEqual(x["summary"]["excluded_pair_count"],1)
        self.assertEqual(x["excluded_records"][0]["reason_codes"][-1],
                         "DUPLICATE_SOURCE_IDENTITY")
        self.assertTrue(any(r["source_row"]==6 for r in x["excluded_records"]))

    def test_15_duplicate_bank_reference_excluded_without_stopping_others(self):
        rec=source_records()+(R("PAYMENT",6,"EV-001","PASS"),)
        x=partition_screened_source(rec,(M(2,2,"PASS"),M(5,5,"PASS")),
            source_sha256=SHA)
        self.assertEqual(x["summary"]["excluded_record_count"],4)
        self.assertEqual(x["summary"]["method_candidate_pair_count"],1)

    def test_16_hold_source_cannot_form_pass_candidate(self):
        x=partition_screened_source(source_records(),(M(4,4,"PASS"),),source_sha256=SHA)
        self.assertEqual(len(x["method_candidates"]),0)
        self.assertEqual(x["held_pairs"][0]["reason_codes"],("SOURCE_RECORD_ON_HOLD",))

    def test_17_excluded_match_can_be_skipped_without_global_block(self):
        x=partition_screened_source(source_records(),(
            M(2,2,"EXCLUDE",("SERVICE_PERIOD_MISMATCH",)),
            M(5,5,"PASS"),
        ),source_sha256=SHA)
        self.assertEqual(len(x["method_candidates"]),1)
        self.assertEqual(x["excluded_pairs"][0]["reason_codes"],
                         ("SERVICE_PERIOD_MISMATCH",))

    def test_18_invalid_persist_authorization_is_rejected(self):
        self.refused("FINANCIAL_APPLY_LOCK_REQUIRED",source_records(),
                    financial_apply="ENABLED")

    def test_19_duplicate_source_row_refused(self):
        self.refused("DUPLICATE_OR_FORGED_SOURCE_ROW",
                    source_records()+(R("INVOICE",2,"MXP900","PASS"),))

    def test_20_unsupported_screen_result_refused(self):
        self.refused("UNKNOWN_RECORD_SCREEN_RESULT",
                    (R("INVOICE",2,"MXP100","OK"),))

    def test_21_result_without_reason_inconsistent(self):
        self.refused("SCREEN_RESULT_REASON_INCONSISTENT",
                    (R("INVOICE",2,"MXP100","HOLD"),))

    def test_22_pass_with_error_inconsistent(self):
        self.refused("SCREEN_RESULT_REASON_INCONSISTENT",
                    (R("INVOICE",2,"MXP100","PASS",("ERROR",)),))

    def test_23_unknown_invoice_in_edge_refused(self):
        self.refused("MATCH_REFERENCES_UNKNOWN_SOURCE_ROW",
                    source_records(),(M(2222,2,"PASS"),))

    def test_24_unknown_payment_in_edge_refused(self):
        self.refused("MATCH_REFERENCES_UNKNOWN_SOURCE_ROW",
                    source_records(),(M(2,2222,"PASS"),))

    def test_25_duplicate_edge_refused(self):
        self.refused("DUPLICATE_SCREENED_EDGE",
                    source_records(),(M(2,2,"PASS"),M(2,2,"PASS")))

    def test_26_invalid_sha_refused(self):
        with self.assertRaisesRegex(DeploymentScopeRefusal,
                                    "ORIGINAL_SOURCE_SHA256_REQUIRED"):
            partition_screened_source(source_records(),(),source_sha256="0")

    def test_27_bad_source_reasons_refused(self):
        self.refused("INVALID_SCREEN_REASON",
                    (R("INVOICE",2,"MXP100","HOLD",("Private narration leaked",)),))

    def test_28_status_not_granted_even_if_all_pass(self):
        x=partition_screened_source((
            R("INVOICE",2,"MXP100","PASS"),
            R("PAYMENT",2,"EV-001","PASS")),
            (M(2,2,"PASS"),),source_sha256=SHA)
        self.assertEqual(len(x["method_candidates"]),1)
        self.assertFalse(x["screening_results_externally_verified"])
        self.assertFalse(x["full_engine_financial_certification_claimed"])
        self.assertFalse(x["production_deployment_claimed"])
        self.assertFalse(x["payment_status_column_m_written"])

    def test_29_empty_source_no_calculated_match(self):
        x=partition_screened_source((),(),source_sha256=SHA)
        self.assertEqual(x["summary"]["source_record_count"],0)
        self.assertEqual(x["summary"]["method_candidate_pair_count"],0)
        self.assertEqual(x["real_bank_allocations"],0)

    def test_30_provisional_dnm_cannot_become_candidate(self):
        x=partition_screened_source(source_records(),(
            M(2,2,"HOLD",("DNM_PROVISIONAL",)),M(5,5,"PASS")),
            source_sha256=SHA)
        self.assertEqual(x["summary"]["method_candidate_pair_count"],1)
        self.assertEqual(x["held_pairs"][0]["reason_codes"],("DNM_PROVISIONAL",))


if __name__=="__main__":
    unittest.main()
