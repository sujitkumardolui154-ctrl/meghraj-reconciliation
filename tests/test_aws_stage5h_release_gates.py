"""Stage 5H offline contract for read-only final-gate inspection."""
import importlib.util
import pathlib
import subprocess
import unittest
from unittest.mock import patch

PATH=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage5h_release_gates.py"
spec=importlib.util.spec_from_file_location("sbi_stage5h",PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FinalGateTests(unittest.TestCase):
    def test_only_known_unauthenticated_gets(self):
        with patch.object(m.urllib.request,"urlopen") as fn:
            fn.return_value.__enter__.return_value.status=401
            self.assertEqual(m.check_url(m.AWS_URL+"/")["http"],401)
            req=fn.call_args.args[0]
            self.assertEqual(req.get_method(),"GET")
            self.assertEqual(req.full_url,m.AWS_URL+"/")

    def test_docker_inspect_fails_closed(self):
        with patch.object(m.subprocess,"run",
                          return_value=subprocess.CompletedProcess([],1,"","")):
            with self.assertRaises(RuntimeError):
                m.docker_inspect()

    def test_no_mutation_or_secret_extraction(self):
        content=PATH.read_text()
        for bad in ('"docker","run"','"docker","exec"','"docker","restart"',
                    '"docker","stop"','"docker","rm"','"docker","cp"',
                    '"docker","volume","rm"','"POST"', '"PUT"', '"PATCH"'):
            self.assertNotIn(bad,content)
        self.assertIn('"feature_parity":"NOT_VERIFIED"',content)
        self.assertIn('"restart_survival"]="NOT_TESTED"',content)

if __name__=="__main__":
    unittest.main()
