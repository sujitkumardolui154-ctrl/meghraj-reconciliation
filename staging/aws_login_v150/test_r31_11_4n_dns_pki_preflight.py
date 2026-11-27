"""R31.11.4N offline tests: no AWS, DNS requests or certificate issuance."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4n_combined_dns_pki_preflight as n


SHA="a"*40


class R3114NOfflineTests(unittest.TestCase):
    def original(self):
        return json.loads(n.INTAKE.read_text("utf-8"))

    def variant(self, change):
        value=self.original()
        change(value)
        tmp=tempfile.TemporaryDirectory()
        path=Path(tmp.name)/"intake.json"
        path.write_text(json.dumps(value),encoding="utf-8")
        return tmp,path

    def test_exact_ten_pending_no_approvals_or_host(self):
        doc,counts=n.validate_intake(n.INTAKE)
        self.assertEqual(len(doc["items"]),10)
        self.assertEqual([item["field"] for item in doc["items"]],list(n.FIELDS))
        self.assertEqual(counts,{n.PENDING:10,n.REFERENCED:0,n.REVIEWED:0})
        self.assertEqual(doc["release_authorization"],"NOT_GRANTED")
        self.assertEqual(doc["qa_hostname"],n.PENDING)
        self.assertEqual(doc["dns_zone"],n.PENDING)

    def test_proposed_hostname_is_unverified_and_never_an_approval(self):
        def update(d):
            d["qa_hostname"]="qa.secure.example.org"
            d["dns_zone"]="example.org"
        tmp,path=self.variant(update)
        with tmp:
            doc,counts=n.validate_intake(path)
            self.assertEqual(doc["qa_hostname"],"qa.secure.example.org")
            self.assertEqual(counts[n.PENDING],10)
            self.assertEqual(doc["release_authorization"],"NOT_GRANTED")

    def test_reject_bad_qa_host_or_unrelated_zone(self):
        bad=[
            ("localhost",n.PENDING),
            ("127.0.0.1",n.PENDING),
            ("qa.example.invalid",n.PENDING),
            ("qa.any.sslip.io",n.PENDING),
            ("qa.example.org","other.org"),
            ("QA.EXAMPLE.ORG","example.org"),
            ("*.qa.example.org","example.org"),
            ("qa.example.org","qa.example.org"),
            ("qa.example.org", "PENDING"),
        ]
        for hostname,zone in bad:
            if hostname=="qa.example.org" and zone=="PENDING":
                continue
            with self.subTest(name=hostname,zone=zone):
                tmp,path=self.variant(lambda d:d.update(
                    {"qa_hostname":hostname,"dns_zone":zone}))
                with tmp,self.assertRaises(n.IntakeBlocked):
                    n.validate_intake(path)

    def test_pending_evidence_cannot_contain_fake_tickets(self):
        tmp,path=self.variant(lambda d:d["items"][0].update({
            "evidence_ticket":"SEC-EVIDENCE-123"}))
        with tmp,self.assertRaises(n.IntakeBlocked):
            n.validate_intake(path)

    def test_referenced_metadata_is_distinct_from_reviewed_approval(self):
        tmp,path=self.variant(lambda d:d["items"][0].update({
            "state":n.REFERENCED,
            "evidence_ticket":"SEC-EVID-2026-101",
            "evidence_sha256":"a"*64,
        }))
        with tmp:
            doc,count=n.validate_intake(path)
            self.assertEqual(count[n.REFERENCED],1)
            self.assertEqual(count[n.PENDING],9)
            self.assertEqual(doc["release_authorization"],"NOT_GRANTED")

    def test_reviewed_metadata_has_distinct_reviewer_no_future_time(self):
        def legitimate(d):
            d["items"][0].update({
                "state":n.REVIEWED,
                "evidence_ticket":"SEC-EVID-2026-101",
                "evidence_sha256":"b"*64,
                "reviewer_ticket":"SEC-REVIEW-2026-201",
                "reviewed_at_utc":"2026-11-27T09:00:00Z",
            })
        tmp,path=self.variant(legitimate)
        with tmp:
            self.assertEqual(n.validate_intake(path)[1][n.REVIEWED],1)
        def future(d):
            legitimate(d)
            d["items"][0]["reviewed_at_utc"]="2099-01-01T00:00:00Z"
        tmp,path=self.variant(future)
        with tmp,self.assertRaises(n.IntakeBlocked):
            n.validate_intake(path)

    def test_unknown_fields_and_privileged_statuses_rejected(self):
        cases=[
            lambda d:d.update({"release_authorization":"GRANTED"}),
            lambda d:d["items"][0].update({"state":"APPROVED"}),
            lambda d:d["items"].pop(),
            lambda d:d["items"].reverse(),
            lambda d:d.update({"unexpected_secret":123}),
            lambda d:d["items"][0].update({"id_token":"secret"}),
            lambda d:d.update({"dns_zone":"example.org"}),
        ]
        for index,change in enumerate(cases):
            with self.subTest(case=index):
                tmp,path=self.variant(change)
                with tmp,self.assertRaises(n.IntakeBlocked):
                    n.validate_intake(path)

    def test_symlink_intake_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"intake.json"
            path.symlink_to(n.INTAKE)
            with self.assertRaises(n.IntakeBlocked):
                n.validate_intake(path)

    def test_source_register_conflict_stops(self):
        incoming=self.original()
        raw=json.loads(n.m.REGISTER.read_text())
        # 4M says evidence exists but 4N remains PENDING: fail-closed.
        raw["entries"][0].update({
            "status":n.m.SUBMITTED,
            "evidence_ticket":"SEC-TEST-2026",
            "evidence_sha256":"f"*64,
        })
        with tempfile.TemporaryDirectory() as d:
            register=Path(d)/"register.json"
            register.write_text(json.dumps(raw))
            with self.assertRaises(n.IntakeBlocked):
                n.check_predecessor_register(incoming,register,n.k.TEMPLATE_PACKET)

    def test_old_4k_packet_claim_does_not_auto_approve(self):
        intake=self.original()
        packet=n.k.read_packet(n.k.TEMPLATE_PACKET)
        packet["fqdn_owner_approved"]=True
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"packet.json"
            path.write_text(json.dumps(packet))
            with self.assertRaises(n.IntakeBlocked):
                n.check_predecessor_register(intake,n.m.REGISTER,path)

    def test_combined_preflight_does_not_execute_dns_pkis_or_finance(self):
        with (
            patch.object(n.m,"combined_preflight") as predecessor,
            patch.object(n.g,"caddy_preflight",
                         return_value=n.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(n.g,"check_database_isolation") as db,
            patch.object(n.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            status=n.main(["--source-sha",SHA])
        self.assertEqual(status,0)
        predecessor.assert_called_once_with(SHA,n.m.REGISTER,n.k.TEMPLATE_PACKET)
        caddy.assert_called_once()
        db.assert_called_once()
        cleanup.assert_called_once()
        result=out.getvalue()
        for must in (
            "DB_R31_11_4N_DNS_PKI_INTAKE_SCHEMA=PASS_EXACT_TEN_FIELDS",
            "DB_R31_11_4N_EVIDENCE_PENDING=10",
            "DB_R31_11_4N_QA_HOSTNAME=NOT_PROVIDED",
            "DB_R31_11_4N_COMBINED_EVIDENCE_PREFLIGHT=PASS_NO_DEPLOY",
            "DB_R31_11_4N_EXTERNAL_HTTPS_MTLS=NOT_TESTED",
            "DB_R31_11_4N_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4N_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(must,result)

    def test_caddy_drift_blocks_and_suppresses_secrets(self):
        with (
            patch.object(n.m,"combined_preflight"),
            patch.object(n.g,"caddy_preflight",return_value="b"*64),
            patch.object(n.g,"check_database_isolation") as db,
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(n.main(["--source-sha",SHA]),2)
        db.assert_not_called()
        self.assertIn("DB_R31_11_4N_BLOCK_REASON=QA_CADDY_FINGERPRINT_DRIFT",
                      out.getvalue())
        with (
            patch.object(n.m,"combined_preflight",
                         side_effect=RuntimeError("PRIVATE_KEY_TOKEN_NOT_FOR_LOGS")),
            redirect_stdout(StringIO()) as out2,
        ):
            self.assertEqual(n.main(["--source-sha",SHA]),2)
        self.assertNotIn("PRIVATE_KEY_TOKEN_NOT_FOR_LOGS",out2.getvalue())


if __name__=="__main__":
    unittest.main()
