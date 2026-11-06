"""Offline, synthetic GCP inventory and GitHub sanitization safety tests."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "sbi_cloud_collector", ROOT/"staging/gcp_owner_private/collect_phase2_readiness.py"
)
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

PROD={
    "metadata":{"name":"sbi-dashboard","annotations":{"run.googleapis.com/ingress":"all"}},
    "spec":{"template":{"spec":{
        "serviceAccountName":"production-secret@example.com",
        "containers":[{"image":"secret.cloud/finance","env":[
            {"name":"FINANCIAL_TOKEN","value":"very_private_secret_value"},
            {"name":"SECRET_SOURCE","valueFrom":{"secretKeyRef":{"name":"secret-ref"}}},
        ]}],
    }}},
    "status":{"latestReadyRevisionName":"sbi-dashboard-00015-vix",
              "url":"https://real-secret-cloud-run-service.example"},
}
STAGE={
    "metadata":{"name":c.STAGE,"annotations":{"run.googleapis.com/ingress":"internal"}},
    "spec":{"template":{"spec":{
        "serviceAccountName":"isolated-staging@example.com",
        "containers":[{"image":"secret.cloud/stage","env":[]}],
    }}},
    "status":{"latestReadyRevisionName":"sbi-stage-00001"},
}
REGISTRY={"format":"DOCKER","name":"projects/hidden/locations/asia-south1/repositories/cloud-run-source-deploy"}
ACTIVE=[{"account":"private.owner@example.com","status":"ACTIVE"}]
SA=[{"email":"production-secret@example.com"},{"email":"staging-readonly@example.com"}]
APIS=[{"config":{"name":x}} for x in c.API_NAMES]


def fixture(*,stage=False, public=False, policy_denied=False, missing_gcp=False, same_identity=False):
    names=["sbi-dashboard"]
    if stage: names.append(c.STAGE)
    services=[{"metadata":{"name":n}} for n in names]
    copy_stage={
        "metadata":dict(STAGE["metadata"]),
        "spec":{"template":{"spec":dict(STAGE["spec"]["template"]["spec"])}},
        "status":dict(STAGE["status"]),
    }
    if same_identity:
        copy_stage["spec"]["template"]["spec"]["serviceAccountName"]=(
            "production-secret@example.com"
        )
    def respond(*args):
        if missing_gcp: return None
        prefix=tuple(args[:2])
        if prefix==("auth","list"): return ACTIVE
        if prefix==("projects","describe"): return {"projectId":c.PROJECT}
        if prefix==("run","services") and args[2]=="list":return services
        if prefix==("run","services") and args[2]=="describe":
            return PROD if args[3]=="sbi-dashboard" else copy_stage if args[3]==c.STAGE and stage else None
        if prefix==("run","services") and args[2]=="get-iam-policy":
            if policy_denied:return None
            return {"bindings":[{"role":"roles/run.invoker","members":["allUsers" if public else "user:private@example.com"]}]}
        if prefix==("iam","service-accounts"):return SA
        if prefix==("artifacts","repositories"):return REGISTRY
        if prefix==("artifacts","docker"):return [{"uri":"a"}, {"uri":"b"}]
        if prefix==("services","list"):return APIS
        return None
    return respond


class Phase2SafeCloudInventoryTests(unittest.TestCase):
    def run_collect(self,**opts):
        with mock.patch.object(c,"gcloud_json",side_effect=fixture(**opts)):
            return c.collect()

    def test_01_project_region_and_registry(self):
        p=self.run_collect()
        self.assertEqual(p["project"],"meghraj-reconciliation")
        self.assertEqual(p["region"],"asia-south1")
        self.assertTrue(p["registry"]["docker_format_verified"])

    def test_02_cloud_identity_boolean_only(self):
        p=self.run_collect()
        self.assertTrue(p["active_gcloud_identity_present"])
        self.assertNotIn("private.owner", c.render(p))

    def test_03_when_stage_missing_status_not_unverified_proof(self):
        p=self.run_collect()
        self.assertFalse(p["expected_services"][c.STAGE]["exists"])
        self.assertEqual(p["staging_account_distinct_from_dashboard_account"],"NOT_VERIFIED")

    def test_04_stage_present_and_distinct(self):
        p=self.run_collect(stage=True)
        self.assertTrue(p["staging_account_distinct_from_dashboard_account"])
        self.assertEqual(p["expected_services"][c.STAGE]["ingress"],"internal")

    def test_05_same_service_account_fails_distinct_gate(self):
        p=self.run_collect(stage=True,same_identity=True)
        self.assertFalse(p["staging_account_distinct_from_dashboard_account"])

    def test_06_public_invoker_principal_detected_without_exposure(self):
        p=self.run_collect(stage=True,public=True)
        self.assertEqual(p["staging_service_public_invoker_policy"],"PUBLIC_GRANT_PRESENT")
        self.assertNotIn("allUsers",c.render(p))

    def test_07_no_public_invoker_policy_still_not_finance_clear(self):
        p=self.run_collect(stage=True)
        self.assertEqual(p["staging_service_public_invoker_policy"],"NO_PUBLIC_GRANT_IN_SERVICE_POLICY")
        self.assertEqual(p["deployment_gates"]["inherited_and_resource_finance_iam_grants"],"NOT_VERIFIED")

    def test_08_policy_permission_denied_not_falsely_private(self):
        p=self.run_collect(stage=True,policy_denied=True)
        self.assertEqual(p["staging_service_public_invoker_policy"],"NOT_VERIFIED")

    def test_09_gcloud_unavailable_fails_closed(self):
        p=self.run_collect(missing_gcp=True)
        self.assertFalse(p["active_gcloud_identity_present"])
        self.assertFalse(p["project_access_verified"])
        self.assertEqual(p["expected_services"]["sbi-dashboard"]["exists"],"NOT_VERIFIED")

    def test_10_no_emails_or_raw_urls_in_report(self):
        p=self.run_collect(stage=True)
        text=c.render(p)
        for secret in ("@","secret.cloud","very_private_secret_value",
                       "production-secret","private.owner","https://"):
            self.assertNotIn(secret,text)

    def test_11_raw_finance_rows_would_be_rejected(self):
        with self.assertRaisesRegex(ValueError,"SENSITIVE"):
            c.render({"leak":"my_email@example.com"})

    def test_12_raw_api_token_would_be_rejected(self):
        with self.assertRaisesRegex(ValueError,"SENSITIVE"):
            c.render({"leak":"github_pat_leaked"})

    def test_13_production_cutover_never_auto_approved(self):
        p=self.run_collect(stage=True)
        self.assertEqual(p["deployment_gates"]["production_cutover"],"BLOCKED")
        self.assertEqual(p["deployment_gates"]["financial_database_writes_executed_by_script"],0)

    def test_14_registry_image_sample_not_release_digest(self):
        p=self.run_collect()
        self.assertEqual(p["registry"]["listed_image_sample_count_max_200"],2)
        self.assertEqual(p["registry"]["new_source_image_digest"],"NOT_VERIFIED")

    def test_15_only_allowlisted_service_names_published(self):
        p=self.run_collect()
        self.assertEqual(set(p["expected_services"]),set(c.PROD+(c.STAGE,)))

    def test_16_unsafe_ingress_string_cannot_be_injected(self):
        self.assertEqual(c.clean_ingress("finance-key-secret"),"NOT_VERIFIED")

    def test_17_git_origin_must_be_approved(self):
        with mock.patch.object(c,"invoke",side_effect=[
            (True,"/home/user/app\n"), (True,"https://evil.example/repo.git\n")
        ]):
            with self.assertRaisesRegex(RuntimeError,"NON_APPROVED_GITHUB_ORIGIN"):
                c.exact_repo_git_root()

    def test_18_git_https_and_ssh_remotes_supported(self):
        for remote in (
            "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git",
            "git@github.com:sujitkumardolui154-ctrl/meghraj-reconciliation.git"
        ):
            with mock.patch.object(c,"invoke",side_effect=[
                (True,"/home/user/app\n"),(True,remote+"\n")
            ]):
                self.assertEqual(c.exact_repo_git_root(),Path("/home/user/app"))

    def test_19_registered_secret_ref_only_counted(self):
        p=self.run_collect()
        self.assertEqual(p["expected_services"]["sbi-dashboard"]["secret_reference_count"],1)
        self.assertNotIn("secret-ref",c.render(p))

    def test_20_expected_apis_boolean_not_credentials(self):
        p=self.run_collect()
        self.assertTrue(all(p["api_enabled"][x] is True for x in c.API_NAMES))


    def test_21_reuse_existing_canonical_report_without_cloud_scan(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            location=Path(folder)/"SBI_PHASE2_GCP_READINESS_20261106T183155Z.json"
            report=self.run_collect(stage=True)
            location.write_text(c.render(report),encoding="utf-8")
            path, loaded=c.validate_existing_report_path(location, inventory_dir=folder)
            self.assertEqual(path,location)
            self.assertEqual(loaded,report)

    def test_22_existing_report_rejects_extra_sensitive_fields(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            location=Path(folder)/"SBI_PHASE2_GCP_READINESS_20261106T183155Z.json"
            report=self.run_collect()
            report["UNAPPROVED_FREE_TEXT"]="made-up-extra-field"
            location.write_text(c.render(report),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"UNEXPECTED_REPORT_FIELDS"):
                c.validate_existing_report_path(location,inventory_dir=folder)

    def test_23_existing_report_rejects_symlink(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            report=self.run_collect()
            good=Path(folder)/"original.json"
            good.write_text(c.render(report))
            link=Path(folder)/"SBI_PHASE2_GCP_READINESS_20261106T183155Z.json"
            link.symlink_to(good)
            with self.assertRaisesRegex(ValueError,"OUTSIDE_PRIVATE_INVENTORY"):
                c.validate_existing_report_path(link,inventory_dir=folder)

    def test_24_upload_uses_explicit_origin_main_refspec_in_shallow_clone(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            root=Path(folder)
            file=root/"SBI_PHASE2_GCP_READINESS_20261106T183155Z.json"
            file.write_text(c.render(self.run_collect()))
            called=[]
            def fake_invoke(argv, **kwargs):
                called.append(argv)
                return (False,"") if argv[:3]==["gh","auth","status"] else (True,"")
            with mock.patch.object(c,"invoke",side_effect=fake_invoke):
                branch,review=c.upload_to_github(root,file,file.name)
            self.assertTrue(branch.startswith("audit/sbi-phase2-gcp-readiness-"))
            self.assertIn("/compare/main...audit/",review)
            fetches=[args for args in called if len(args)>3 and args[3]=="fetch"]
            self.assertEqual(len(fetches),1)
            self.assertIn(
                "+refs/heads/main:refs/remotes/origin/main",fetches[0]
            )
            self.assertTrue(any("refs/remotes/origin/main^{commit}" in args
                                for args in called))
            staged=[args for args in called if "add" in args and "--" in args]
            self.assertEqual(len(staged),1)
            self.assertEqual(staged[0][-1],"audit/cloud/"+file.name)

    def test_25_error_if_refspec_fetch_does_not_succeed(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            file=Path(folder)/"SBI_PHASE2_GCP_READINESS_20261106T183155Z.json"
            file.write_text(c.render(self.run_collect()))
            with mock.patch.object(c,"invoke",return_value=(False,"")):
                with self.assertRaisesRegex(RuntimeError,"origin/main failed"):
                    c.upload_to_github(Path(folder),file,file.name)



if __name__=="__main__":
    unittest.main()
