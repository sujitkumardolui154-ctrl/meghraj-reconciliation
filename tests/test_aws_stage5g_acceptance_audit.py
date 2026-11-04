"""Stage 5G readonly service-audit contract."""
import importlib.util
import pathlib
import subprocess
import unittest
from unittest.mock import patch

P=pathlib.Path(__file__).resolve().parents[1]/"staging/aws_lightsail/stage5g_acceptance_audit.py"
S=importlib.util.spec_from_file_location("stage5g",P)
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)

class Stage5G(unittest.TestCase):
    def test_script_has_no_mutating_docker_calls(self):
        s=P.read_text()
        for t in ('"docker", "run"', '"docker", "exec"', '"docker", "stop"',
                  '"docker", "restart"', '"docker", "rm"', '"docker", "compose"'):
            self.assertNotIn(t,s)

    def test_only_loopback_get_http(self):
        with patch.object(m.urllib.request,"urlopen") as u:
            u.return_value.__enter__.return_value.status=401
            self.assertEqual(m.http_code(18082,"/"),401)
            req=u.call_args.args[0]
            self.assertEqual(req.get_method(),"GET")
            self.assertEqual(req.full_url,"http://127.0.0.1:18082/")

    def test_invalid_docker_inspect_fails_closed(self):
        with patch.object(m.subprocess,"run",return_value=subprocess.CompletedProcess([],1,"","fail")):
            with self.assertRaises(RuntimeError):
                m.container(m.CADDY)

if __name__=="__main__":
    unittest.main()
