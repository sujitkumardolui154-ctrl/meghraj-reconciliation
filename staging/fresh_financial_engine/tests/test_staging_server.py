"""Localhost-only synthetic HTTP tests. Do not load finance data or files."""
import json
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from staging_server import SyntheticHandler, synthetic_smoke, stage3_mock_smoke


class SyntheticHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = HTTPServer(("127.0.0.1", 0), SyntheticHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.http.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)

    def call(self, path, method="GET", data=None):
        req = Request(self.url + path, method=method, data=data)
        try:
            res = urlopen(req, timeout=2)
        except HTTPError as e:
            res = e
        with res:
            return res.status, json.loads(res.read())

    def test_health_is_synthetic_and_locked(self):
        status, doc = self.call('/healthz')
        self.assertEqual(status, 200)
        self.assertEqual(doc['engine'], 'NEW engine 21 11 2026')
        self.assertEqual(doc['mode'], 'SYNTHETIC_ONLY')
        for key in ('financial_writes', 'financial_execution_enabled', 'apply_enabled',
                    'production_approved', 'historical_records_accessed', 'database_connected'):
            self.assertIs(doc[key], False)

    def test_readiness_means_staging_only(self):
        status, doc = self.call('/readyz')
        self.assertEqual(status, 200)
        self.assertEqual(doc['ready_for'], 'synthetic_staging_only')
        self.assertIs(doc['production_approved'], False)

    def test_hardcoded_fabricated_engine_works(self):
        status, doc = self.call('/api/synthetic-demo')
        self.assertEqual(status, 200)
        self.assertEqual(doc['synthetic_probe'], 'PASS')
        self.assertEqual(doc['proposal_count'], 1)
        self.assertEqual(doc['actual_financial_status'], 'NOT_ASSIGNED')
        self.assertIs(doc['financial_writes'], False)
        self.assertEqual(synthetic_smoke()['proposal_count'], 1)

    def test_financial_routes_deny_all_posts(self):
        for path in ('/api/payment-reconciliation/apply',
                     '/api/payment-reconciliation/preflight', '/api/synthetic-demo'):
            with self.subTest(path=path):
                status, doc = self.call(path, 'POST', b'{"not":"accepted"}')
                self.assertEqual(status, 403)
                self.assertEqual(doc['error'], 'FINANCIAL_APPLY_LOCKED')
                self.assertIs(doc['financial_writes'], False)

    def test_unlisted_routes_and_query_strings_not_accepted(self):
        for path in ('/api/payment-reconciliation/status', '/api/real-data',
                     '/api/synthetic-demo?invoice=MXP001'):
            with self.subTest(path=path):
                status, doc = self.call(path)
                self.assertEqual(status, 404)
                self.assertEqual(doc['error'], 'ROUTE_NOT_AVAILABLE')


    def test_stage3_mock_bridge_is_read_only_and_dual_reviewed(self):
        status, doc = self.call('/api/stage3/synthetic-bridge')
        self.assertEqual(status, 200)
        self.assertEqual(doc['stage3_probe'], 'PASS')
        self.assertTrue(doc['mock_review_completed'])
        self.assertEqual(doc['mock_candidate_ledger_edges'], 1)
        self.assertFalse(doc['mock_ledger_persistent'])
        self.assertFalse(doc['financial_writes'])
        self.assertEqual(stage3_mock_smoke()['actual_financial_status'], 'NOT_ASSIGNED')

    def test_stage3_endpoint_never_accepts_payments(self):
        status, doc = self.call('/api/stage3/synthetic-bridge','POST',b'{"credit":"117.00"}')
        self.assertEqual(status, 403)
        self.assertFalse(doc['apply_enabled'])

    def test_other_mutation_methods_denied(self):
        for method in ('PUT', 'PATCH', 'DELETE'):
            status, doc = self.call('/api/synthetic-demo', method, b'{}')
            self.assertEqual(status, 403)
            self.assertIs(doc['financial_writes'], False)


if __name__ == '__main__':
    unittest.main()