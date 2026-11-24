"""Synthetic private master CSV and approved GitHub matcher intake tests."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"staging/invoice-gst"))
spec=importlib.util.spec_from_file_location(
    "sbi_load_private_master",
    ROOT/"staging/invoice-gst/load_private_branch_master.py"
)
loader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class VerifiedPrivateMasterIntake(unittest.TestCase):
    def write(self,root,good=True):
        csv=b"Official Branch Name,SOL ID,Search Aliases\nQA VERIFIED KOLKATA BRANCH,03970,QA VK\n"
        evidence=[{
            "official_name":"QA VERIFIED KOLKATA BRANCH","sol_id":"03970",
            "approved":good,"branch_key":"qa-03970",
            "invoice_branch":"KOLKATA",
            "invoice_generate_location":"KOLKATA",
            "customer_address":"QA SYNTHETIC ADDRESS",
            "recipient_title":"AGM","verified_by":"qa-reviewer",
            "client_class":"SBI_BANK","gstin":"19AAACS8577K3ZK"
        }]
        path=root/"master.csv"; path.write_bytes(csv)
        ev=root/"evidence.json"; ev.write_text(json.dumps(evidence))
        h=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        return path,ev,h(path),h(ev)

    def test_fingerprinted_approved_master_accepted_only_for_qa(self):
        with tempfile.TemporaryDirectory() as folder:
            data=self.write(Path(folder))
            result=loader.verified_private_inputs(data[0],data[1],
                master_sha=data[2],evidence_sha=data[3])
            self.assertEqual(result["status"],"READY_FOR_PRIVATE_QA_IMPORT")
            self.assertEqual(result["rows"][0]["sol_id"],"03970")

    def test_tampered_source_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            data=self.write(Path(folder))
            with self.assertRaisesRegex(ValueError,"DIGEST_MISMATCH"):
                loader.verified_private_inputs(data[0],data[1],
                    master_sha="0"*64,evidence_sha=data[3])

    def test_unapproved_private_source_not_importable(self):
        with tempfile.TemporaryDirectory() as folder:
            data=self.write(Path(folder),good=False)
            result=loader.verified_private_inputs(data[0],data[1],
                master_sha=data[2],evidence_sha=data[3])
            self.assertEqual(result["status"],"REVIEW_REQUIRED")
            self.assertEqual(result["rows"],[])
            with self.assertRaisesRegex(ValueError,"NO_DATABASE_WRITE"):
                loader.stage_approved_master_qa("DO_NOT_USE",result)


if __name__=="__main__":
    unittest.main()
