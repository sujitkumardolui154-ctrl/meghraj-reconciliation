"""Synthetic, read-only regression tests. Run: python -m unittest discover -s staging/mxp-gst/tests"""
import importlib.util
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mxp_gst_matcher", root / "matcher.py")
matcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = matcher
spec.loader.exec_module(matcher)

class AliasTests(unittest.TestCase):
    def test_owner_approved_cac_malda(self):
        r = matcher.resolve_name("cac malda", [])
        self.assertEqual((r["sol_id"], r["official_name"]), ("18583", "CASH ADMINSTRATION CELL MALDA"))

    def test_owner_approved_kalyani(self):
        r = matcher.resolve_name("RBO 6 Kalyani", [])
        self.assertEqual(r["sol_id"], "18252")

    def test_sbi_fund_requires_krishnanagar(self):
        self.assertEqual(matcher.resolve_name("SBI FUND MANAGEMENT LTD KRISHNANAGAR", [])["sol_id"], "99922")
        self.assertEqual(matcher.resolve_name("SBI FUND MANAGEMENT LTD", [])["status"], "REVIEW_REQUIRED")

    def test_incomplete_rbo_rejected(self):
        for raw in ("RBO", "R.B.O.", "RBO-III", "RBO III"):
            self.assertEqual(matcher.resolve_name(raw, [])["status"], "REVIEW_REQUIRED")

    def test_cross_rbo_alias_blocked(self):
        master = [{"Official Branch Name": "RBO 5 KRISHNAGAR", "SOL ID": "14872", "Search Aliases": "RBO 6 KALYANI"}]
        self.assertEqual(matcher.resolve_name("RBO 6 Kalyani",master)["sol_id"], "18252")
        master = [{"Official Branch Name": "RBO 2 SILIGURI", "SOL ID": "14879", "Search Aliases": "RBO 3 SILIGURI"}]
        self.assertEqual(matcher.resolve_name("RBO 3 SILIGURI",master)["status"], "REVIEW_REQUIRED")

    def test_conflict_no_silent_auto_match(self):
        master = [{"Official Branch Name":"RAMPUR","SOL ID":"08064","Search Aliases":""},
                  {"Official Branch Name":"RAMPUR","SOL ID":"09723","Search Aliases":""}]
        self.assertEqual(matcher.resolve_name("Rampur",master)["reason"], "MULTIPLE_MASTER_MATCHES")

    def test_unique_official_and_alias(self):
        master = [{"Official Branch Name":"HALISAHAR STATION ROAD","SOL ID":"12463","Search Aliases":"HALISHAHAR STN ROAD"}]
        self.assertEqual(matcher.resolve_name("HALISHAHAR STN ROAD",master)["sol_id"],"12463")

if __name__ == "__main__":
    unittest.main()
