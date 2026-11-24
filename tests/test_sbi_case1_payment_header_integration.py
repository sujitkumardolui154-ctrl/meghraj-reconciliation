"""Case 1: end-to-end read-only SBI real-schema importer with synthetic files."""
from __future__ import annotations
from hashlib import sha256
import sys,unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
from test_sbi_r266_readonly_real_source_population_gate import (
    workbook,cell,
)
from test_sbi_r267_readonly_real_source_adapter import invoice,tiny_master
from sbi_r266_readonly_real_source_population_gate import scan_readonly_source,R266Refusal
from sbi_r267_readonly_real_source_adapter import read_private_snapshots
from sbi_r267_readonly_real_candidate_engine import plan_review_only


def bank_header(credit_col="I", approved=False, marker_col="K"):
    if approved:
        pairs=(("A","Description"),("B","Posting Date"),
               ("C","Service Period"),("D","Bank Reference / UTR"),
               ("E","Bank / Statement Source"),("F","SOL ID"),
               ("G","Client Name"),("H","Debit"),("I","Credit"),
               ("J","Balance"),("K","Record For Me"))
    else:
        pairs=(("A","Location"),("B","Branch Name"),("C","Txn Date"),
               ("D","Value Date"),("E","Description"),
               ("F","Branch Code"),("G","Name"),(credit_col,"Credit"),
               ("J","Balance"),(marker_col,"Record For Me"))
    return "".join(cell(col+"1",val) for col,val in pairs)


def bank_row(credit_col="I", approved=False, marker_col="K", marker=None):
    if approved:
        pairs=(("A","POSTAGE MXP10001 SEPTEMBER 2026"),
               ("B","2026-09-15"),("C","2026-09"),("D","SYNTHETIC-UTR-01"),
               ("E","SYNTHETIC-BANK"),("F","0001"),
               ("G","SYNTHETIC ALPHA"),("I",1160),
               ("K",marker))
    else:
        pairs=(("C","2026-09-15"),
               ("E","POSTAGE MXP10001 SEPTEMBER 2026"),
               ("F","0001"),("G","SYNTHETIC ALPHA"),
               (credit_col,1160),(marker_col,marker))
    return '<row r="2">' + ''.join(cell(col+"2",val) for col,val in pairs) + '</row>'


def source(**kw):
    return workbook(invoice_rows=[invoice()],
                    bank_rows=[bank_row(**kw)],
                    payment_header=bank_header(
                        credit_col=kw.get("credit_col","I"),
                        approved=kw.get("approved",False),
                        marker_col=kw.get("marker_col","K")))


def intake(data):
    master=tiny_master()
    return read_private_snapshots(
        data,master,source_sha256=sha256(data).hexdigest(),
        master_sha256=sha256(master).hexdigest(),
    )


class Case1FreshHeaderEndToEnd(unittest.TestCase):
    def test_01_legacy_I_bank_source_credit_read(self):
        d=source()
        r=scan_readonly_source(d,expected_sha256=sha256(d).hexdigest())
        self.assertEqual(r["positive_bank_credit_rounded_sum"],"1160.00")
        self.assertEqual(r["payment_header_normalization"]["source_to_approved_columns"][8],
                         ("Credit",9))
    def test_02_legacy_H_bank_source_credit_read(self):
        d=source(credit_col="H")
        r=scan_readonly_source(d,expected_sha256=sha256(d).hexdigest())
        self.assertEqual(r["positive_bank_credit_rounded_sum"],"1160.00")
        self.assertEqual(r["payment_header_normalization"]["source_to_approved_columns"][8],
                         ("Credit",8))
    def test_03_approved_payment_A_description_I_credit(self):
        d=source(approved=True)
        r=scan_readonly_source(d,expected_sha256=sha256(d).hexdigest())
        self.assertEqual(r["positive_bank_credit_rounded_sum"],"1160.00")
        self.assertEqual(r["payment_header_normalization"]["source_to_approved_columns"][0],
                         ("Description",1))
    def test_04_importer_reads_historical_I_credit(self):
        d=source()
        s=intake(d)
        self.assertEqual(len(s.payments),1)
        self.assertEqual(s.payments[0].credit,"1160.00")
    def test_05_importer_reads_moved_H_credit(self):
        d=source(credit_col="H")
        s=intake(d)
        self.assertEqual(len(s.payments),1)
        self.assertEqual(s.payments[0].credit,"1160.00")
    def test_06_importer_reads_approved_A_description(self):
        d=source(approved=True)
        s=intake(d)
        self.assertEqual(s.payments[0].description,
                         "POSTAGE MXP10001 SEPTEMBER 2026")
    def test_07_importer_reads_original_E_description(self):
        d=source()
        s=intake(d)
        self.assertEqual(s.payments[0].description,
                         "POSTAGE MXP10001 SEPTEMBER 2026")
    def test_08_importer_uses_B_date_when_approved(self):
        d=source(approved=True)
        s=intake(d)
        self.assertEqual(s.payments[0].bank_date.isoformat(),"2026-09-15")
    def test_09_importer_uses_C_Txn_Date_when_legacy(self):
        d=source()
        s=intake(d)
        self.assertEqual(s.payments[0].bank_date.isoformat(),"2026-09-15")
    def test_10_approved_service_period_if_consistent(self):
        d=source(approved=True)
        s=intake(d)
        self.assertEqual(s.payments[0].service_periods,("2026-09",))
    def test_11_legacy_service_period_parsed_from_narration(self):
        d=source()
        s=intake(d)
        self.assertEqual(s.payments[0].service_periods,("2026-09",))
    def test_12_moved_Record_For_Me_to_L_used(self):
        d=source(marker_col="L",marker="OK")
        s=intake(d)
        self.assertEqual(s.payments[0].original_k,"OK")
    def test_13_original_K_OK_protected(self):
        d=source(marker="OK")
        s=intake(d)
        self.assertEqual(s.payments[0].original_k,"OK")
    def test_14_approved_layout_source_matches_review_candidate(self):
        d=source(approved=True)
        s=intake(d)
        r=plan_review_only(list(s.invoices),list(s.payments),
            list(s.master_pairs),source_sha256=s.source_sha256,
            master_sha256=s.master_sha256)
        self.assertEqual(len(r["candidate_rows"]),1)
        self.assertTrue(r["financial_apply_locked"])
    def test_15_H_credit_variant_matches_same_review_candidate(self):
        d=source(credit_col="H")
        s=intake(d)
        r=plan_review_only(list(s.invoices),list(s.payments),
            list(s.master_pairs),source_sha256=s.source_sha256,
            master_sha256=s.master_sha256)
        self.assertEqual(len(r["candidate_rows"]),1)
        self.assertEqual(r["candidate_rows"][0][2],"1160.00")
    def test_16_raw_input_bytes_not_changed(self):
        d=source(credit_col="H")
        before=sha256(d).hexdigest()
        intake(d)
        self.assertEqual(sha256(d).hexdigest(),before)
    def test_17_no_historical_population_parity(self):
        d=source(approved=True)
        s=intake(d)
        self.assertEqual(s.source_preflight["invoice_data_rows"],1)
        self.assertEqual(s.source_preflight["payment_data_rows"],1)
        self.assertFalse(s.source_preflight["historical_OK_status_copy_authorized"])
    def test_18_real_finance_still_locked_after_mapping(self):
        d=source(approved=True)
        s=intake(d)
        self.assertFalse(s.source_preflight["complete_master_v251_matrix_v239_certified"])
        self.assertEqual(s.source_preflight["production_database_writes"],0)


if __name__=="__main__":unittest.main()
