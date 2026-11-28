"""Owner-approved Invoice UI v2: cross-month and editable AWB intake tests.

Synthetic records only; no AWS, Firestore, production DB, customer data,
payment reconciliation, or real financial writes.
"""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"dashboard_source"))
from openpyxl import Workbook
from invoice_gst_core import InvoiceError,build_invoice,gst_row
from invoice_annexure_intake import (
    AnnexureImportError,parse_xlsx_annexure,
)

BRANCH={
    "verified":True, "branch_key":"QA-03970",
    "client_name":"QA SMECCC KOLKATA","invoice_branch":"QA KOLKATA",
    "invoice_generate_location":"QA KOLKATA",
    "original_branch_name":"QA SBI SAMPLE","sol_id":"03970",
    "client_class":"SBI_BANK","gstin":"19AAACS8577K3ZK",
    "recipient_title":"QA Manager","customer_address":"QA synthetic",
    "state_code":"19",
}
BASE={
    "invoice_no":"MXP90070", "branch_key":"QA-03970",
    "service_from":"2026-09-01","service_to":"2026-10-31",
    "invoice_date":"2026-11-05",
    "shipments":[
        {"dispatch_date":"2026-09-01","lr_no":"QA-AWB1",
         "packet_ref_no":"","consignee":"QA CONSIGNEE ONE",
         "weight_kg":"0.100","amount":"150.00"},
        {"dispatch_date":"2026-10-31","lr_no":"QA-AWB2",
         "packet_ref_no":"P1","consignee":"QA CONSIGNEE TWO",
         "weight_kg":"0.500","amount":"250.00"},
    ],
}
HEADERS=["Dispatch Date","AWB No","Packet Ref No","Consignee","Weight (kg)","Amount ₹"]


def workbook_bytes(*rows, headers=HEADERS):
    wb=Workbook();ws=wb.active
    ws.append(headers)
    for row in rows:ws.append(row)
    b=BytesIO();wb.save(b);wb.close()
    return b.getvalue()


class InvoiceV2ServicePeriod(unittest.TestCase):
    def test_sept_to_oct_2026_and_correct_totals(self):
        out=build_invoice(BASE,BRANCH)
        self.assertEqual(out["service_month"],"Sept To Oct 2026")
        self.assertEqual(out["service_month_key"],"2026-09")
        self.assertEqual(out["fy"],"2026-2027")
        self.assertEqual(out["invoice_date"],"2026-11-05")
        self.assertTrue(out["multi_month_period"])
        self.assertEqual(out["gst_period_policy"],"MULTI_MONTH_REVIEW_REQUIRED")
        self.assertEqual(out["taxable"],"400.00")
        self.assertEqual((out["cgst"],out["sgst"],out["total"]),
                         ("36.00","36.00","472.00"))
        out["status"]="FINALIZED";out["verification_flags"]=""
        self.assertEqual(gst_row(out)[3],"Sept To Oct 2026")

    def test_dec_to_jan_cross_calendar_year_same_fy(self):
        p=deepcopy(BASE)
        p["service_from"]="2026-12-01";p["service_to"]="2027-01-31"
        p["invoice_date"]="2027-02-07"
        p["shipments"][0]["dispatch_date"]="2026-12-01"
        p["shipments"][1]["dispatch_date"]="2027-01-31"
        self.assertEqual(build_invoice(p,BRANCH)["service_month"],
                         "Dec 2026 To Jan 2027")
        self.assertEqual(build_invoice(p,BRANCH)["fy"],"2026-2027")

    def test_same_month_keeps_full_month_label(self):
        p=deepcopy(BASE)
        p["service_from"]="2026-09-01";p["service_to"]="2026-09-30"
        p["shipments"][1]["dispatch_date"]="2026-09-30"
        o=build_invoice(p,BRANCH)
        self.assertEqual(o["service_month"],"September 2026")
        self.assertFalse(o["multi_month_period"])

    def test_cross_financial_year_and_reverse_period_denied(self):
        p=deepcopy(BASE)
        p["service_from"]="2026-03-01";p["service_to"]="2026-04-30"
        with self.assertRaisesRegex(InvoiceError,"CROSS_FINANCIAL_YEAR_REVIEW_REQUIRED"):
            build_invoice(p,BRANCH)
        p=deepcopy(BASE)
        p["service_from"]="2026-11-01";p["service_to"]="2026-10-31"
        with self.assertRaisesRegex(InvoiceError,"SERVICE_PERIOD_REVIEW_REQUIRED"):
            build_invoice(p,BRANCH)

    def test_selected_only_and_manual_edited_fields(self):
        p=deepcopy(BASE)
        p["shipments"]=p["shipments"][:1]  # unchecked second AWB excluded
        p["shipments"][0]["packet_ref_no"]="EDITED-PACKET"
        p["shipments"][0]["consignee"]="QA EDITED CONSIGNEE"
        p["shipments"][0]["weight_kg"]="0.750"
        p["shipments"][0]["amount"]="177.25"
        o=build_invoice(p,BRANCH)
        self.assertEqual(o["shipment_count"],1)
        self.assertEqual(o["taxable"],"177.25")
        self.assertEqual(o["shipments"][0]["packet_ref_no"],"EDITED-PACKET")
        self.assertEqual(o["shipments"][0]["consignee"],"QA EDITED CONSIGNEE")
        self.assertEqual(o["shipments"][0]["weight_kg"],"0.750")
        self.assertEqual(o["shipments"][0]["amount"],"177.25")

    def test_invalid_selected_awb_still_rejected_server_side(self):
        p=deepcopy(BASE);p["shipments"][0]["amount"]="177.255"
        with self.assertRaisesRegex(InvoiceError,"INVALID_SHIPMENT_AMOUNT"):
            build_invoice(p,BRANCH)
        p=deepcopy(BASE);p["shipments"][0]["dispatch_date"]="2026-08-31"
        with self.assertRaisesRegex(InvoiceError,"DISPATCH_DATE_OUTSIDE_SERVICE_PERIOD"):
            build_invoice(p,BRANCH)
        p=deepcopy(BASE);p["shipments"][0]["weight_kg"]="1000000000.000"
        with self.assertRaisesRegex(InvoiceError,"INVALID_WEIGHT"):
            build_invoice(p,BRANCH)


class InvoiceV2ExcelParsing(unittest.TestCase):
    def test_xlsx_awb_header_float_and_duplicate_review(self):
        raw=workbook_bytes(
            [datetime(2026,9,1),"334371520","","QA CONSIGNEE",0.1,15.0],
            ["31/10/2026","334371521","P-11","QA 2",0.35,125.25],
            ["31/10/2026","334371521","P-11","QA 2",0.35,125.25],
        )
        result=parse_xlsx_annexure(raw)
        self.assertEqual(result["imported_count"],2)
        self.assertEqual(result["duplicate_rows_skipped"],1)
        self.assertEqual(result["shipments"][0]["dispatch_date"],"2026-09-01")
        self.assertEqual(result["shipments"][0]["weight_kg"],"0.100")
        self.assertEqual(result["shipments"][0]["amount"],"15.00")
        self.assertFalse(result["persisted"])
        self.assertFalse(result["financial_writes"])

    def test_unapproved_excel_header_and_formula_blocked(self):
        raw=workbook_bytes(
            ["01/09/2026","334371520","","QA CONSIGNEE",0.1,15.0],
            headers=["Date","AWB No","Packet Ref No","Consignee","Weight","Amount"],
        )
        with self.assertRaisesRegex(AnnexureImportError,"APPROVED_SIX_COLUMN"):
            parse_xlsx_annexure(raw)
        raw=workbook_bytes(
            ["01/09/2026","334371520","","QA CONSIGNEE",0.1,"=1+2"],
        )
        with self.assertRaisesRegex(AnnexureImportError,"EXCEL_FORMULA"):
            parse_xlsx_annexure(raw)

    def test_extra_precision_blank_and_invalid_date_denied(self):
        raw=workbook_bytes(
            ["01/09/2026","334371520","","QA CONSIGNEE",0.1,15.005],
        )
        with self.assertRaisesRegex(AnnexureImportError,"INVALID_AMOUNT_PRECISION"):
            parse_xlsx_annexure(raw)
        raw=workbook_bytes(
            ["31/02/2026","334371520","","QA CONSIGNEE",0.1,15.0],
        )
        with self.assertRaisesRegex(AnnexureImportError,"INVALID_DISPATCH_DATE"):
            parse_xlsx_annexure(raw)

    def test_xlsx_not_persisted_or_used_as_authoritative_branch(self):
        raw=workbook_bytes(
            ["01/09/2026","QA-777","","QA FAKE",0.125,12.45]
        )
        data=parse_xlsx_annexure(raw)
        self.assertNotIn("branch_key",data["shipments"][0])
        self.assertNotIn("client_name",data["shipments"][0])
        self.assertTrue(data["shipments"][0]["lr_no"].startswith("QA-"))
        self.assertFalse(data["persisted"])


if __name__=="__main__":
    unittest.main()
