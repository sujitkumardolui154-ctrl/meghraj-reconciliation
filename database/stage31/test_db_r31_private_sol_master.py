"""Synthetic tests for private approved SOL master, no real SBI identity data."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parent))
from db_r31_private_sol_master import (
    PrivateSolMasterReview,load_approved_sol_file,normalized_sol,SCHEMA,
)


class R31MasterTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/"approved-private-sol.json"
        self.doc={
            "schema":SCHEMA,
            "branches":[
                {"sol_id":"001505","official_branch_name":"SYNTHETIC BRANCH A",
                 "approved":True},
                {"sol_id":"6884","official_branch_name":"SYNTHETIC BRANCH B",
                 "approved":True},
                {"sol_id":"6884","official_branch_name":"SYNTHETIC BRANCH C",
                 "approved":True},
                {"sol_id":"3999","official_branch_name":"SYNTHETIC PENDING",
                 "approved":False},
                {"sol_id":"99922","official_branch_name":"SYNTHETIC APPROVED",
                 "approved":True},
            ],
        }
        self.store()

    def store(self):
        raw=(json.dumps(self.doc,sort_keys=True)+"\n").encode()
        self.path.write_bytes(raw)
        self.path.chmod(0o600)
        self.digest=hashlib.sha256(raw).hexdigest()

    def test_01_unambiguous_only(self):
        names,digest=load_approved_sol_file(str(self.path),self.digest)
        self.assertEqual(names,{"1505":"SYNTHETIC BRANCH A",
                                "99922":"SYNTHETIC APPROVED"})
        self.assertEqual(digest,self.digest)

    def test_02_known_99922_is_not_permanently_blocked(self):
        names,_=load_approved_sol_file(str(self.path),self.digest)
        self.assertEqual(names["99922"],"SYNTHETIC APPROVED")

    def test_03_collision_and_unapproved_hold(self):
        names,_=load_approved_sol_file(str(self.path),self.digest)
        self.assertNotIn("6884",names)
        self.assertNotIn("3999",names)

    def test_04_preserve_source_sol_leading_zero_lookup(self):
        self.assertEqual(normalized_sol("001505"),"1505")
        self.assertEqual(normalized_sol("000001"),"1")
        self.assertIsNone(normalized_sol("000000"))
        self.assertIsNone(normalized_sol("1505.0"))

    def test_05_master_missing_is_safe_hold_mode(self):
        self.assertEqual(load_approved_sol_file("",""),({},None))

    def test_06_partial_master_config_rejected(self):
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_PATH_AND_SHA_REQUIRED"):
            load_approved_sol_file(str(self.path),"")

    def test_07_modified_master_sha_rejected(self):
        self.path.write_text('{"schema":"not approved"}')
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_BYTES_SHA_MISMATCH"):
            load_approved_sol_file(str(self.path),self.digest)

    def test_08_unprotected_permission_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_PRIVATE_PERMISSIONS_REQUIRED"):
            load_approved_sol_file(str(self.path),self.digest)

    def test_09_symlink_rejected(self):
        link=Path(self.folder.name)/"link.json"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_PRIVATE_PATH_REQUIRED"):
            load_approved_sol_file(str(link),self.digest)

    def test_10_unapproved_version_rejected(self):
        self.doc["schema"]="not-approved-version"
        self.store()
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_SCHEMA_UNAPPROVED"):
            load_approved_sol_file(str(self.path),self.digest)

    def test_11_non_boolean_approval_rejected(self):
        self.doc["branches"][0]["approved"]="yes"
        self.store()
        with self.assertRaisesRegex(PrivateSolMasterReview,
                                    "SOL_MASTER_ROW_DATA_INVALID"):
            load_approved_sol_file(str(self.path),self.digest)

    def test_12_revoked_mapping_with_same_sol_never_auto_selected(self):
        self.doc["branches"].append({
            "sol_id":"1505","official_branch_name":"SYNTHETIC BRANCH A",
            "approved":False})
        self.store()
        names,_=load_approved_sol_file(str(self.path),self.digest)
        self.assertNotIn("1505",names)


if __name__=="__main__":
    unittest.main()
