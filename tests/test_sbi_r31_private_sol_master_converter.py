"""R31 private SOL XLSX→JSON adapter tests; synthetic master only."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"staging/aws_login_v150/prepare_private_sol_master.py"
spec=importlib.util.spec_from_file_location("r31_master_converter",P)
conv=importlib.util.module_from_spec(spec)
spec.loader.exec_module(conv)


class R31PrivateSOLConverterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/"synthetic-sol-master.xlsx"
        self.dest=Path(self.tmp.name)/"private-approved-sol.json"
        wb=Workbook()
        ws=wb.active
        ws.title="Clean Branch Master"
        ws.append(["Search Aliases","Official Branch Name","SOL ID","Review Flag"])
        ws.append(["","SOUTHERN AVENUE","001505",""])
        ws.append(["","UNIQUE OFFICE","000123",""])
        ws.append(["","ZONAL OFFICE KOLKATA","006884",""])
        ws.append(["","TRANSACTION BANKING HUB","006884",""])
        ws.append(["","FUND KHAGRA","99922",""])
        wb.save(self.source);wb.close()

    def test_01_exact_excel_names_and_conflicting_sol_held(self):
        report=conv.persist(self.source,self.dest)
        self.assertEqual(report["sol_code_count"],4)
        self.assertEqual(report["unambiguous_approved_code_count"],2)
        self.assertEqual(report["review_sol_ids"],["6884","99922"])
        obj=json.loads(self.dest.read_bytes())
        self.assertEqual(obj["schema"],conv.SCHEMA)
        valid=[r for r in obj["branches"] if r["approved"]]
        self.assertEqual({r["sol_id"] for r in valid},{"123","1505"})
        self.assertEqual({r["official_branch_name"] for r in valid},
                         {"UNIQUE OFFICE","SOUTHERN AVENUE"})

    def test_02_sha_pinned_and_private_0600(self):
        report=conv.persist(self.source,self.dest)
        self.assertEqual(report["private_sha256"],
                         hashlib.sha256(self.dest.read_bytes()).hexdigest())
        self.assertEqual(self.dest.stat().st_mode&0o777,0o600)

    def test_03_no_silent_overwrite_of_approved_master(self):
        conv.persist(self.source,self.dest)
        before=self.dest.read_bytes()
        with self.assertRaises(FileExistsError):
            conv.persist(self.source,self.dest)
        self.assertEqual(self.dest.read_bytes(),before)

    def test_04_unknown_input_sheet_refused(self):
        wb=Workbook()
        wb.active.title="WRONG"
        wb.save(self.source);wb.close()
        with self.assertRaises(KeyError):
            conv.prepare(self.source)
        self.assertFalse(self.dest.exists())

    def test_05_padded_sol_key_is_looked_up_without_rewriting_original(self):
        self.assertEqual(conv.normalize_sol("001505"),"1505")
        self.assertEqual(conv.normalize_sol("00001"),"1")
        self.assertIsNone(conv.normalize_sol("00AB"))
        self.assertIsNone(conv.normalize_sol("00000"))


if __name__=="__main__":
    unittest.main()
