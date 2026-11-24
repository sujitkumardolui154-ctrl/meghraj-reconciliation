"""R31.7 dedicated QA profile safety contracts (synthetic, offline).

Never creates/deletes Docker containers or accesses AWS. Tests only functions
under mocked inspect/docker values, including regression for dual-home auth.
"""
from pathlib import Path
from unittest import mock
import unittest
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import db_r31_owner_qa_combined as qa
import db_r31_7_dedicated_isolated as launcher

class ProfileIsolationTests(unittest.TestCase):
    def setUp(self):
        self.orig=(qa.PG,qa.NETWORK,qa.PRIVATE)
        self.addCleanup(self.restore)
    def restore(self):
        qa.PG,qa.NETWORK,qa.PRIVATE=self.orig

    def pg(self,networks=None):
        return {
            "State":{"Status":"running"},
            "NetworkSettings":{"Networks":{n:{} for n in (
                networks if networks is not None else (qa.NETWORK,))}},
            "HostConfig":{"PortBindings":None},
            "Mounts":[],
        }

    def net(self,names,internal=True):
        return [{"Internal":internal,
                 "Containers":{str(n):{"Name":n} for n in names}}]

    def fake_validate(self,names,pg_networks=None,internal=True,unsafe=None):
        def inspect(name):
            if name==qa.PG:return self.pg(pg_networks)
            return (unsafe or {}).get(name,self.pg((qa.NETWORK,)))
        def docker(*a,**kw):
            if a[:2]==("network","inspect"):
                import json
                return json.dumps(self.net(names,internal))
            raise AssertionError("Unexpected Docker request")
        with mock.patch.object(qa,"inspect",inspect),\
             mock.patch.object(qa,"docker",docker),\
             mock.patch.object(qa,"db_exists",side_effect=lambda db:db==qa.SOURCE),\
             mock.patch.object(qa.Path,"is_file",return_value=True):
            return qa.validate_safety()

    def test_01_original_staging_stays_pinned(self):
        self.assertEqual(qa.PG,"sbi-synthetic-postgres-38-31")
        self.assertEqual(qa.NETWORK,"sbi-synthetic-isolated-38-31")

    def test_02_dedicated_profile_does_not_mutate_original_source_files(self):
        qa.use_dedicated_isolated_profile()
        self.assertEqual(qa.PG,"sbi-r31-7-dedicated-pg")
        self.assertEqual(qa.NETWORK,"sbi-r31-7-dedicated-internal")
        self.assertEqual(str(qa.PRIVATE),
                         "/home/ubuntu/sbi-db-management/db-r31-7-dedicated")

    def test_03_one_pg_member_only_passes(self):
        qa.use_dedicated_isolated_profile()
        self.fake_validate({qa.PG})

    def test_04_dual_homed_auth_member_stays_blocked(self):
        qa.use_dedicated_isolated_profile()
        auth="sbi-r31-auth-private-qa"
        with self.assertRaisesRegex(RuntimeError,
                                    "QA_NETWORK_ISOLATION_FAILED"):
            self.fake_validate({qa.PG,auth},
                               unsafe={auth:self.pg((qa.NETWORK,
                                            "aws_lightsail_private_web"))})

    def test_05_pg_attached_to_web_stays_blocked(self):
        qa.use_dedicated_isolated_profile()
        with self.assertRaisesRegex(RuntimeError,
                                    "QA_NETWORK_ISOLATION_FAILED"):
            self.fake_validate({qa.PG},pg_networks=(qa.NETWORK,
                                        "aws_lightsail_private_web"))

    def test_06_network_internal_false_stays_blocked(self):
        qa.use_dedicated_isolated_profile()
        with self.assertRaisesRegex(RuntimeError,
                                    "QA_NETWORK_ISOLATION_FAILED"):
            self.fake_validate({qa.PG},internal=False)

    def test_07_shared_original_auth_remains_unapproved(self):
        auth="sbi-r31-auth-private-qa"
        with self.assertRaisesRegex(RuntimeError,
                                    "QA_NETWORK_ISOLATION_FAILED"):
            self.fake_validate({qa.PG,"sbi-ft04-payment-staging-overlay",auth})

    def test_08_qa_launcher_never_disconnects_original(self):
        c=(ROOT/"db_r31_7_dedicated_isolated.py").read_text()
        for forbidden in ('docker("network","disconnect"',
                          'docker("rm","-f","sbi-r31-auth-private-qa"',
                          'docker("network","rm","sbi-synthetic-isolated-38-31"',
                          'docker("run","--network","aws_lightsail_private_web"'):
            self.assertNotIn(forbidden,c)
        self.assertIn("DEDICATED_NETWORK",c)
        self.assertIn("DEDICATED_PG",c)

    def test_09_explicit_profile_only_accepted_by_runner(self):
        c=(ROOT/"db_r31_owner_qa_combined.py").read_text()
        self.assertIn('sys.argv[1:]==["--dedicated-isolated-qa"]',c)
        self.assertIn("QA_RUNNER_ARGUMENTS_NOT_ALLOWED",c)

    def test_10_unknown_cleanup_names_never_removed(self):
        c=(ROOT/"db_r31_7_dedicated_isolated.py").read_text()
        self.assertIn("DEDICATED_CONTAINER_CHANGED_REFUSE_CLEANUP",c)
        self.assertIn("DEDICATED_NETWORK_CHANGED_REFUSE_CLEANUP",c)
        self.assertIn("DEDICATED_UNKNOWN_PRIVATE_CREDENTIAL_REFUSE_CLEANUP",c)

if __name__=="__main__":
    unittest.main()
