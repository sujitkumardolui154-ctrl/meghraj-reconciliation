"""Bulk Report button is functional, source-only, and cannot update finance."""
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
for folder in (ROOT/"dashboard_source",ROOT/"staging/aws_login_v150",
               ROOT/"staging/railway_public",ROOT/"backend_source"):
    sys.path.insert(0,str(folder))
from invoice_source_schema import HEADERS_53,HEADERS_34,HEADERS_35
spec=importlib.util.spec_from_file_location("sbi_bulk_report_v1",ROOT/"staging/aws_login_v150/app.py")
server=importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def xlsx(headers, rows, sheet=None):
    workbook=Workbook()
    ws=workbook.active
    ws.title=sheet or ("Invoice Details." if len(headers)!=53 else "SOURCE 53")
    ws.append(headers)
    for row in rows:
        ws.append(row)
    out=io.BytesIO()
    workbook.save(out)
    workbook.close()
    return out.getvalue()


def make_row(headers,invoice,paid=None,balance=0):
    vals=[""]*len(headers)
    width=len(headers)
    invoice_index={53:12,35:10,34:9}[width]
    pay_index={53:20,35:18,34:17}[width]
    balance_index={53:27,35:25,34:24}[width]
    vals[invoice_index]=invoice
    vals[pay_index]=paid
    vals[balance_index]=balance
    return vals


class BulkReportTests(unittest.TestCase):
    def setUp(self):
        server.app.testing=True
        self.client=server.app.test_client()
        self.client.set_cookie("__Host-dil_session","test-session",secure=True)
        self.client.set_cookie("__Host-dil_csrf","a"*64,secure=True)
    def auth(self,uid="report-owner"):
        stack=ExitStack()
        user=SimpleNamespace(uid=uid,email="test@example.invalid",
            display_name="QA",disabled=False,custom_claims={"dil_dashboard":True})
        stack.enter_context(patch("dashboard_sessions.firebase_app",return_value=None))
        stack.enter_context(patch("dashboard_sessions.auth.verify_session_cookie",
                                  return_value={"uid":uid}))
        stack.enter_context(patch("dashboard_sessions.auth.get_user",return_value=user))
        return stack
    def headers(self):
        return {"Origin":server.SITE_ORIGIN,"X-DIL-CSRF":"a"*64}
    def submit(self,body,filename="invoices.xlsx",headers=None):
        return self.client.post("/api/bulk-report/generate",
            data={"file":(io.BytesIO(body),filename)},
            headers=self.headers() if headers is None else headers,
            content_type="multipart/form-data")
    def assert_zip(self,resp):
        self.assertEqual(resp.status_code,200,resp.get_data(as_text=True)[:1000])
        self.assertEqual(resp.headers["X-Bulk-Report-Mode"],"SOURCE_ONLY_NOT_RECONCILED")
        self.assertIn("application/zip",resp.headers["Content-Type"])
        with zipfile.ZipFile(io.BytesIO(resp.data)) as archive:
            files={name:archive.read(name) for name in archive.namelist()}
        self.assertEqual(set(files),{
            "all-invoices.csv","unpaid.csv","ok.csv","error-value.csv",
            "balance-review.csv","validation-review.csv","manifest.json"})
        return files,json.loads(files["manifest.json"])
    def csv_rows(self,files,name):
        return list(csv.reader(io.StringIO(files[name].decode("utf-8-sig"))))

    def test_reports_tab_replaces_old_disabled_upload_with_working_action(self):
        html=(ROOT/"dashboard_source/index.html").read_text(encoding="utf-8")
        start=html.index('<main id="dil-reports"')
        end=html.index("</main>",start)
        reports=html[start:end]
        db=html[html.index('<main id="dil-imports"'):]
        self.assertIn('id="bulk-report-heading">Bulk Report',reports)
        self.assertIn('id="bulk-report-button" type="submit">Generate Bulk Report',reports)
        self.assertIn('id="bulk-report-file" name="file"',reports)
        self.assertIn('fetch("/api/bulk-report/generate"',reports)
        self.assertIn('headers:{"X-DIL-CSRF":csrf.csrf_token}',reports)
        self.assertNotIn("Excel Upload — Dashboard v1.3.0",html)
        self.assertNotIn('id="bulk-report"',db)
        self.assertNotIn('"/api/upload"',reports)
        self.assertIn('id="dil-import-form"',db)
        self.assertIn('id="dil-db-payments"',db)

    def test_auth_and_financial_write_denials(self):
        anonymous=server.app.test_client()
        self.assertEqual(anonymous.get("/api/bulk-report/status").status_code,401)
        self.assertEqual(anonymous.post("/api/bulk-report/generate").status_code,403)
        with self.auth():
            health=self.client.get("/api/bulk-report/status")
            self.assertEqual(health.status_code,200)
            self.assertFalse(health.json["financial_writes"])
            self.assertEqual(health.json["max_rows"],20000)
            self.assertEqual(self.client.post("/api/bulk-report/generate",
                headers={"Origin":server.SITE_ORIGIN}).status_code,403)
            self.assertEqual(self.submit(xlsx(HEADERS_53,[make_row(HEADERS_53,"MXP-SYNTHETIC")]),
                headers={"Origin":"https://evil.invalid","X-DIL-CSRF":"a"*64}).status_code,403)
            for route in ("/api/upload","/api/payment-reconciliation/run","/api/imports/apply"):
                self.assertEqual(self.client.post(route,headers=self.headers()).status_code,403,route)

    def test_53_column_source_reports_and_review_export(self):
        rows=[
            make_row(HEADERS_53,"MXP-SYN-U",None,None),
            make_row(HEADERS_53,"MXP-SYN-O",100,0),
            make_row(HEADERS_53,"MXP-SYN-E",-10,0),
            make_row(HEADERS_53,"MXP-SYN-D",0,0),
            make_row(HEADERS_53,"MXP-SYN-D",0,0),
            make_row(HEADERS_53,123456,50,0),
            make_row(HEADERS_53,"MXP-SYN-F","=1+1",0),
        ]
        body=xlsx(HEADERS_53,rows)
        with self.auth(),patch.dict(os.environ,{
            "SBI_AWS_REPORT_SNAPSHOT_DIR":"",
            "SBI_AWS_REPORT_MANIFEST_SHA256":""}):
            response=self.submit(body)
            files,manifest=self.assert_zip(response)
            c=manifest["counts"]
            self.assertEqual(c["source_rows"],7)
            self.assertEqual(c["accepted_unique_invoice_rows"],4)
            self.assertEqual(c["review_rows"],3)
            self.assertEqual(c["unpaid"],1)
            self.assertEqual(c["ok"],1)
            self.assertEqual(c["error-value"],2)
            self.assertEqual(c["balance-review"],1)
            self.assertEqual(manifest["source_sha256"],hashlib.sha256(body).hexdigest())
            self.assertFalse(manifest["financial_writes"])
            self.assertFalse(manifest["reconciliation_executed"])
            self.assertFalse(manifest["database_updated"])
            self.assertEqual(self.csv_rows(files,"all-invoices.csv")[0],HEADERS_53)
            self.assertLess(len(set(HEADERS_53)),53)
            errors=self.csv_rows(files,"validation-review.csv")
            self.assertEqual(len(errors)-1,3)
            self.assertIn("DUPLICATE_INVOICE_NUMBER",str(errors))
            self.assertIn("INVOICE_NUMBER_MUST_BE_TEXT",str(errors))
            self.assertEqual(self.client.get("/api/reporting/v2").json["source_status"],
                             "NOT_CONNECTED")
            self.assertEqual(self.client.get("/api/reporting/v2/unpaid.csv").status_code,503)

    def test_34_and_35_approved_headers_preserve_projection(self):
        for headers in (HEADERS_34,HEADERS_35):
            row=make_row(headers,"MXP-SYN-"+str(len(headers)),42,0)
            row[6]="1505"
            if len(headers)==35: row[8]="1505"
            with self.subTest(columns=len(headers)),self.auth():
                files,manifest=self.assert_zip(self.submit(xlsx(headers,[row])))
                self.assertEqual(manifest["source_layout_columns"],len(headers))
                self.assertEqual(manifest["counts"]["ok"],1)
                output=self.csv_rows(files,"ok.csv")
                self.assertEqual(len(output[1]),53)
                self.assertEqual(output[1][6],"1505")
                self.assertEqual(output[1][10],("1505" if len(headers)==35 else ""))
                self.assertEqual(output[1][12],"MXP-SYN-"+str(len(headers)))
                self.assertEqual(output[1][8],"")
                self.assertFalse(manifest["financial_writes"])

    def test_invalid_workbooks_rejected_without_artifacts(self):
        with self.auth():
            self.assertEqual(self.submit(b"invalid bytes").status_code,422)
            self.assertEqual(self.submit(b"not xlsx",filename="old.xls").status_code,422)
            bad=xlsx(["Invoice","Amount"],[["INV","1"]])
            resp=self.submit(bad)
            self.assertEqual(resp.status_code,422)
            self.assertIn("approved",resp.json["error"].lower())
            self.assertFalse(resp.json["financial_writes"])
            self.assertEqual(self.submit(b"").status_code,413)

    def test_malicious_formula_is_escaped_in_csv(self):
        row=make_row(HEADERS_53,"MXP-SYN-P",100,0)
        row[7]="=HYPERLINK(\"evil\")"
        with self.auth():
            files,manifest=self.assert_zip(self.submit(xlsx(HEADERS_53,[row])))
            value=self.csv_rows(files,"ok.csv")[1][7]
            self.assertTrue(value.startswith("'="))
            self.assertEqual(manifest["counts"]["accepted_unique_invoice_rows"],1)
if __name__=="__main__":
    unittest.main()
