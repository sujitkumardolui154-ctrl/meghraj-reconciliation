"""Runner-independent v2.18 schema checks (no artifact_tool import needed)."""
from pathlib import Path
import ast
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
MAN=json.loads((ROOT/'references'/'V218_OUTPUT_HEADER_LOCK_MANIFEST.json').read_text('utf-8'))
WRITER=(ROOT/'v218_writer.py').read_text('utf-8')

class TestV218LockedSchema(unittest.TestCase):
    def test_original_manifest_id(self):
        self.assertEqual(MAN['rule_id'],'OUT-SCHEMA-V218-001')
    def test_payment_layout(self):
        self.assertEqual(MAN['model_layout']['PAYMNENT'].split(',')[0],'M:W')
        self.assertEqual([int(k) for k in MAN['headers']['PAYMNENT'] if int(k)>=13],list(range(13,24)))
        self.assertEqual(MAN['headers']['PAYMNENT']['12'],'')
        self.assertEqual(MAN['headers']['PAYMNENT']['13'],'Model Reconciliation Status')
    def test_invoice_layout(self):
        self.assertEqual([int(k) for k in MAN['headers']['Invoice Details.'] if int(k)>=35],list(range(35,40)))
        self.assertEqual(MAN['headers']['Invoice Details.']['35'],'Model SOL ID')
    def test_schema_status_categories(self):
        self.assertEqual(MAN['status_enum'],['OK','SUSPENSE','Duplicate Payment'])
        self.assertIn('SUSPENSE',WRITER)
    def test_no_financial_writes_or_openpyxl(self):
        module=ast.parse(WRITER)
        imports=set()
        for node in ast.walk(module):
            if isinstance(node,ast.Import):imports.update(alias.name for alias in node.names)
            if isinstance(node,ast.ImportFrom):imports.add(node.module or '')
        self.assertIn('artifact_tool',imports)
        self.assertFalse(any(x.startswith(('openpyxl','firebase_admin','psycopg','requests','boto3')) for x in imports))
        self.assertNotIn('def apply_financial',WRITER)

if __name__=='__main__':unittest.main()