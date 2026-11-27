"""R31.11.4M no-AWS regression: evidence provenance is NOT authorization."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4m_combined_evidence_preflight as m

SHA="a"*40


class EvidenceAuditTests(unittest.TestCase):
    def original(self):
        return json.loads(m.REGISTER.read_text("utf-8"))

    def variant(self, mutate):
        doc=self.original()
        mutate(doc)
        tmp=tempfile.TemporaryDirectory()
        path=Path(tmp.name)/"evidence.json"
        path.write_text(json.dumps(doc),encoding="utf-8")
        return tmp,path

    def test_default_register_contains_exactly_23_pending(self):
        totals=m.read_register(m.REGISTER)
        self.assertEqual(totals,{m.PENDING:23,m.SUBMITTED:0,m.REVIEWED:0})
        self.assertEqual(m.EXPECTED_FIELDS,
                         tuple(m.k.APPROVAL_FIELDS)+tuple(m.k.TEXT_FIELDS))

    def test_submitted_evidence_metadata_is_not_approval(self):
        def add(d):
            d["entries"][0].update({
                "status":m.SUBMITTED,
                "evidence_ticket":"SEC-2026-001",
                "evidence_sha256":"a"*64,
            })
        tmp,path=self.variant(add)
        with tmp:
            self.assertEqual(m.read_register(path),
                             {m.PENDING:22,m.SUBMITTED:1,m.REVIEWED:0})

    def test_metadata_review_alone_never_grants_deployment(self):
        def add(d):
            d["entries"][0].update({
                "status":m.REVIEWED,
                "evidence_ticket":"SEC-EVIDENCE-101",
                "evidence_sha256":"b"*64,
                "review_ticket":"SEC-REVIEW-102",
                "reviewed_at_utc":"2026-11-27T12:00:00Z",
            })
        tmp,path=self.variant(add)
        with tmp:
            self.assertEqual(m.read_register(path),
                             {m.PENDING:22,m.SUBMITTED:0,m.REVIEWED:1})

    def test_rejects_unsupported_claims_forged_approvals_and_secret_strings(self):
        cases=[
            lambda d:d.update({"release_authorization":"GRANTED"}),
            lambda d:d["entries"].pop(),
            lambda d:d["entries"].reverse(),
            lambda d:d["entries"][0].update({"status":"APPROVED"}),
            lambda d:d["entries"][0].update({"evidence_ticket":"SEC-001"}),
            lambda d:d["entries"][0].update({"status":m.SUBMITTED,
                                              "evidence_ticket":"PASSWORD_SECRET",
                                              "evidence_sha256":"b"*64}),
            lambda d:d["entries"][0].update({"status":m.SUBMITTED,
                                              "evidence_ticket":"SEC-REF-123",
                                              "evidence_sha256":"0"*63}),
            lambda d:d["entries"][0].update({"status":m.REVIEWED,
                                              "evidence_ticket":"SEC-REF-123",
                                              "evidence_sha256":"1"*64,
                                              "review_ticket":"SEC-REF-123",
                                              "reviewed_at_utc":"2026-11-27T12:00:00Z"}),
            lambda d:d["entries"][0].update({"status":m.REVIEWED,
                                              "evidence_ticket":"SEC-REF-123",
                                              "evidence_sha256":"1"*64,
                                              "review_ticket":"SEC-REV-123",
                                              "reviewed_at_utc":"2030-90-90T00:00:00Z"}),
            lambda d:d["entries"][0].update({"personal_email":"no"}),
        ]
        for n,change in enumerate(cases):
            with self.subTest(case=n):
                tmp,p=self.variant(change)
                with tmp,self.assertRaises(m.EvidenceBlocked):
                    m.read_register(p)

    def test_reject_symlink_evidence_register(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"evidence.json"
            path.symlink_to(m.REGISTER)
            with self.assertRaises(m.EvidenceBlocked):
                m.read_register(path)

    def test_all_in_one_audit_never_mutates_caddy_db_or_finance(self):
        with (
            patch.object(m.l,"combined_audit") as predecessor,
            patch.object(m.l,"inspect_design") as design,
            patch.object(m.g,"caddy_preflight",
                         return_value=m.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(m.g,"check_database_isolation") as pg,
            patch.object(m.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as output,
        ):
            result=m.main(["--source-sha",SHA])
        self.assertEqual(result,0)
        predecessor.assert_called_once_with(SHA,m.k.TEMPLATE_PACKET)
        design.assert_called_once()
        caddy.assert_called_once()
        pg.assert_called_once()
        cleanup.assert_called_once()
        out=output.getvalue()
        self.assertIn("DB_R31_11_4M_EVIDENCE_PENDING=23",out)
        self.assertIn("DB_R31_11_4M_COMBINED_EVIDENCE_PREFLIGHT=PASS_READONLY_NO_DEPLOY",out)
        self.assertIn("DB_R31_11_4M_EXTERNAL_MTLS_HTTPS=NOT_TESTED",out)
        self.assertIn("DB_R31_11_4M_FINANCIAL_APPLY=LOCKED",out)
        self.assertIn("DB_R31_11_4M_PRODUCTION_RELEASE=BLOCKED",out)

    def test_4k_packet_claim_of_approval_requires_separate_review(self):
        packet=m.k.read_packet(m.k.TEMPLATE_PACKET)
        packet["fqdn_owner_approved"]=True
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"packet.json"
            path.write_text(json.dumps(packet),encoding="utf-8")
            with (redirect_stdout(StringIO()),
                  self.assertRaises(m.EvidenceBlocked)):
                m.verify_packet_consistency(path,{m.PENDING:23,m.SUBMITTED:0,m.REVIEWED:0})

    def test_caddy_hash_mismatch_stops_before_financial_or_db_changes(self):
        with (
            patch.object(m.l,"combined_audit"),
            patch.object(m.l,"inspect_design"),
            patch.object(m.g,"caddy_preflight",return_value="f"*64),
            patch.object(m.g,"check_database_isolation") as pg,
            redirect_stdout(StringIO()) as output,
        ):
            rc=m.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        pg.assert_not_called()
        self.assertIn("DB_R31_11_4M_BLOCK_REASON=CADDY_FINGERPRINT_CHANGED",
                      output.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",output.getvalue())

    def test_sensitive_errors_not_exposed(self):
        with (patch.object(m.l,"combined_audit",
                           side_effect=RuntimeError("PASSWORD_AND_COOKIE_VALUE")),
              redirect_stdout(StringIO()) as output):
            rc=m.main(["--source-sha",SHA])
        self.assertEqual(rc,2)
        self.assertNotIn("PASSWORD_AND_COOKIE_VALUE",output.getvalue())
        self.assertIn("STOP=DB_R31_11_4M_EVIDENCE_AUDIT_REVIEW_REQUIRED",
                      output.getvalue())

if __name__=="__main__":
    unittest.main()
