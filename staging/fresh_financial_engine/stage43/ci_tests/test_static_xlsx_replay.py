"""Independent GitHub replay of pre-generated *fabricated* XLSX bytes.

All 5 XLSX variants are pre-generated with artifact_tool in a separate isolated
creation runtime, base64-pinned by SHA256 in a text-only source fixture.
This test intentionally DOES NOT import artifact_tool, modify a workbook, or
read real bank records. It executes the actual Stage4.3 OOXML->signed-evidence
->SQLite review code under a standard CPython GitHub runner.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from new_only_adapter import NewSourceBlocked, _xl_snapshot, review_new_only_pair
from stage4_ledger import Principal, Stage4Blocked, Stage4Policy, upload_row_sha256

HERE = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((HERE / 'ci_fixtures/fixture_bundle.json').read_text('utf-8'))
KEY = b'FAKE_TEST_ONLY_32_BYTES_LONG_NEVER_USE_IN_PRODUCTION'
POLICY = Stage4Policy('SBI_INTERNAL_GATEWAY_TEST', '2026-11-21', '2026-11-22', KEY)
UP = Principal('synthetic_up', 'INTAKE')
REVIEWER = Principal('synthetic_reviewer', 'REVIEWER')
ROW = {'Description': 'SYNTHETIC NOVEMBER POSTAGE', 'SOL ID': '0001505', 'Credit Amount': '118.00'}


def signed_tag(body: dict, kind: str) -> str:
    raw = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                     allow_nan=False).encode('utf-8')
    return hmac.new(KEY, b'SBI_STG4_V1:' + kind.encode() + b':' + raw, 'sha256').hexdigest()


def make_evidence(path: Path) -> tuple[dict, dict]:
    digest = sha256(path.read_bytes()).hexdigest()
    bank = {
        'schema': 'SBI_BANK_EVIDENCE_V1', 'issuer': POLICY.issuer,
        'source_kind': 'NEW_ONLY', 'source_sha256': digest, 'source_row': 2,
        'source_column': 'PAYMNENT!I',
        'statement_sha256': sha256(b'FAKE statement').hexdigest(),
        'bank_date': '2026-11-22', 'payment_reference': 'SYNTH-UTR-0001',
        'sol_id': '0001505', 'client_name': 'SYNTHETIC CLIENT',
        'upload_row_sha256': upload_row_sha256(ROW),
        'description': ROW['Description'], 'credit_amount': '118.00',
        'invoice_reference': 'SYNTH-INV-0001', 'service_month': '2026-11',
    }
    invoice = {
        'schema': 'SBI_INVOICE_EVIDENCE_V1', 'issuer': POLICY.issuer,
        'source_kind': 'NEW_ONLY', 'source_sha256': digest, 'source_row': 2,
        'invoice_no': 'SYNTH-INV-0001', 'invoice_date': '2026-11-21',
        'sol_id': '0001505', 'client_name': 'SYNTHETIC CLIENT',
        'service_month': '2026-11', 'taxable': '100.00',
        'cgst': '9.00', 'sgst': '9.00', 'gross': '118.00',
        'paid_marker': '', 'credit_note': False,
    }
    return bank, invoice


class StaticNewXlsxReplay(unittest.TestCase):
    def setUp(self):
        self.assertEqual(PACKAGE['schema'], 'SBI_STAGE43_FABRICATED_XLSX_REPLAY_V1')
        self.assertIs(PACKAGE['contains_real_financial_records'], False)
        self.temp = tempfile.TemporaryDirectory(prefix='SBI_STAGE43_CI_REPLAY_')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.src = self._case('valid')
        self.bank, self.invoice = make_evidence(self.src)

    def _case(self, name: str) -> Path:
        data = PACKAGE['fixtures'][name]
        payload = base64.b64decode(data['xlsx_base64'], validate=True)
        self.assertLess(len(payload), 250_000)
        self.assertEqual(sha256(payload).hexdigest(), data['sha256'],
                         'Fixture bytes changed without authorized digest update')
        src = self.path / 'SYNTHETIC_NEW_SOURCE.xlsx'
        src.write_bytes(payload)
        return src

    def run_review(self, **change):
        params = dict(source_xlsx=self.src, payment_row=ROW,
                      bank_evidence=self.bank, bank_tag=signed_tag(self.bank, 'bank'),
                      invoice_evidence=self.invoice,
                      invoice_tag=signed_tag(self.invoice, 'invoice'),
                      policy=POLICY, uploader=UP, reviewer=REVIEWER)
        params.update(change)
        return review_new_only_pair(**params)

    def _resign_fixture(self, name: str):
        self._case(name)
        self.bank, self.invoice = make_evidence(self.src)

    def test_01_valid_signed_new_source_and_no_financial_writes(self):
        before = self.src.read_bytes()
        result = self.run_review()
        self.assertEqual(self.src.read_bytes(), before)
        self.assertEqual(result['candidate_reservations'], 0)
        self.assertTrue(result['receipt_reviewed'])
        self.assertFalse(result['financial_writes'])
        self.assertFalse(result['production_apply_enabled'])
        self.assertFalse(result['bank_origin_independently_authenticated'])
        self.assertEqual(result['status'], 'SYNTHETIC_NEW_ONLY_SOURCE_REVIEWED_NOT_RECONCILED')
        self.assertEqual(result['legacy_v218_export'], 'BLOCKED_SOURCE_COLUMN_OVERLAP')

    def test_02_workbook_cell_types_zero_padded_sol_and_formula(self):
        tabs, sheets = _xl_snapshot(self.src)
        self.assertEqual(tabs, ('PAYMNENT', 'Invoice Details.'))
        self.assertEqual(sheets['PAYMNENT'][(2, 6)], ('text', '0001505', None))
        self.assertEqual(sheets['Invoice Details.'][(2, 11)][1], 'SYNTH-INV-0001')
        self.assertEqual(sheets['Invoice Details.'][(2, 15)][1], '118')
        self.assertEqual(sheets['PAYMNENT'][(2, 10)][2], 'I2-H2')

    def test_03_nonblank_invoice_paid_marker_numeric_zero_denied(self):
        self._resign_fixture('paid_zero')
        with self.assertRaisesRegex(NewSourceBlocked, 'PAID_MARKER_NONBLANK_INCLUDING_ZERO'):
            self.run_review()

    def test_04_legacy_invoice_col_j_misplacement_denied(self):
        self._resign_fixture('legacy_col_j')
        with self.assertRaisesRegex(NewSourceBlocked, 'INVOICE_INVOICE_NO_SOURCE_CONFLICT'):
            self.run_review()

    def test_05_formula_bank_credit_i_denied(self):
        self._resign_fixture('formula_credit_i')
        with self.assertRaisesRegex(NewSourceBlocked, 'SOURCE_CELL_MISSING_OR_FORMULA_2_9'):
            self.run_review()

    def test_06_unapproved_extra_sheet_denied(self):
        self._resign_fixture('extra_sheet')
        with self.assertRaisesRegex(NewSourceBlocked, 'EXACT_TWO_SOURCE_SHEETS_REQUIRED'):
            self.run_review()

    def test_07_post_signature_workbook_substitution_denied(self):
        self._case('paid_zero')
        with self.assertRaisesRegex(NewSourceBlocked, 'SIGNED_WORKBOOK_SHA256_CONFLICT'):
            self.run_review()

    def test_08_invalid_bank_signature_denied(self):
        with self.assertRaisesRegex(Stage4Blocked, 'ATTESTATION_SIGNATURE_MISMATCH'):
            self.run_review(bank_tag='0' * 64)

    def test_09_invalid_invoice_signature_denied(self):
        with self.assertRaisesRegex(Stage4Blocked, 'ATTESTATION_SIGNATURE_MISMATCH'):
            self.run_review(invoice_tag='0' * 64)

    def test_10_unsigned_payment_amount_conflict_denied(self):
        changed = {**ROW, 'Credit Amount': '119.00'}
        with self.assertRaisesRegex(NewSourceBlocked, 'UPLOAD_ROW_SOURCE_CONFLICT'):
            self.run_review(payment_row=changed)

    def test_11_wrong_resigned_invoice_sol_denied(self):
        changed = {**self.invoice, 'sol_id': '0001506'}
        with self.assertRaisesRegex(NewSourceBlocked, 'INVOICE_SOL_ID_SOURCE_CONFLICT'):
            self.run_review(invoice_evidence=changed, invoice_tag=signed_tag(changed, 'invoice'))

    def test_12_same_actor_for_intake_and_review_denied(self):
        with self.assertRaisesRegex(NewSourceBlocked, 'DISTINCT_TRUSTED_HOST_ROLES_REQUIRED'):
            self.run_review(reviewer=UP)

    def test_13_unapproved_real_source_filename_denied(self):
        path = self.path / 'bank-actual.xlsx'
        path.write_bytes(self.src.read_bytes())
        with self.assertRaisesRegex(NewSourceBlocked, 'SYNTHETIC_TWO_SHEET_FILE_ONLY'):
            self.run_review(source_xlsx=path)

    def test_14_pinned_fixture_has_five_variants(self):
        self.assertEqual(set(PACKAGE['fixtures']), {
            'valid', 'paid_zero', 'legacy_col_j', 'formula_credit_i', 'extra_sheet'
        })
        self.assertEqual(PACKAGE['data_source'], 'ARTIFACT_TOOL_GENERATED_FAKE_ONLY')


if __name__ == '__main__':
    unittest.main()