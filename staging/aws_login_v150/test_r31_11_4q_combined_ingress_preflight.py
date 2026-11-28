"""R31.11.4Q offline strict policy and combined private QA regression suite.

All Docker/Firebase/PG/Caddy interactions are mocked in CI. This test
validates a candidate *design*, not deployed proxy behavior.
"""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import r31_11_4q_combined_ingress_preflight as q

SHA="a"*40


class IngressPolicyTests(unittest.TestCase):

    def doc(self):
        return json.loads(q.FILE.read_text("utf-8"))

    def changed(self,modify):
        doc=self.doc()
        modify(doc)
        temp=tempfile.TemporaryDirectory()
        path=Path(temp.name)/"policy.json"
        path.write_text(json.dumps(doc),encoding="utf-8")
        return temp,path

    def test_policy_exact_methods_routes_approval_and_log_safety(self):
        with redirect_stdout(StringIO()) as out:
            policy=q.validate_design()
        self.assertEqual(len(policy["controls"]),14)
        self.assertEqual(len(policy["routes"]),5)
        self.assertEqual(len(policy["forbidden_prefixes"]),9)
        self.assertEqual(len(policy["rollback"]),9)
        self.assertEqual(len(policy["linked_approval_requirements"]),13)
        self.assertEqual(policy["financial_apply"],"LOCKED")
        self.assertEqual(policy["acceptance"]["external_case_count"],22)
        self.assertIn("INGRESS_POLICY=PASS_NONDEPLOYABLE_14_GATES",out.getvalue())

    def test_permission_expansion_and_status_claims_fail_closed(self):
        changes=[
            lambda d:d.update({"deployment_authorization":"GRANTED"}),
            lambda d:d["topology"].update({"tls_listener":"DEPLOYED"}),
            lambda d:d["topology"].update({"qa_proxy_docker_socket":"ALLOWED"}),
            lambda d:d["topology"].update({"qa_proxy_direct_postgres":"ALLOWED"}),
            lambda d:d["topology"].update({"qa_proxy_production_financial_network":"ALLOWED"}),
            lambda d:d["controls"][0].update({"status":"ACCEPTED"}),
            lambda d:d["routes"].append({
                "method":"POST","path":"/api/payment-evidence",
                "auth_gate":"MTLS_ONLY","status":"PROPOSED_NOT_EXPOSED"}),
            lambda d:d["routes"][3].update({"auth_gate":"MTLS_ONLY"}),
            lambda d:d["routes"][2].update({"method":"GET"}),
            lambda d:d["forbidden_prefixes"].remove("/api/gst"),
            lambda d:d["logging_policy"]["permitted_fields"].append("Cookie"),
            lambda d:d["logging_policy"]["status"].__class__,
            lambda d:d["rollback"][0].update({"status":"EXECUTED"}),
            lambda d:d["linked_approval_requirements"][0].update({"status":"APPROVED"}),
            lambda d:d["acceptance"].update({"actual_remote_mtls":"PASS"}),
            lambda d:d.update({"financial_apply":"ENABLED"}),
            lambda d:d.update({"production_release":"APPROVED"}),
            lambda d:d.update({"secrets":"FIREBASE_PASSWORD"}),
        ]
        for index,change in enumerate(changes):
            if index==11:
                continue  # simple no-op is not a policy mutation
            with self.subTest(index=index):
                temp,path=self.changed(change)
                with temp,self.assertRaises(q.IngressBlocked):
                    q.validate_design(path)

    def test_untracked_symlink_policy_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"policy.json"
            path.symlink_to(q.FILE)
            with self.assertRaises(q.IngressBlocked):
                q.validate_design(path)

    def valid(self,method="GET",path="/healthz",**overrides):
        values={
            "method":method,"path":path,
            "client_cert_verified":True,
            "peer_ip_in_approved_range":True,
            "sni_host_match":True,
            "identity_headers_absent":True,
            "firebase_session_valid":False,
            "origin_and_csrf_valid":False,
        }
        values.update(overrides)
        return values

    def test_exact_five_allowed_route_shapes_with_synthetic_prerequisites(self):
        for route in q.ROUTES:
            attrs={}
            if route["auth_gate"]=="MTLS_FIREBASE_SESSION_REQUIRED":
                attrs["firebase_session_valid"]=True
            if route["auth_gate"]=="MTLS_ORIGIN_CSRF_REQUIRED":
                attrs["origin_and_csrf_valid"]=True
            with self.subTest(route=route):
                self.assertTrue(q.allow_synthetic_request(
                    self.valid(route["method"],route["path"],**attrs)))

    def test_unauthorized_routes_forged_headers_and_auth_fail(self):
        routes=[
            ("POST","/healthz"),("HEAD","/healthz"),
            ("GET","/api/gst"),("GET","/admin"),
            ("POST","/api/payment-evidence"),
            ("GET","/auth/*"),("GET","/auth//csrf"),
            ("GET","/auth/%63srf"),("GET","/auth/csrf/"),
            ("GET","/api/r31-private-qa/tenant-rls-source-r3114"),
            ("POST","/auth/session"),
        ]
        for method,path in routes:
            with self.subTest(method=method,path=path):
                self.assertFalse(q.allow_synthetic_request(self.valid(method,path)))
        for field in (
           "client_cert_verified","peer_ip_in_approved_range",
           "sni_host_match","identity_headers_absent"
        ):
            with self.subTest(field=field):
                self.assertFalse(q.allow_synthetic_request(self.valid(**{field:False})))
        self.assertFalse(q.allow_synthetic_request(
            self.valid("GET","/auth/me",firebase_session_valid=False)))
        self.assertFalse(q.allow_synthetic_request(
            self.valid("POST","/auth/session",
                       origin_and_csrf_valid=False,client_cert_verified=True)))
        self.assertFalse(q.allow_synthetic_request(self.valid(client_cert_verified=1)))
        self.assertFalse(q.allow_synthetic_request(dict(self.valid(),uid="forged")))
        with redirect_stdout(StringIO()) as out:
            q.simulate()
        self.assertIn("PASS_FIVE_ALLOW_FIFTEEN_DENY",out.getvalue())
        self.assertIn("REAL_HTTP_PROXY=NOT_DEPLOYED",out.getvalue())

    def test_packet_and_register_must_remain_pending(self):
        with redirect_stdout(StringIO()) as out:
            q.check_approvals()
        self.assertIn("13_OF_13_PENDING_WITHIN_23",out.getvalue())
        self.assertIn("23_OF_23_PENDING",out.getvalue())
        original=q.k.read_packet(q.k.TEMPLATE_PACKET)
        original["qa_proxy_config_peer_reviewed"]=True
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"fake.json"
            p.write_text(json.dumps(original),encoding="utf-8")
            with self.assertRaises(q.IngressBlocked):
                q.check_approvals(packet_path=p)

    def fake_caddy(self, *, qa_network=False, socket_mount=False):
        networks={"aws_lightsail_private_web":{}}
        if qa_network:
            networks[q.g.QA_NETWORK]={}
        mounts=[{"Source":"/var/run/docker.sock","Destination":"/var/run/docker.sock"}] \
                 if socket_mount else []
        return {
            "State":{"Running":True},
            "HostConfig":{"Privileged":False},
            "NetworkSettings":{"Networks":networks},
            "Mounts":mounts,
        }

    def test_existing_caddy_isolated_without_socket(self):
        with (patch.object(q.g,"inspect_one",return_value=self.fake_caddy()),
              redirect_stdout(StringIO()) as out):
            q.inspect_running_proxy_metadata()
        self.assertIn("PASS_READONLY_METADATA",out.getvalue())
        self.assertIn("NEW_QA_PROXY=NOT_DEPLOYED_BY_4Q",out.getvalue())

    def test_existing_caddy_on_qa_pg_network_or_socket_denied(self):
        for case in ({"qa_network":True},{"socket_mount":True}):
            with self.subTest(case=case):
                with patch.object(q.g,"inspect_one",
                                  return_value=self.fake_caddy(**case)):
                    with self.assertRaises(q.IngressBlocked):
                        q.inspect_running_proxy_metadata()

    def test_combined_full_source_security_then_postcheck(self):
        with (
            patch.object(q.p,"combined") as predecessor,
            patch.object(q.g,"inspect_one",return_value=self.fake_caddy()),
            patch.object(q.g,"caddy_preflight",
                         return_value=q.h.EXPECTED_4G_CADDY_SHA256) as caddy,
            patch.object(q.g,"check_database_isolation") as database,
            patch.object(q.g,"ephemeral_cleanup") as cleanup,
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(q.main(["--source-sha",SHA]),0,out.getvalue())
        predecessor.assert_called_once_with(
            SHA,q.p.PLAN,q.k.TEMPLATE_PACKET,q.m.REGISTER,
            q.p.n.INTAKE,q.p.o.DOSSIER)
        caddy.assert_called_once()
        database.assert_called_once()
        cleanup.assert_called_once()
        for label in (
            "DB_R31_11_4Q_4P_THROUGH_4H_COMBINED_SECURITY=PASS_READONLY",
            "DB_R31_11_4Q_AFTER_QA_DB_AND_CADDY=PASS_UNCHANGED",
            "DB_R31_11_4Q_COMBINED_INGRESS_READINESS=PASS_DESIGN_ONLY_NO_DEPLOY",
            "DB_R31_11_4Q_REAL_QA_MTLS_ENDPOINT=NOT_DEPLOYED",
            "DB_R31_11_4Q_FINANCIAL_APPLY=LOCKED",
            "DB_R31_11_4Q_PRODUCTION_RELEASE=BLOCKED",
        ):
            self.assertIn(label,out.getvalue())

    def test_caddy_drift_stops_before_pg_postcheck(self):
        with (
            patch.object(q.p,"combined"),
            patch.object(q.g,"inspect_one",return_value=self.fake_caddy()),
            patch.object(q.g,"caddy_preflight",return_value="0"*64),
            patch.object(q.g,"check_database_isolation") as database,
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(q.main(["--source-sha",SHA]),2)
        database.assert_not_called()
        self.assertIn("DB_R31_11_4Q_BLOCK_REASON=Q_PUBLIC_CADDY_HASH_DRIFT",
                      out.getvalue())
        self.assertNotIn("COMBINED_INGRESS_READINESS=PASS",out.getvalue())

    def test_secret_error_is_not_exposed_to_qa_logs(self):
        with (
            patch.object(q.p,"combined",side_effect=RuntimeError(
                "SECRET_FIREBASE_UID_OR_SESSION_COOKIE")),
            redirect_stdout(StringIO()) as out,
        ):
            self.assertEqual(q.main(["--source-sha",SHA]),2)
        self.assertNotIn("SECRET_FIREBASE_UID_OR_SESSION_COOKIE",out.getvalue())
        self.assertIn("STOP=DB_R31_11_4Q_COMBINED_SECURITY_REVIEW_REQUIRED",
                      out.getvalue())
        self.assertIn("FINANCIAL_APPLY=LOCKED",out.getvalue())


if __name__=="__main__":
    unittest.main()
