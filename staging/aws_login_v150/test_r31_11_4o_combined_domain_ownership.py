"""4O completely offline CI tests. AWS/DNS/Firebase/PG/Caddy are mocked."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4o_combined_domain_ownership as o

SHA="a"*40


class DomainOwnerQATests(unittest.TestCase):
    def original(self):
        return json.loads(o.DOSSIER.read_text("utf-8"))

    def variant(self,change):
        doc=self.original()
        change(doc)
        t=tempfile.TemporaryDirectory()
        path=Path(t.name)/"domain_dossier.json"
        path.write_text(json.dumps(doc),encoding="utf-8")
        return t,path

    def test_default_dossier_is_pending_not_approved(self):
        doc,counts=o.read_dossier(o.DOSSIER)
        self.assertEqual(counts,{o.n.PENDING:6,o.n.REFERENCED:0,o.n.REVIEWED:0})
        self.assertEqual(doc["qa_fqdn"],"PENDING")
        self.assertEqual(doc["parent_dns_zone"],"PENDING")
        self.assertEqual(doc["deployment_authorization"],"NOT_GRANTED")
        self.assertEqual(doc["security_position"],o.LOCKED_POSITION)

    def test_bad_fqdn_or_wrong_zone_rejected(self):
        cases=[
            ("qa.example.invalid","example.invalid"),
            ("qa.127.0.0.1.sslip.io","sslip.io"),
            ("qa.example.org","unrelated.org"),
            ("qa.example.org","qa.example.org"),
            ("127.0.0.1","PENDING"),
            ("qa.other.org","PENDING"),
            ("*.example.org","example.org"),
            ("QA.EXAMPLE.ORG","example.org"),
            ("PENDING","example.org"),
        ]
        for hostname,zone in cases:
            with self.subTest(host=hostname,zone=zone):
                t,p=self.variant(lambda d:d.update({
                    "qa_fqdn":hostname,"parent_dns_zone":zone}))
                with t,self.assertRaises(o.OwnershipBlocked):
                    o.read_dossier(p)

    def test_candidate_fqdn_is_syntactic_only_not_authority(self):
        t,p=self.variant(lambda d:d.update({
            "qa_fqdn":"qa.secure.example.org",
            "parent_dns_zone":"example.org",
        }))
        with t:
            doc,counts=o.read_dossier(p)
        self.assertEqual(doc["deployment_authorization"],"NOT_GRANTED")
        self.assertEqual(counts[o.n.PENDING],6)
        # Original 4N intake has NO domain; cannot introduce independent
        # unbacked hostname only in 4O and declare it accepted.
        with self.assertRaises(o.OwnershipBlocked):
            o.correlate_with_4n(doc,o.n.INTAKE)

    def test_no_added_fields_or_release_claims(self):
        changes=[
            lambda d:d.update({"deployment_authorization":"APPROVED"}),
            lambda d:d["security_position"].update({"financial_apply":"ENABLED"}),
            lambda d:d["security_position"].update({"owner_approval_verified":"PASS"}),
            lambda d:d["evidence"][0].update({"state":"APPROVED"}),
            lambda d:d["evidence"][0].update({"evidence_ticket":"SEC-FAKE-123"}),
            lambda d:d["evidence"][0].update({"secret":"password"}),
            lambda d:d["evidence"].pop(),
            lambda d:d["evidence"].reverse(),
            lambda d:d.update({"qa_port":443}),
            lambda d:d.update({"source_4n_intake":"unapproved-intake.json"}),
        ]
        for i,modify in enumerate(changes):
            with self.subTest(case=i):
                t,p=self.variant(modify)
                with t,self.assertRaises(o.OwnershipBlocked):
                    o.read_dossier(p)

    def test_evidence_reference_is_not_owner_approval(self):
        def update(d):
            d["evidence"][0].update({
                "state":o.n.REFERENCED,
                "evidence_ticket":"SEC-DNS-2026-101",
                "evidence_sha256":"b"*64,
            })
        t,p=self.variant(update)
        with t:
            doc,counts=o.read_dossier(p)
        self.assertEqual(counts[o.n.REFERENCED],1)
        with self.assertRaises(o.OwnershipBlocked):
            o.correlate_with_4n(doc,o.n.INTAKE)

    def test_review_metadata_distinct_and_no_future_timestamp(self):
        def review(d):
            d["evidence"][0].update({
                "state":o.n.REVIEWED,
                "evidence_ticket":"SEC-DNS-2026-101",
                "evidence_sha256":"c"*64,
                "independent_review_ticket":"SEC-REVIEW-2026-102",
                "reviewed_at_utc":"2026-11-27T12:00:00Z",
            })
        t,p=self.variant(review)
        with t:
            doc,counts=o.read_dossier(p)
        self.assertEqual(counts[o.n.REVIEWED],1)
        self.assertEqual(doc["security_position"]["owner_approval_verified"],"NOT_VERIFIED")

        def future(d):
            review(d)
            d["evidence"][0]["reviewed_at_utc"]="2099-01-01T00:00:00Z"
        t,p=self.variant(future)
        with t,self.assertRaises(o.OwnershipBlocked):
            o.read_dossier(p)

    def test_symlink_dossier_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"dossier.json"
            target.symlink_to(o.DOSSIER)
            with self.assertRaises(o.OwnershipBlocked):
                o.read_dossier(target)

    def test_all_in_one_mode_invokes_actual_combined_predecessor(self):
        with (
            patch.object(o.n,"run_combined") as previous,
            patch.object(o.g,"caddy_preflight",
                         return_value=o.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(o.g,"check_database_isolation") as db,
            patch.object(o.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as stdout,
        ):
            result=o.main(["--source-sha",SHA])
        self.assertEqual(result,0)
        previous.assert_called_once_with(
            SHA,o.n.INTAKE,o.m.REGISTER,o.k.TEMPLATE_PACKET)
        caddy.assert_called_once()
        db.assert_called_once()
        cleanup.assert_called_once()
        text=stdout.getvalue()
        for receipt in (
            "DB_R31_11_4O_DOMAIN_DOSSIER=PASS_STRICT_SIX_GATES_NO_SECRETS",
            "DB_R31_11_4O_OWNER_EVIDENCE_PENDING=6",
            "DB_R31_11_4O_QA_HOSTNAME=NOT_PROVIDED",
            "DB_R31_11_4O_4N_THROUGH_4H_COMBINED_QA=PASS_READONLY",
            "DB_R31_11_4O_COMBINED_DOMAIN_PREFLIGHT=PASS_PREPARATION_ONLY",
            "DB_R31_11_4O_REAL_DNS_OWNER_VERIFICATION=NOT_PERFORMED",
            "DB_R31_11_4O_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4O_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(receipt,text)

    def test_original_caddy_drift_fails_closed(self):
        with (
            patch.object(o.n,"run_combined"),
            patch.object(o.g,"caddy_preflight",return_value="0"*64),
            patch.object(o.g,"check_database_isolation") as db,
            redirect_stdout(StringIO()) as stdout,
        ):
            result=o.main(["--source-sha",SHA])
        self.assertEqual(result,2)
        db.assert_not_called()
        self.assertIn("DB_R31_11_4O_BLOCK_REASON=DNS_OWNER_CADDY_BASELINE_CHANGED",
                      stdout.getvalue())
        self.assertNotIn("COMBINED_DOMAIN_PREFLIGHT=PASS",stdout.getvalue())

    def test_untrusted_errors_do_not_disclose_cloud_secrets(self):
        with (
            patch.object(o.n,"run_combined",
                         side_effect=RuntimeError("SENSITIVE_FIREBASE_TOKEN_ABC")),
            redirect_stdout(StringIO()) as stdout,
        ):
            self.assertEqual(o.main(["--source-sha",SHA]),2)
        self.assertNotIn("SENSITIVE_FIREBASE_TOKEN_ABC",stdout.getvalue())
        self.assertIn("STOP=DB_R31_11_4O_DOMAIN_EVIDENCE_REVIEW_REQUIRED",
                      stdout.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",stdout.getvalue())


if __name__=="__main__":
    unittest.main()
