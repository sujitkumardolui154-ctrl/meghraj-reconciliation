"""AWS authenticated source reports: no fabricated counts, no finance writes."""
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for location in (ROOT/"staging/aws_login_v150",ROOT/"dashboard_source",ROOT/"staging/railway_public"):
    sys.path.insert(0,str(location))
spec=importlib.util.spec_from_file_location("sbi_report_gate",ROOT/"staging/aws_login_v150/app.py")
server=importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
from aws_readonly_snapshot_reports import NotCertified
CONTRACT=json.loads((ROOT/"backend_source/invoice_import_contract.json").read_text())
HEADERS=CONTRACT["headers"]
KINDS=("unpaid","ok","error-value","balance-review")
def sha(b):return hashlib.sha256(b).hexdigest()
def hpin(headers):
    return sha(json.dumps(headers,ensure_ascii=False,separators=(",",":")).encode())
def csv_bytes(headers,rows):
    output=io.StringIO(newline="")
    writer=csv.writer(output,lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class SourceReportGateTests(unittest.TestCase):
    def setUp(self):
        server.app.testing=True
        self.client=server.app.test_client()
        self.client.set_cookie("__Host-dil_session","synthetic",secure=True)
        self.tmp=tempfile.TemporaryDirectory(prefix="sbi-certified-report-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def auth(self):
        stack=ExitStack()
        user=SimpleNamespace(uid="qa-reader",email="test@example.invalid",
            display_name="QA",disabled=False,custom_claims={"dil_dashboard":True})
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",
                                  return_value={"uid":"qa-reader"}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=user))
        return stack
    def env(self,extra=None):
        vars={"SBI_AWS_REPORT_SNAPSHOT_DIR":str(self.root),
              "SBI_AWS_REPORT_MANIFEST_SHA256":self.manifest_sha,
              "SBI_AWS_APPROVED_53_HEADERS_SHA256":hpin(HEADERS)}
        vars.update(extra or {})
        return patch.dict(os.environ,vars)
    def prepare(self, *, approval="INDEPENDENTLY_APPROVED",expires=None,
                extra_rows=None):
        now=datetime.now(timezone.utc)
        reports={}
        for kind in KINDS:
            row=[""]*53
            row[12]="MXP-SYNTHETIC-TEST-"+kind
            row[20]="-1.25" if kind=="error-value" else "100.00"
            raw=csv_bytes(HEADERS,extra_rows if extra_rows is not None else [row])
            (self.root/(kind+".csv")).write_bytes(raw)
            reports[kind]={
                "file":kind+".csv",
                "row_count":1,
                "column_count":53,
                "classification":"SOURCE_REFERENCE_ONLY",
                "headers":list(HEADERS),
                "sha256":sha(raw)
            }
        manifest={
            "schema":"sbi-aws-phase1-private-snapshot/v1",
            "release_class":"REPORTING_ONLY",
            "approval_status":approval,
            "financial_writes_disabled":True,
            "reconciliation_executed":False,
            "source_sha256":sha(b"synthetic-original-source"),
            "approval_receipt_id":"SYNTHETIC-QA-001",
            "approved_at_utc":(now-timedelta(minutes=1)).isoformat(),
            "expires_at_utc":(expires or now+timedelta(hours=1)).isoformat(),
            "reports":reports
        }
        raw=json.dumps(manifest,sort_keys=True).encode()
        (self.root/"manifest.json").write_bytes(raw)
        self.manifest_sha=sha(raw)

    def test_report_ui_no_longer_requests_legacy_403(self):
        html=(ROOT/"dashboard_source/index.html").read_text()
        self.assertIn('requestReport("/api/reporting/v2", "application/json")',html)
        self.assertIn('requestReport("/api/reporting/v2/" + kind + ".csv", "text/csv")',html)
        self.assertIn("Reports not connected:",html)
        self.assertNotIn('requestReport("/api/reports", "application/json")',html)
        self.assertIn("Verified Read-only Sources",html)

    def test_anonymous_guard_and_legacy_write_denials(self):
        anon=server.app.test_client()
        self.assertEqual(anon.get("/api/reporting/v2").status_code,401)
        self.assertEqual(anon.get("/api/reporting/v2/unpaid.csv").status_code,401)
        self.assertEqual(anon.get("/api/reporting/v2/error-value.csv").status_code,401)
        with self.auth():
            self.assertEqual(self.client.get("/api/reports").status_code,403)
            self.assertEqual(self.client.post("/api/upload",
                headers={"Origin":server.SITE_ORIGIN}).status_code,403)
            self.assertEqual(self.client.post("/api/payment-reconciliation/run",
                headers={"Origin":server.SITE_ORIGIN}).status_code,403)

    def test_unconnected_report_status_is_truthful_and_no_csv(self):
        with self.auth(),patch.dict(os.environ,{
            "SBI_AWS_REPORT_SNAPSHOT_DIR":"",
            "SBI_AWS_REPORT_MANIFEST_SHA256":""}):
            response=self.client.get("/api/reporting/v2")
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json["source_status"],"NOT_CONNECTED")
            self.assertFalse(response.json["financial_writes"])
            self.assertFalse(response.json["financial_data_connected"])
            self.assertEqual(set(response.json["reports"]),set(KINDS))
            self.assertTrue(all(v["status"]=="NOT_CONNECTED"
                for v in response.json["reports"].values()))
            csv_resp=self.client.get("/api/reporting/v2/unpaid.csv")
            self.assertEqual(csv_resp.status_code,503)
            self.assertEqual(csv_resp.json["reason"],"REPORT_DATA_NOT_CONNECTED")

    def test_four_independently_pinned_53_column_csvs_available(self):
        self.assertEqual(len(HEADERS),53)
        self.assertLess(len(set(HEADERS)),53)  # repeats must not be discarded
        self.prepare()
        with self.auth(),self.env():
            index=self.client.get("/api/reporting/v2")
            self.assertEqual(index.status_code,200)
            data=index.json
            self.assertEqual(data["source_status"],"READY")
            self.assertFalse(data["financial_writes"])
            self.assertFalse(data["reconciliation_executed"])
            self.assertEqual(set(data["reports"]),set(KINDS))
            for kind in KINDS:
                result=data["reports"][kind]
                self.assertEqual(result["rows"],1)
                self.assertEqual(result["columns"],53)
                self.assertEqual(result["status"],"AVAILABLE")
                reply=self.client.get("/api/reporting/v2/"+kind+".csv")
                self.assertEqual(reply.status_code,200,kind)
                self.assertIn("attachment",reply.headers["Content-Disposition"])
                self.assertEqual(reply.headers["X-Report-Rows"],"1")
                self.assertEqual(reply.headers["X-Report-Classification"],
                                 "SOURCE_REFERENCE_ONLY")
                rows=list(csv.reader(io.StringIO(reply.data.decode("utf-8-sig"))))
                self.assertEqual(rows[0],HEADERS)
                self.assertEqual(len(rows[1]),53)
            self.assertEqual(self.client.get("/api/reporting/v2/not-approved.csv").status_code,404)

    def test_manifest_missing_approval_and_header_mismatch(self):
        self.prepare()
        with self.auth(),self.env({"SBI_AWS_APPROVED_53_HEADERS_SHA256":"0"*64}):
            result=self.client.get("/api/reporting/v2")
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json["source_status"],"NOT_CERTIFIED")
            self.assertEqual(result.json["reports"]["unpaid"]["reason"],
                             "INDEPENDENT_HEADER_CONTRACT_NOT_VERIFIED")
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").status_code,503)
        with self.auth(),self.env({"SBI_AWS_REPORT_MANIFEST_SHA256":"0"*64}):
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").json["reason"],
                             "SNAPSHOT_MANIFEST_HASH_MISMATCH")
        self.prepare(approval="DRAFT")
        with self.auth(),self.env():
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").json["reason"],
                             "SNAPSHOT_APPROVAL_REQUIRED")
        self.prepare(expires=datetime.now(timezone.utc)-timedelta(minutes=1))
        with self.auth(),self.env():
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").json["reason"],
                             "SNAPSHOT_APPROVAL_EXPIRED")

    def test_tampered_csv_and_formula_injection_denied(self):
        self.prepare()
        (self.root/"ok.csv").write_bytes(b"tampered source")
        with self.auth(),self.env():
            result=self.client.get("/api/reporting/v2/ok.csv")
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json["reason"],"SNAPSHOT_REPORT_HASH_MISMATCH")
            self.assertEqual(self.client.get("/api/reporting/v2").json["source_status"],
                             "PARTIAL_CERTIFIED")
        # Even a SHA-pinned manifest cannot override a dangerous CSV cell.
        dangerous=[""]*53;dangerous[12]="=HYPERLINK(example)"
        self.prepare(extra_rows=[dangerous])
        with self.auth(),self.env():
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").json["reason"],
                             "SNAPSHOT_CSV_FORMULA_NOT_ESCAPED")
if __name__=="__main__":
    unittest.main()
