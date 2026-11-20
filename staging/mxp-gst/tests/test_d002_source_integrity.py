"""D-002 offline-only synthetic source integrity regression."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_source_integrity import (
    SourceIntegrityError, verify_file_bytes, verify_batch_identity,
    verify_private_inputs,
)

SOURCE = b"synthetic source invoice file, no real financial data"
MASTER = b"synthetic branch master, no real branch records"
def sha(data):
    return hashlib.sha256(data).hexdigest()

class D002IntegrityTests(unittest.TestCase):
    def test_real_byte_digest_check(self):
        result=verify_file_bytes(SOURCE,sha(SOURCE))
        self.assertEqual(result["sha256"],sha(SOURCE))
        self.assertFalse(result["financial_write_performed"])

    def test_reject_modified_source_bytes(self):
        with self.assertRaisesRegex(SourceIntegrityError,"SOURCE_SHA256_MISMATCH"):
            verify_file_bytes(SOURCE+b"x",sha(SOURCE))

    def test_reject_missing_and_invalid_approved_digest(self):
        for expected in ("",None,"a"*63,"notasha"):
            with self.assertRaises(SourceIntegrityError):
                verify_file_bytes(SOURCE,expected)

    def test_reject_missing_actual_file_bytes(self):
        for data in (None,b"",SOURCE.decode()):
            with self.assertRaises(SourceIntegrityError):
                verify_file_bytes(data,sha(SOURCE))

    def test_exact_complete_invoice_manifest(self):
        result=verify_batch_identity(
            [{"invoice_no":"MXP0001"},{"invoice_no":"MXP0002"}],
            ["MXP0002","MXP0001"])
        self.assertEqual(result["record_count"],2)

    def test_duplicate_in_original_is_denied(self):
        with self.assertRaisesRegex(SourceIntegrityError,"DUPLICATE_ORIGINAL_BATCH"):
            verify_batch_identity([{"invoice_no":"MXP0001"}]*2,["MXP0001"])

    def test_duplicate_in_manifest_is_denied(self):
        with self.assertRaisesRegex(SourceIntegrityError,"DUPLICATE_APPROVED_MANIFEST"):
            verify_batch_identity([{"invoice_no":"MXP0001"}],["MXP0001"]*2)

    def test_missing_and_extra_invoice_denied(self):
        for records in ([{"invoice_no":"MXP0001"}],
                        [{"invoice_no":"MXP0001"},{"invoice_no":"MXP0002"},{"invoice_no":"MXP0003"}]):
            with self.assertRaisesRegex(SourceIntegrityError,"INCOMPLETE_OR_UNEXPECTED"):
                verify_batch_identity(records,["MXP0001","MXP0002"])

    def test_missing_approved_manifest_denied(self):
        with self.assertRaises(SourceIntegrityError):
            verify_batch_identity([],[])

    def test_master_hash_mismatch_denied(self):
        with self.assertRaisesRegex(SourceIntegrityError,"SOURCE_SHA256_MISMATCH"):
            verify_private_inputs(SOURCE,sha(SOURCE),MASTER,sha(b"wrong"),
                                  [{"invoice_no":"MXP0001"}],["MXP0001"])

    def test_combined_precheck_never_claims_value_parity(self):
        out=verify_private_inputs(SOURCE,sha(SOURCE),MASTER,sha(MASTER),
                                  [{"invoice_no":"MXP0001"}],["MXP0001"])
        self.assertEqual(out["status"],"INTEGRITY_PRECHECK_PASS")
        self.assertFalse(out["original_invoice_values_independently_verified"])
        self.assertFalse(out["source_parser_provenance_verified"])
        self.assertFalse(out["approved_for_posting"])
        self.assertFalse(out["financial_write_performed"])

if __name__=="__main__":
    unittest.main()
