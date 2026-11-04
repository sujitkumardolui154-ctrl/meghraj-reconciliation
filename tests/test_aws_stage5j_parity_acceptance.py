"""Offline Stage 5J feature parity and safety contracts."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

PATH=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage5j_parity_acceptance.py"
spec=importlib.util.spec_from_file_location("stage5j",PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Stage5JTests(unittest.TestCase):
    def test_source_only_does_not_claim_deployed_parity(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            for file in m.REF_FILES:
                p=root/m.REFERENCE/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("")
            for file in m.PREVIEW_FILES:
                p=root/m.PREVIEW/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("")
            (root/m.REFERENCE/m.REF_FILES[0]).write_text("/api/reports")
            result=m.source_scan(root)
            self.assertTrue(result["reports"]["cloud_run_source_declares"])
            self.assertFalse(result["reports"]["aws_preview_source_declares"])
            self.assertTrue(all(not v["deployment_verified"] for v in result.values()))

    def test_no_credential_or_finance_io(self):
        src=PATH.read_text()
        for bad in ("docker run","docker exec","docker restart","subprocess.run", "PREVIEW_PASSWORD",
                    "Authorization", '"POST"', '"PUT"', '"PATCH"'):
            self.assertNotIn(bad,src)

    def test_unauthenticated_get_only(self):
        with patch.object(m.urllib.request,"urlopen") as fn:
            fn.return_value.__enter__.return_value.status=401
            self.assertEqual(m.get_status(m.BASE+"/"),401)
            req=fn.call_args.args[0]
            self.assertEqual(req.get_method(),"GET")
            self.assertNotIn("Authorization", str(req.headers))

if __name__=="__main__":
    unittest.main()
