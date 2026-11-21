import os
import unittest
from unittest.mock import MagicMock, patch

from sbi_pg_reporting import ReportCounts, read_report_counts


class AdapterTests(unittest.TestCase):
    def test_query_whitelist_and_readonly_options(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(0,), (0,)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        connector = MagicMock(return_value=connection)
        with patch.dict(os.environ, {
            'PGHOST': '/var/run/postgresql',
            'PGUSER': 'sbi_pr129_report_login',
            'PGDATABASE': 'sbi_reconciliation_main'
        }):
            result = read_report_counts(connect=connector)
        self.assertEqual(result, ReportCounts(0, 0))
        statements = [item.args[0] for item in cursor.execute.call_args_list]
        self.assertEqual(statements, [
            'SET TRANSACTION READ ONLY',
            'SELECT COUNT(*) FROM sbi.invoice_financial_summary',
            'SELECT COUNT(*) FROM sbi.payment_financial_summary',
        ])
        settings = connector.call_args.kwargs
        self.assertEqual(settings['host'], '/var/run/postgresql')
        self.assertEqual(settings['dbname'], 'sbi_reconciliation_main')
        self.assertEqual(settings['user'], 'sbi_pr129_report_login')
        self.assertNotIn('password', settings)
        self.assertIn('default_transaction_read_only=on', settings['options'])
        self.assertIn('statement_timeout=5000', settings['options'])

    def test_authentication_failure_is_not_swallowed(self):
        def failing_connector(**_):
            raise ConnectionError('synthetic failed connection')
        with self.assertRaises(ConnectionError):
            read_report_counts(connect=failing_connector)

    def test_report_count_serialization(self):
        result = ReportCounts(2, 3)
        self.assertEqual(result.as_dict(), {'invoice_report_rows': 2, 'payment_report_rows': 3})


if __name__ == '__main__':
    unittest.main()
