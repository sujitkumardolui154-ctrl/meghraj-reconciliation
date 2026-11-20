"""Database Update navigation: relocated Excel Upload and safe payment entry.

No live Firebase, financial API, invoice DB, or payment evidence is used.
"""
import importlib.util
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
DASH=ROOT/"dashboard_source"
LOGIN=ROOT/"staging/aws_login_v150"
for folder in (DASH,LOGIN,ROOT/"staging/railway_public"):
    sys.path.insert(0,str(folder))
spec=importlib.util.spec_from_file_location("database_nav_release",LOGIN/"app.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContainerParser(HTMLParser):
    VOID={"area","base","br","col","embed","hr","img","input","link","meta",
          "param","source","track","wbr"}
    def __init__(self):
        super().__init__()
        self.stack=[]
        self.by_id={}
    def handle_starttag(self,tag,attrs):
        props=dict(attrs)
        current=[(name,ident) for name,ident in self.stack if ident]
        if props.get("id"):
            self.by_id[props["id"]]={"tag":tag,"attributes":props,
                                      "ancestor_ids":[x[1] for x in current]}
        if tag not in self.VOID:
            self.stack.append((tag,props.get("id")))
    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==tag:
                del self.stack[index:]
                return


class DatabaseUpdateNavigationTests(unittest.TestCase):
    def setUp(self):
        module.app.testing=True
        self.client=module.app.test_client()
        self.html=(DASH/"index.html").read_text(encoding="utf-8")
        self.css=(DASH/"dashboard_theme.css").read_text(encoding="utf-8")
        self.parser=ContainerParser()
        self.parser.feed(self.html)
    def test_excel_upload_is_inside_database_invoice_view_only(self):
        nodes=self.parser.by_id
        upload=nodes["excel-upload"]
        self.assertEqual(upload["tag"],"section")
        self.assertIn("dil-imports",upload["ancestor_ids"])
        self.assertIn("dil-db-invoices",upload["ancestor_ids"])
        self.assertNotIn("dil-home",upload["ancestor_ids"])
        self.assertEqual(nodes["excel-upload-form"]["tag"],"form")
        self.assertIn("dil-db-invoices",nodes["excel-upload-form"]["ancestor_ids"])
        self.assertIn("disabled",nodes["excel-file"]["attributes"])
        self.assertIn("disabled",nodes["excel-upload-button"]["attributes"])
        self.assertIn("dil-db-invoices",nodes["dil-import-form"]["ancestor_ids"])
        self.assertIn("dil-db-invoices",nodes["dil-import-receipt"]["ancestor_ids"])
        self.assertIn("dil-db-invoices",nodes["dil-import-log"]["ancestor_ids"])
        self.assertEqual(self.html.count("<!-- DIL Excel Upload v1.3.0 -->"),1)
    def test_database_has_two_accessible_switchable_views(self):
        nodes=self.parser.by_id
        self.assertIn("dil-imports",nodes)
        self.assertEqual(nodes["dil-db-invoices-button"]["attributes"]["aria-selected"],"true")
        self.assertEqual(nodes["dil-db-payments-button"]["attributes"]["aria-selected"],"false")
        self.assertEqual(nodes["dil-db-payments-button"]["attributes"]["role"],"tab")
        self.assertIn("hidden",nodes["dil-db-payments"]["attributes"])
        self.assertIn("dil-imports",nodes["dil-db-payments"]["ancestor_ids"])
        self.assertIn('invoiceButton.addEventListener("click", () => show("invoices"))',self.html)
        self.assertIn('paymentButton.addEventListener("click", () => show("payments"))',self.html)
        self.assertIn('invoice.hidden = !invoicesActive;',self.html)
        self.assertIn('payment.hidden = invoicesActive;',self.html)
        self.assertIn(".dil-db-switch button[aria-selected=\"true\"]",self.css)
        self.assertIn(".dil-db-stages",self.css)
        self.assertIn('id="dil-tower-button"',self.html)
    def test_payment_evidence_upload_enabled_but_reconciliation_still_disabled(self):
        nodes=self.parser.by_id
        for name in ("dil-payment-evidence-file","dil-payment-preview",
                     "dil-payment-reconcile"):
            self.assertIn("dil-db-payments",nodes[name]["ancestor_ids"])
        self.assertNotIn("disabled",nodes["dil-payment-evidence-file"]["attributes"])
        self.assertNotIn("disabled",nodes["dil-payment-preview"]["attributes"])
        self.assertIn("disabled",nodes["dil-payment-reconcile"]["attributes"])
        self.assertIn('id="dil-payment-upload-form"',self.html)
        self.assertIn('href="/api/payment-evidence/template"',self.html)
        self.assertIn("Description | SOL ID | Credit Amount",self.html)
        self.assertIn("PAYMNENT worksheet",self.html)
        self.assertIn("Column I (Credit)",self.html)
        self.assertIn("original PAYMNENT worksheet",self.html)
        self.assertIn("no reconciliation has run",self.html)
        self.assertNotIn('fetch("/api/reconcile"',self.html)
    def test_authenticated_dashboard_and_existing_financial_denials(self):
        self.assertEqual(self.client.get("/dashboard").status_code,401)
        user=SimpleNamespace(uid="synthetic",disabled=False,
            email="test@example.invalid",display_name="test",
            custom_claims={"dil_dashboard":True})
        self.client.set_cookie("__Host-dil_session","synthetic",secure=True)
        with patch("dashboard_sessions.firebase_app",return_value=None), \
             patch("dashboard_sessions.auth.verify_session_cookie",
                   return_value={"uid":"synthetic"}), \
             patch("dashboard_sessions.auth.get_user",return_value=user):
            page=self.client.get("/dashboard")
            self.assertEqual(page.status_code,200)
            self.assertIn(b'role="tablist"',page.data)
            self.assertEqual(self.client.get("/dashboard-theme.css").status_code,200)
            for endpoint in ("/api/upload","/api/imports/preview",
                             "/api/payment-reconciliation/run"):
                self.assertEqual(self.client.post(endpoint).status_code,403,endpoint)
            self.assertFalse(self.client.get("/healthz").json["financial_execution_enabled"])
    def test_existing_release_and_persistent_volume_are_preserved(self):
        caddy=(LOGIN/"Caddyfile.board_v2").read_text()
        self.assertIn("reverse_proxy sbi-control-tower-board-v2:8080",caddy)
        self.assertIn("reverse_proxy sbi-preview:8080",caddy)
        self.assertIn("SBI_PRIVATE_WORKSPACE_DB=/data/workspace.sqlite3",
                      (LOGIN/"deploy_board_v2.sh").read_text())
if __name__=="__main__":
    unittest.main()
