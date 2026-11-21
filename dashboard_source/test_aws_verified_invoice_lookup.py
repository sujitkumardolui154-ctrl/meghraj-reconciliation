"""Synthetic only: no real credentials, network, invoice numbers or financial writes."""
import hashlib
import io
import unittest

from openpyxl import load_workbook
from invoice_source_schema import HEADERS_53
from invoice_number_selection import Selection
from bulk_report_selection import build_selection_zip
from bulk_report_excel import combined_excel_from_report_zip
from aws_verified_invoice_lookup import (
    CHUNK, DATASET, SHA, ROOT, VerifiedSourceUnavailable,
    lookup_verified_invoices,
)


def firevalue(v):
    if isinstance(v, bool): return {"booleanValue": v}
    if isinstance(v, int): return {"integerValue": str(v)}
    if isinstance(v, str): return {"stringValue": v}
    if isinstance(v, list): return {"arrayValue": {"values": [firevalue(i) for i in v]}}
    raise TypeError("Unsupported synthetic value")


class FakeResponse:
    def __init__(self, status, data):
        import json
        self.status_code = status
        self._data = data
        self.content = json.dumps(data).encode()
    def json(self):
        return self._data


def snapshot(number, payment="0", balance=True):
    fields = [""] * 53
    fields[12] = number
    fields[20] = payment
    fields[27] = "0"
    types = ["s"] * 53
    return {
        "invoice_no": number,
        "original_values": fields,
        "original_cell_types": types,
        "source_sha256": SHA,
        "original_columns_source_sha256": SHA,
        "source_row": 2,
        "balance_valid": balance,
        "original_headers": HEADERS_53,
    }


class FakeReadSession:
    def __init__(self, rows=(), *, imported=(), metadata_valid=True, status=200):
        self.rows = list(rows)
        self.imported = list(imported)
        self.status = status
        self.closed = False
        self.metadata_valid = metadata_valid
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        assert kwargs.get("allow_redirects") is False
        if url.startswith(ROOT + "/dashboard_import_receipts_v140/"):
            return FakeResponse(404, {})
        assert url == ROOT + "/dashboard_report_datasets/" + DATASET
        m = {
            "source_sha256": SHA,
            "state": "READY" if self.metadata_valid else "PENDING",
            "rows": 14374,
            "original_columns_state": "READY",
            "original_column_count": 53,
            "original_columns_row_count": 14374,
            "original_headers": HEADERS_53,
        }
        return FakeResponse(self.status, {"fields": {k: firevalue(v) for k, v in m.items()}})
    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        assert kwargs.get("allow_redirects") is False
        query = kwargs["json"]["structuredQuery"]
        collection = query["from"][0]["collectionId"]
        if collection == "dashboard_invoice_rows_v140":
            where=query["where"]["fieldFilter"]
            requested={v["stringValue"] for v in where["value"]["arrayValue"]["values"]}
            rows=[]
            for n, row in enumerate(self.imported, 1):
                if row["invoice_no"] in requested:
                    name=(ROOT.removeprefix("https://firestore.googleapis.com/v1/")
                          + "/dashboard_invoice_rows_v140/import-" + str(n))
                    rows.append({"document": {
                        "name": name,
                        "fields": {k: firevalue(v) for k,v in row.items()}
                    }})
            return FakeResponse(200,rows)
        assert collection == "rows"
        assert url == ROOT + "/dashboard_report_datasets/" + DATASET + ":runQuery"
        where = query["where"]["fieldFilter"]
        assert where["field"]["fieldPath"] == "invoice_no"
        assert where["op"] == "IN"
        requested = {v["stringValue"] for v in where["value"]["arrayValue"]["values"]}
        assert 1 <= len(requested) <= CHUNK
        rows = []
        for n, row in enumerate(self.rows, 1):
            if row["invoice_no"] in requested:
                name = (ROOT.removeprefix("https://firestore.googleapis.com/v1/")
                        + "/dashboard_report_datasets/" + DATASET + "/rows/" + str(n))
                rows.append({"document": {
                    "name": name,
                    "fields": {k: firevalue(v) for k, v in row.items()},
                }})
        return FakeResponse(self.status, rows)
    def close(self): self.closed = True


class AWSReadOnlyInvoiceLookupTests(unittest.TestCase):
    def test_exact_random_order_complete_53_columns(self):
        s = FakeReadSession([
            snapshot("TEST-A", "0"),
            snapshot("TEST-B", "118", False),
        ])
        result = lookup_verified_invoices(["TEST-B", "TEST-C", "TEST-A"], session=s)
        self.assertEqual([r["invoice_no"] for r in result["matches"]],
                         ["TEST-B", "TEST-A"])
        self.assertEqual(result["matches"][0]["payment_kind"], "ok")
        self.assertTrue(result["matches"][0]["balance_review"])
        self.assertEqual(result["matches"][1]["payment_kind"], "unpaid")
        self.assertEqual(result["review"][0]["reason"],
                         "NOT_FOUND_IN_VERIFIED_REPORT_SOURCE")
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(len(result["matches"][0]["values"]), 53)
        self.assertTrue(all(x[0] in ("GET","POST") for x in s.calls))
        upload_sha=hashlib.sha256(b"synthetic").hexdigest()
        selection=Selection(("TEST-B", "TEST-C", "TEST-A"), ())
        zipdata, manifest=build_selection_zip(selection, result, upload_sha)
        self.assertEqual(manifest["counts"]["matched"], 2)
        workbook=load_workbook(io.BytesIO(combined_excel_from_report_zip(zipdata)),
                               read_only=True, data_only=False)
        try:
            self.assertEqual(workbook["All Invoices"].cell(2,13).value,"TEST-B")
            self.assertEqual(workbook["All Invoices"].cell(3,13).value,"TEST-A")
            self.assertEqual(workbook["Lookup Review"].cell(2,1).value,"TEST-C")
        finally:
            workbook.close()

    def test_conflict_never_silently_chosen(self):
        s=FakeReadSession([snapshot("TEST-A"),snapshot("TEST-A")])
        r=lookup_verified_invoices(["TEST-A"],session=s)
        self.assertEqual(r["matched_count"], 0)
        self.assertEqual(r["review"][0]["reason"],
                         "DUPLICATE_DATABASE_INVOICE_MATCH")

    def test_corrupted_row_goes_to_review(self):
        bad=snapshot("TEST-A")
        bad["original_values"][12]="TEST-WRONG"
        r=lookup_verified_invoices(["TEST-A"],session=FakeReadSession([bad]))
        self.assertEqual(r["matches"],[])
        self.assertEqual(r["review"][0]["reason"],"DATABASE_SOURCE_CONFLICT")

    def test_metadata_not_ready_stops_report(self):
        with self.assertRaises(VerifiedSourceUnavailable):
            lookup_verified_invoices(["TEST-A"],session=FakeReadSession(
                [snapshot("TEST-A")],metadata_valid=False))

    def test_firestore_http_error_stops_report(self):
        with self.assertRaises(VerifiedSourceUnavailable):
            lookup_verified_invoices(["TEST-A"],session=FakeReadSession(
                status=403))

    def test_duplicate_uploaded_selection_rejected(self):
        with self.assertRaises(ValueError):
            lookup_verified_invoices(["TEST-A","TEST-A"],session=FakeReadSession())

    def test_formula_like_payment_is_review_not_payment(self):
        bad=snapshot("TEST-A", "=2+2")
        r=lookup_verified_invoices(["TEST-A"],session=FakeReadSession([bad]))
        self.assertEqual(r["matches"][0]["payment_kind"],"error-value")

    def test_imported_row_without_completed_receipt_is_not_accepted(self):
        # An imported invoice with no COMPLETED receipt must be reviewed.
        row=snapshot("TEST-IMPORT")
        row.update({
            "import_receipt": "b"*32,
            "source_sha256": "a"*64,
            "source_sheet": "TEST",
            "finance_processed": False,
        })
        s=FakeReadSession(imported=[row])
        r=lookup_verified_invoices(["TEST-IMPORT"],session=s)
        self.assertEqual(r["matched_count"],0)
        self.assertEqual(r["review"][0]["reason"],
                         "DATABASE_SOURCE_CONFLICT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
