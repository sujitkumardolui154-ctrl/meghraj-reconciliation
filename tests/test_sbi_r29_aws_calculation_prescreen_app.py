"""R29 private AWS candidate gateway negative tests (synthetic only)."""
import base64
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts/ci"))
spec=importlib.util.spec_from_file_location(
    "r29_prescreen_gateway",ROOT/"backend_source/aws_calculation_prescreen_app.py")
gateway=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

USER="synthetic-private-user"
PASSWORD="offline-synthetic-password-123456789"
BASIC="Basic "+base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
SHA="a"*64

def sample():
    return {
        "mode":"PRE_SCREENED_CANDIDATE_REVIEW_ONLY",
        "source_sha256":SHA,
        "records":[
            {"role":"INVOICE","source_row":2,"source_identity":"SYN-MXP100",
             "result":"PASS","reasons":[]},
            {"role":"INVOICE","source_row":3,"source_identity":"SYN-MXP101",
             "result":"EXCLUDE","reasons":["GST_TOTAL_MISMATCH"]},
            {"role":"INVOICE","source_row":4,"source_identity":"SYN-MXP102",
             "result":"HOLD","reasons":["SOL_MASTER_REVIEW"]},
            {"role":"PAYMENT","source_row":2,"source_identity":"SYN-BANK100",
             "result":"PASS","reasons":[]},
            {"role":"PAYMENT","source_row":3,"source_identity":"SYN-BANK101",
             "result":"EXCLUDE","reasons":["INVALID_BANK_CREDIT"]},
            {"role":"PAYMENT","source_row":4,"source_identity":"SYN-BANK102",
             "result":"HOLD","reasons":["BANK_UTR_REVIEW"]},
        ],
        "matches":[
            {"invoice_row":2,"payment_row":2,"result":"PASS","reasons":[]},
            {"invoice_row":3,"payment_row":2,"result":"PASS","reasons":[]},
            {"invoice_row":2,"payment_row":3,"result":"PASS","reasons":[]},
            {"invoice_row":4,"payment_row":4,"result":"PASS","reasons":[]},
        ],
    }


class R29GatewayTests(unittest.TestCase):
    def setUp(self):
        self.environ=patch.dict(os.environ,{
            "SBI_CALC_PREVIEW_ENABLED":"true",
            "SBI_FINANCIAL_APPLY":"LOCKED",
            "SBI_CALC_PREVIEW_USERNAME":USER,
            "SBI_CALC_PREVIEW_PASSWORD":PASSWORD,
        })
        self.environ.start();self.addCleanup(self.environ.stop)
        gateway.app.testing=True
        self.client=gateway.app.test_client()

    def post(self,data=None,auth=True):
        headers={"Authorization":BASIC} if auth else {}
        return self.client.post("/api/candidate-screen",json=data if data is not None else sample(),
                                headers=headers)

    def test_01_health_explicitly_not_full_engine(self):
        r=self.client.get("/healthz")
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json["full_v251_v239_engine_connected"])
        self.assertEqual(r.json["engine"],"FULL_V251_V239_NOT_CONNECTED")
        self.assertFalse(r.json["formal_financial_certificate_required"])
        self.assertEqual(r.json["real_database_writes"],0)

    def test_02_ready_only_for_prescreen(self):
        r=self.client.get("/readyz")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["status"],"READY_FOR_PRE_SCREENED_TEST_ONLY")
        self.assertFalse(r.json["payment_final_status_authorized"])

    def test_03_absent_auth_denied(self):
        r=self.post(auth=False)
        self.assertEqual(r.status_code,401)
        self.assertEqual(r.json["reason_code"],"AUTH_REQUIRED")
        self.assertIn("Basic",r.headers["WWW-Authenticate"])

    def test_04_bad_auth_denied(self):
        r=self.client.post("/api/candidate-screen",json=sample(),headers={
            "Authorization":"Basic "+base64.b64encode(b"bad:wrong").decode()})
        self.assertEqual(r.status_code,401)

    def test_05_preview_disabled_denied(self):
        with patch.dict(os.environ,{"SBI_CALC_PREVIEW_ENABLED":"false"}):
            self.assertEqual(self.post().status_code,503)
            self.assertEqual(self.client.get("/readyz").status_code,503)

    def test_06_apply_unlocked_denied(self):
        with patch.dict(os.environ,{"SBI_FINANCIAL_APPLY":"ENABLED"}):
            self.assertEqual(self.post().status_code,503)
            self.assertEqual(self.client.get("/readyz").status_code,503)

    def test_07_short_password_denied(self):
        with patch.dict(os.environ,{"SBI_CALC_PREVIEW_PASSWORD":"short"}):
            self.assertEqual(self.post().status_code,503)
            self.assertEqual(self.client.get("/readyz").status_code,503)

    def test_08_missing_username_denied(self):
        with patch.dict(os.environ,{"SBI_CALC_PREVIEW_USERNAME":""}):
            self.assertEqual(self.post().status_code,503)

    def test_09_valid_screen_individual_exclusions(self):
        r=self.post()
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["summary"]["eligible_invoice_rows"],1)
        self.assertEqual(r.json["summary"]["eligible_payment_rows"],1)
        self.assertEqual(r.json["summary"]["excluded_record_count"],2)
        self.assertEqual(r.json["summary"]["held_record_count"],2)
        self.assertEqual(r.json["summary"]["method_candidate_pair_count"],1)
        self.assertEqual(r.json["summary"]["excluded_pair_count"],2)
        self.assertEqual(r.json["summary"]["held_pair_count"],1)
        self.assertEqual(r.json["candidate_row_pairs"][0]["invoice_source_row"],2)
        self.assertEqual(r.json["candidate_row_pairs"][0]["payment_source_row"],2)
        self.assertFalse(r.json["full_matching_rules_executed"])
        self.assertFalse(r.json["final_payment_status_assigned"])
        self.assertFalse(r.json["reconciliation_executed"])
        self.assertEqual(r.json["real_bank_allocations"],0)
        self.assertEqual(r.json["real_database_writes"],0)
        self.assertEqual(r.json["financial_apply"],"LOCKED")

    def test_10_source_names_not_leaked_in_response(self):
        payload=sample()
        payload["records"][0]["source_identity"]="SYN-PRIVATE-UNIQUE-CUSTOMER-TOKEN"
        r=self.post(payload)
        self.assertEqual(r.status_code,200)
        self.assertNotIn("SYN-PRIVATE-UNIQUE-CUSTOMER-TOKEN",r.get_data(as_text=True))

    def test_11_no_auth_report_endpoint(self):
        self.assertEqual(self.client.get("/reports").status_code,403)

    def test_12_no_upload_endpoint(self):
        self.assertEqual(self.client.post("/api/upload").status_code,403)

    def test_13_no_settle_endpoint(self):
        self.assertEqual(self.client.post("/api/settle").status_code,403)

    def test_14_no_db_update_endpoint(self):
        self.assertEqual(self.client.post("/database/update").status_code,403)

    def test_15_no_get_candidate_results(self):
        self.assertEqual(self.client.get("/api/candidate-screen").status_code,403)

    def test_16_bad_json_type_rejected(self):
        r=self.client.post("/api/candidate-screen",data="unstructured",
                           content_type="text/plain",headers={"Authorization":BASIC})
        self.assertEqual(r.status_code,415)

    def test_17_json_schema_rejects_write_flags(self):
        x=sample();x["write_to_db"]=True
        self.assertEqual(self.post(x).status_code,422)

    def test_18_financial_method_mode_rejected(self):
        x=sample();x["mode"]="SETTLEMENT_POST"
        self.assertEqual(self.post(x).status_code,422)

    def test_19_wrong_sha_rejected(self):
        x=sample();x["source_sha256"]="not a sha"
        self.assertEqual(self.post(x).status_code,422)

    def test_20_unknown_payment_source_rejected(self):
        x=sample();x["matches"][0]["payment_row"]=8888
        self.assertEqual(self.post(x).status_code,422)

    def test_21_duplicate_invoice_rejected_locally_not_global(self):
        x=sample()
        x["records"].append({"role":"INVOICE","source_row":6,"source_identity":"SYN-MXP100",
                  "result":"PASS","reasons":[]})
        r=self.post(x)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["summary"]["method_candidate_pair_count"],0)
        self.assertIn("DUPLICATE_SOURCE_IDENTITY",str(r.json["excluded_source_rows"]))

    def test_22_over_1000_rows_rejected(self):
        x=sample()
        x["records"]=[{"role":"INVOICE","source_row":i+2,"source_identity":f"SYN-{i}",
                       "result":"PASS","reasons":[]} for i in range(1001)]
        self.assertEqual(self.post(x).status_code,422)

    def test_23_over_512k_rejected(self):
        headers={"Authorization":BASIC}
        r=self.client.post("/api/candidate-screen",
            data="x"*(512*1024+1),content_type="application/json",headers=headers)
        self.assertEqual(r.status_code,413)

    def test_24_noninteger_source_row_rejected(self):
        x=sample();x["records"][0]["source_row"]=True
        self.assertEqual(self.post(x).status_code,422)

    def test_25_noninteger_edge_row_rejected(self):
        x=sample();x["matches"][0]["invoice_row"]="2"
        self.assertEqual(self.post(x).status_code,422)

    def test_26_provisional_dnm_never_candidate(self):
        x=sample();x["matches"][0]["result"]="HOLD"
        x["matches"][0]["reasons"]=["DNM_PROVISIONAL"]
        r=self.post(x)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["summary"]["method_candidate_pair_count"],0)
        self.assertEqual(r.json["summary"]["held_pair_count"],2)

    def test_27_headers_noncacheable(self):
        for r in (self.client.get("/healthz"),self.post()):
            self.assertEqual(r.headers["Cache-Control"],"no-store, private")
            self.assertEqual(r.headers["X-Frame-Options"],"DENY")
            self.assertEqual(r.headers["Content-Security-Policy"],"default-src 'none'")

    def test_28_original_request_never_mutated(self):
        x=sample();before=copy.deepcopy(x)
        self.assertEqual(self.post(x).status_code,200)
        self.assertEqual(x,before)

    def test_29_no_claim_source_verification(self):
        r=self.post()
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json["screening_evidence_independently_verified"])
        self.assertFalse(r.json["full_matching_rules_executed"])

    def test_30_invalid_role_blocked(self):
        x=sample();x["records"][0]["role"]="FINANCE_ADMIN"
        self.assertEqual(self.post(x).status_code,422)


if __name__=="__main__":
    unittest.main()
