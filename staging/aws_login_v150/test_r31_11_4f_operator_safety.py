"""R31.11.4F host operator safety regression: no AWS or live Firebase."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import r31_11_4f_private_runtime_operator as op


class OperatorSafetyTests(unittest.TestCase):
    SHA="a"*40

    def test_default_mode_cannot_launch_runtime_or_ask_password(self):
        with (patch.object(op,"source_guard"),
              patch.object(op.gate,"run_checks"),
              patch.object(op,"baseline",return_value=None),
              patch.object(op,"no_preexisting_resources"),
              patch.object(op,"execute") as execute,
              patch.object(op,"tokens_from_two_real_test_users") as password,
              redirect_stdout(StringIO()) as capture):
            result=op.main(["--source-sha",self.SHA])
        self.assertEqual(result,0)
        self.assertIn("DB_R31_11_4F_MODE=READONLY_PLAN_NO_DOCKER_CHANGES",
                      capture.getvalue())
        execute.assert_not_called()
        password.assert_not_called()

    def test_no_execution_without_explicit_approval(self):
        with (patch.object(op,"source_guard"),
              patch.object(op.gate,"run_checks"),
              patch.object(op,"baseline"),
              patch.object(op,"no_preexisting_resources"),
              patch.object(op,"execute") as execute,
              redirect_stdout(StringIO()) as capture):
            result=op.main(["--source-sha",self.SHA,"--execute"])
        self.assertEqual(result,2)
        self.assertIn("STOP=DB_R31_11_4F_PRIVATE_ACCEPTANCE_REVIEW_REQUIRED",
                      capture.getvalue())
        execute.assert_not_called()

    def test_private_runtime_has_no_port_public_secret_or_write(self):
        image="synthetic-ci-image:123"
        container={
          "State":{"Running":False},
          "Config":{"User":"10001:10001","ExposedPorts":None},
          "HostConfig":{"PortBindings":{},"Privileged":False,"ReadonlyRootfs":True},
          "NetworkSettings":{"Networks":{op.EGRESS:{},op.QA_NET:{}}},
          "Mounts":[
              {"Source":str(op.SECRETS),"Destination":"/run/secrets","RW":False},
              {"Source":str(op.TEMP_ADC),"Destination":"/run/firebase/adc.json","RW":False},
          ],
        }
        calls=[]
        def fake_docker(*args,**kwargs):
            calls.append(args)
            if args[:1]==("inspect",):
                return json.dumps([container])
            return "ok"
        with patch.object(op,"docker",side_effect=fake_docker):
            op.create_private_runtime(image)
        names=[a[0] for a in calls]
        self.assertEqual(names,["network","create","network","inspect"])
        create=calls[1]
        self.assertNotIn("-p",create)
        self.assertNotIn("--publish",create)
        self.assertIn("--read-only",create)
        self.assertIn("--cap-drop",create)
        self.assertIn("--security-opt",create)
        self.assertNotIn("/var/run/docker.sock"," ".join(create))
        self.assertNotIn("sbi_reconciliation_main"," ".join(create))
        self.assertNotIn("FINANCIAL_APPLY=ENABLED"," ".join(create))

    def test_firebase_token_passes_only_via_process_stdin(self):
        expected=set(op.EXPECTED_LINES)
        with (patch.object(op.subprocess,"run",return_value=
                     SimpleNamespace(returncode=0,stdout="\n".join(expected)+"\n",
                                     stderr="TOKEN_DO_NOT_PRINT")) as run,
              redirect_stdout(StringIO()) as capture):
            op.run_one_shot(["ci-fake-a","ci-fake-b"])
        self.assertEqual(run.call_args.args[0][-2:],["-ai",op.APP])
        self.assertNotIn("ci-fake-a",str(run.call_args.args[0]))
        self.assertIn("ci-fake-a",run.call_args.kwargs["input"])
        self.assertNotIn("ci-fake-a",capture.getvalue())
        self.assertNotIn("TOKEN_DO_NOT_PRINT",capture.getvalue())
        self.assertIn("PASS_TWO_FIREBASE_UID_BOUND_TO_PG",capture.getvalue())

    def test_any_raw_exception_is_suppressed(self):
        with (patch.object(op,"source_guard",
                           side_effect=RuntimeError("SECRET_TOKEN_NOT_FOR_LOGS")),
              redirect_stdout(StringIO()) as capture):
            self.assertEqual(op.main(["--source-sha",self.SHA]),2)
        self.assertNotIn("SECRET_TOKEN_NOT_FOR_LOGS",capture.getvalue())
        self.assertIn("DB_R31_11_4F_FINANCIAL_APPLY=LOCKED",capture.getvalue())

    def test_synthetic_firebase_api_key_not_logged(self):
        payload={"idToken":"ci-token-not-to-log","localId":"ci-fake-uid"}
        class FakeReply:
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,limit):return json.dumps(payload).encode()
        with (patch.object(op.sys.stdin,"isatty",return_value=True),
              patch.object(op.urllib.request,"urlopen",return_value=FakeReply()),
              redirect_stdout(StringIO()) as capture):
            token,uid=op.sign_in("ci-fake-key","fake@example.invalid","ci-password")
        self.assertEqual(token,payload["idToken"])
        self.assertEqual(uid,payload["localId"])
        self.assertEqual(capture.getvalue(),"")


if __name__=="__main__":
    unittest.main()
