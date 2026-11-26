"""R31.11.4A minimal offline safety tests; no Docker or AWS side effects."""
from __future__ import annotations
import contextlib
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

import r31_11_4a_isolated_postgres_provision as p


class IsolatedPostgresProvisionTests(unittest.TestCase):
    IMAGE = "sha256:" + "a"*64

    def test_unique_resources_never_use_existing_qa_or_finance_names(self):
        self.assertNotEqual(p.NAME,p.EXISTING_PG)
        self.assertNotEqual(p.DATABASE,p.EXISTING_QA)
        self.assertNotIn("sbi_reconciliation",p.DATABASE)
        self.assertNotIn("sbi_r31_11_tenant_clone",p.DATABASE)
        self.assertNotEqual(p.NETWORK,"sbi-synthetic-isolated-38-31")
        self.assertIn("r3114",p.NAME)
        self.assertIn("r3114",p.VOLUME)
        self.assertEqual(p.BASE_ALLOWED,
            frozenset(("postgres","template0","template1",p.DATABASE)))

    def test_docker_run_has_strict_private_topology_and_no_public_port(self):
        args=p._run_args(self.IMAGE)
        self.assertEqual(args[0:2],("run","-d"))
        self.assertIn("--pull",args)
        self.assertIn("never",args)
        self.assertIn("--network",args)
        self.assertIn(p.NETWORK,args)
        self.assertIn("--read-only",args)
        self.assertIn("no-new-privileges",args)
        self.assertIn("--cap-drop",args)
        self.assertIn("ALL",args)
        self.assertIn("--pids-limit",args)
        self.assertIn("--restart",args)
        self.assertIn("no",args)
        self.assertIn("POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",args)
        self.assertIn("POSTGRES_DB="+p.DATABASE,args)
        self.assertIn("POSTGRES_PASSWORD_FILE="+p.SECRET_MOUNT,args)
        self.assertNotIn("--publish",args)
        self.assertNotIn("-p",args)
        self.assertNotIn("--privileged",args)
        self.assertNotIn("sbi_reconciliation_main"," ".join(args))
        self.assertNotIn("sbi_r31_owner_qa_20261125"," ".join(args))
        self.assertNotIn("docker.sock"," ".join(args))
        self.assertNotIn("password=",str(args).lower())
        self.assertEqual(args[-1],self.IMAGE)

    def test_resource_probe_no_existing_name_required(self):
        with (patch.object(p,"preflight"),
              patch.object(p,"inspect_original_image",return_value=self.IMAGE),
              patch.object(p,"caddy_fingerprint",return_value="caddyhash"),
              patch.object(p,"_existing_resource_names",return_value={
                  "container":False,"network":False,"volume":False,
                  "secret":False,"secret_dir":False,
              }),
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertEqual(p.review_plan(),(self.IMAGE,"caddyhash"))
        self.assertIn("ALL_UNUSED",output.getvalue())
        for occupied in ("container","network","volume","secret","secret_dir"):
            with (patch.object(p,"preflight"),
                  patch.object(p,"inspect_original_image",return_value=self.IMAGE),
                  patch.object(p,"caddy_fingerprint",return_value="caddyhash"),
                  patch.object(p,"_existing_resource_names",return_value={
                      occupied:True,
                  })):
                with self.assertRaises(p.ProvisionBlocked):
                    p.review_plan()

    def test_plan_is_readonly_and_missing_approval_never_applies(self):
        with (patch.object(p,"review_plan",return_value=(self.IMAGE,"hash")),
              patch.object(p,"apply") as apply,
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertEqual(p.main([]),0)
            self.assertEqual(p.main(["--apply"]),2)
            apply.assert_not_called()
        self.assertIn("MODE=READONLY_PLAN_ONLY_NO_CHANGES",output.getvalue())
        self.assertIn("STOP=DB_R31_11_4A_GUARDED",output.getvalue())
        with (patch.object(p,"review_plan",return_value=(self.IMAGE,"hash")),
              patch.object(p,"apply") as apply,
              contextlib.redirect_stdout(StringIO())):
            self.assertEqual(p.main(["--apply","--approve",p.APPROVE]),0)
            apply.assert_called_once_with(self.IMAGE,"hash")

    def test_original_image_requires_pin_and_postgres16(self):
        info={
            "Image":self.IMAGE,"State":{"Running":True},
            "Config":{"Entrypoint":["docker-entrypoint.sh"]},
            "HostConfig":{"PortBindings":None},
            "NetworkSettings":{"Networks":{"sbi-synthetic-isolated-38-31":{}}},
        }
        with patch.object(p,"docker",side_effect=lambda *args,**kwargs: (
            "postgres (PostgreSQL) 16.8" if args[0]=="exec"
            else "["+__import__("json").dumps(info)+"]"
        )):
            self.assertEqual(p.inspect_original_image(),self.IMAGE)
        info["Image"]="postgres:16"
        with patch.object(p,"docker",return_value="["+__import__("json").dumps(info)+"]"):
            with self.assertRaises(p.ProvisionBlocked):
                p.inspect_original_image()

    def test_caddy_route_references_forbid_provision(self):
        for text in (
            "reverse_proxy sbi-r3114-private-api:8080",
            "reverse_proxy sbi-r3114-private-postgres:5432",
            "reverse_proxy sbi-r31-auth-private-qa:8080",
        ):
            with patch.object(p,"docker",return_value=text):
                with self.assertRaises(p.ProvisionBlocked):
                    p.caddy_fingerprint()
        with patch.object(p,"docker",return_value="example.invalid { respond 404 }"):
            self.assertEqual(len(p.caddy_fingerprint()),64)

    def test_runtime_topology_positive_and_rejects_public_port(self):
        mounts=[
            {"Type":"volume","Name":p.VOLUME,
             "Destination":"/var/lib/postgresql/data"},
            {"Type":"bind","Source":str(p.PASSWORD_PATH),
             "Destination":p.SECRET_MOUNT,"RW":False},
        ]
        info={
            "Image":self.IMAGE,"State":{"Running":True},
            "Config":{"Labels":{p.LABEL:"true"}},
            "HostConfig":{
                "Privileged":False,"PortBindings":{},
                "ReadonlyRootfs":True,"SecurityOpt":["no-new-privileges"],
            },
            "NetworkSettings":{"Networks":{p.NETWORK:{}}},
            "Mounts":mounts,
        }
        net={"Internal":True,"Attachable":False}
        import json,copy
        def fake(*args,**kwargs):
            return json.dumps([net if args[0]=="network" else info])
        with patch.object(p,"docker",side_effect=fake):
            self.assertTrue(p._exact_topology(self.IMAGE))
        bad=copy.deepcopy(info)
        bad["HostConfig"]["PortBindings"]={"5432/tcp":[{"HostPort":"5432"}]}
        with patch.object(p,"docker",side_effect=lambda *args,**kwargs: (
            json.dumps([net if args[0]=="network" else bad])
        )):
            self.assertFalse(p._exact_topology(self.IMAGE))

    def test_catalog_rejects_unexpected_db_or_data(self):
        dbs="\n".join(sorted(p.BASE_ALLOWED))
        def fake(*args,**kwargs):
            if "postgres -V" in " ".join(args):
                return "postgres (PostgreSQL) 16.10"
            if "FROM pg_database" in " ".join(args):
                return dbs
            return "0"
        with patch.object(p,"docker",side_effect=fake),\
             contextlib.redirect_stdout(StringIO()):
            p._catalog()
        with patch.object(p,"docker",side_effect=lambda *args,**kwargs:(
            dbs+"\nsbi_reconciliation_main"
            if "FROM pg_database" in " ".join(args) else "0"
        )):
            with self.assertRaises(p.ProvisionBlocked):
                p._catalog()

    def test_empty_schema_restore_is_isolated_to_private_probe(self):
        recorded=[]
        def text_command(*args,**kwargs):
            recorded.append(args)
            if len(args)>2 and args[2]=="psql":
                return (p.PROBE_DB if "SELECT current_database()" in " ".join(args)
                        else "0")
            return ""
        with (patch.object(p,"docker",side_effect=text_command),
              patch.object(p,"docker_blob",return_value=b"PGDMPtest"),
              contextlib.redirect_stdout(StringIO())):
            p._empty_schema_restore_drill()
        self.assertTrue(any(a[2]=="createdb" and p.PROBE_DB in a
                            for a in recorded))
        self.assertTrue(any(a[2]=="dropdb" and p.PROBE_DB in a
                            for a in recorded))
        self.assertFalse(any(p.EXISTING_QA in " ".join(a) for a in recorded))
        self.assertFalse(any("sbi_reconciliation_main" in " ".join(a)
                             for a in recorded))

    def test_release_never_lifts_financial_lock(self):
        with (patch.object(p,"review_plan",side_effect=p.ProvisionBlocked("x")),
              contextlib.redirect_stdout(StringIO()) as output):
            self.assertEqual(p.main([]),2)
        s=output.getvalue()
        self.assertIn("FINANCIAL_APPLY=LOCKED",s)
        self.assertIn("PRODUCTION_FINANCIAL_WRITES=NONE_BY_SCRIPT",s)
        self.assertIn("R3112_FINANCIAL_INTEGRATION=QUARANTINED",s)
        self.assertIn("RELEASE=PRODUCTION_BLOCKED",s)


if __name__=="__main__":
    unittest.main()
