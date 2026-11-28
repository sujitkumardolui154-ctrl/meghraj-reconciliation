"""R31.11.4Y only: validate evidence-screen fail-closed behavior without external QA."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("evidence_screen",ROOT/"r31_11_4y_nonsecret_evidence_screen.py")
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class EvidenceIntakeTests(unittest.TestCase):
    def template(self):
        return gate.load(gate.TEMPLATE)

    def test_unapproved_template_is_safe(self):
        self.assertEqual(gate.review(self.template()),0)

    def test_approve_or_unlock_is_rejected(self):
        for key,val in (("release_authorization","GRANTED"),
                        ("financial_apply","ENABLED"),
                        ("production_release","APPROVED"),
                        ("external_acceptance","PASS")):
            with self.subTest(key=key):
                data=self.template()
                data[key]=val
                with self.assertRaises(ValueError):
                    gate.review(data)

    def test_attested_metadata_is_not_approval(self):
        data=self.template()
        item=data["evidence_groups"][0]
        item.update({
            "state":"SUBMITTED_FOR_INDEPENDENT_REVIEW",
            "change_ticket":"QA-CHANGE-100",
            "evidence_reference":"review/ref-100",
            "evidence_sha256":"a"*64,
            "owner_review_ticket":"OWNER-100",
            "independent_security_review_ticket":"SEC-100",
            "reviewed_at_utc":"2026-11-28T14:00:00Z",
        })
        self.assertEqual(gate.review(data),0)
        self.assertEqual(data["release_authorization"],"NOT_GRANTED")

    def test_partial_and_secret_like_metadata_rejected(self):
        for value in ("PENDING","sk-secret-token-value","abc def","-----BEGIN PRIVATE KEY-----"):
            data=self.template()
            item=data["evidence_groups"][0]
            item["state"]="SUBMITTED_FOR_INDEPENDENT_REVIEW"
            item["evidence_reference"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                gate.review(data)

    def test_unsafe_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"reference.json"
            p.symlink_to(gate.TEMPLATE)
            with self.assertRaises(ValueError):
                gate.load(p)

if __name__=="__main__":
    unittest.main()
