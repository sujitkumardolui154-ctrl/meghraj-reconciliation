"""R31.11.4H regression: strict pinned source permits generated .pyc only.

No AWS, Firebase, Docker or database usage.
"""
import unittest
from unittest.mock import patch

import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4h_combined_readonly_security as h

SHA="a"*40


class PycacheSourceGateTests(unittest.TestCase):
    def check_status(self, status, *, sha=SHA):
        def run(*args):
            if "rev-parse" in args:
                return 0, SHA+"\n"
            if "status" in args:
                self.assertIn("--untracked-files=all",args)
                return 0,status
            raise AssertionError("Unexpected command, source check must be git-only")
        with patch.object(g,"run",side_effect=run):
            return g.check_source(sha)

    def test_clean_source_passes(self):
        self.assertTrue(self.check_status(""))

    def test_generated_pycache_files_only_are_accepted(self):
        caches=(
          "?? staging/aws_login_v150/__pycache__/r31_11_4e_session_binding_readiness.cpython-312.pyc\n"
          "?? staging/aws_login_v150/__pycache__/r31_11_4g_mtls_readonly_preflight.cpython-312.pyc\n"
          "?? dashboard_source/__pycache__/dashboard_sessions.cpython-312.pyc\n"
        )
        self.assertTrue(self.check_status(caches))

    def test_any_source_change_or_noncache_file_blocks(self):
        for status in (
            " M staging/aws_login_v150/r31_11_4g_mtls_readonly_preflight.py\n",
            "M  staging/aws_login_v150/r31_11_4h_combined_readonly_security.py\n",
            "?? staging/aws_login_v150/.env\n",
            "?? staging/aws_login_v150/__pycache__/unsafe.txt\n",
            "?? staging/aws_login_v150/fake.pyc\n",
            '?? "staging/aws_login_v150/__pycache__/file with spaces.pyc"\n',
            "?? staging/aws_login_v150/__pycache__/module.cpython-312.pyc\n"
            "?? staging/aws_login_v150/app.py\n",
        ):
            with self.subTest(status=status):
                with self.assertRaises(g.ReadOnlyBlocked):
                    self.check_status(status)

    def test_wrong_source_revision_still_denied(self):
        with self.assertRaises(g.ReadOnlyBlocked):
            self.check_status("",sha="b"*40)

    def test_combined_disables_new_bytecode_writes(self):
        import sys
        self.assertTrue(sys.dont_write_bytecode)


if __name__=="__main__":
    unittest.main()
