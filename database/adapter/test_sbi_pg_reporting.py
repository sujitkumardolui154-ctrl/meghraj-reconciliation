import unittest
from unittest.mock import Mock, patch
from sbi_pg_reporting import ReportCounts, read_report_counts


class ReportingAdapterTests(unittest.TestCase):
    def test_success_and_read_only_queries(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(0,), (0,)]
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        connect = Mock(return_value=conn)
        with patch.dict('os.environ', {'PGHOST': '/var/run/postgresql', 'PGUSER': 'sbi_pr129_report_login'}):
            value = read_report_counts(connect=connect)
        self.assertEqual(value, ReportCounts(0, 0))
        sql = [c.args[0] for c in cursor.execute.call_args_list]
        self.assertEqual(sql, [
            'SET TRANSACTION READ ONLY',
            'SELECT COUNT(*) FROM sbi.invoice_financial_summary',
            'SELECT COUNT(*) FROM sbi.payment_financial_summary',
        ])
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs['dbname'], 'sbi_reconciliation_main')
        self.assertEqual(kwargs['user'], 'sbi_pr129_report_login')
        self.assertNotIn('password', kwargs)
        self.assertIn('default_transaction_read_only=on', kwargs['options'])

    def test_bad_connection_propagates_without_writes(self):
        def fail(**kwargs):
            raise ConnectionError('authentication failed')
        with self.assertRaises(ConnectionError):
            read_report_counts(connect=fail)

    def test_dict_serialization(self):
        self.assertEqual(ReportCounts(3, 4).as_dict(), {'invoice_report_rows': 3, 'payment_report_rows': 4})


if __name__ == '__main__':
    unittest.main()
