"""Source-only Stage 4.2 combined gate; runnable without artifact_tool."""
from pathlib import Path
import ast
import hashlib
import json
import unittest

ROOT=Path(__file__).resolve().parents[2]
STAGE42=ROOT/'stage42'
MANIFEST=STAGE42/'references/V218_OUTPUT_HEADER_LOCK_MANIFEST.json'

class SourceOnlyCombinedGate(unittest.TestCase):
    def test_01_exact_legacy_manifest_pinned(self):
        self.assertEqual(hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                         '1cd0ee356dba943b0a0d40f7d5679f17127627e148b01e5c714a8ebfc3f7b04e')
        m=json.loads(MANIFEST.read_text())
        self.assertEqual(m['rule_id'],'OUT-SCHEMA-V218-001')
        self.assertEqual(len(m['sheets']),9)

    def test_02_source_columns_cannot_be_inferred_from_newer_variant(self):
        m=json.loads(MANIFEST.read_text())
        self.assertEqual(m['headers']['Invoice Details.']['10'],'Invoice No')
        self.assertEqual(m['headers']['PAYMNENT']['9'],'Credit')
        self.assertTrue(m['model_layout']['PAYMNENT'].startswith('M:W, exact eleven header labels and order'))

    def test_03_combined_review_requires_source_hash_and_no_reservation(self):
        src=(STAGE42/'combined_review.py').read_text()
        ast.parse(src)
        self.assertIn('SIGNED_SOURCE_FILE_SHA_MISMATCH',src)
        self.assertIn('UNAPPROVED_V218_SOURCE_LAYOUT',src)
        self.assertIn("status['counts']['reservations'] == 0",src)
        self.assertIn("'payment_model_status':'SUSPENSE'",src)
        self.assertIn("'production_apply_enabled':False",src)

    def test_04_reused_ledger_does_not_expose_apply_method(self):
        root=ast.parse((ROOT/'stage4/stage4_ledger.py').read_text())
        ledger=next(n for n in root.body if isinstance(n,ast.ClassDef) and n.name=='NewOnlyCandidateLedger')
        methods={n.name for n in ledger.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertIn('review_bank',methods)
        self.assertIn('reserve_candidate',methods)
        self.assertNotIn('apply_financial_payment',methods)
        self.assertNotIn('settle_payment',methods)
        self.assertNotIn('reconcile_real_bank',methods)

    def test_05_reused_writer_restricts_status_and_original_columns(self):
        src=(ROOT/'stage41/v218_writer.py').read_text()
        ast.parse(src)
        for x in ('REVIEW_ONLY_STATUS_MUST_BE_SUSPENSE',
                  'PROTECTED_SOURCE_TYPE_VALUE_OR_FORMULA_CHANGED',
                  'OUTPUT_SHEET_ORDER_CHANGED','PAYMENT_MODEL_TEXT_SOL_CORRUPTED'):
            self.assertIn(x,src)

if __name__=='__main__':unittest.main()
