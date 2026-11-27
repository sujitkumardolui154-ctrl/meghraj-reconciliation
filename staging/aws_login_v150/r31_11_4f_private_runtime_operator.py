#!/usr/bin/env python3
"""DB-R31.11.4F controlled QA-only operator: default READ-ONLY preflight.

--execute requires explicit approval and interactive AWS terminal for TWO
existing approved Firebase test-account passwords (hidden getpass).
It signs in over Google's official API on the AWS host, verifies actual UID,
streams ID tokens only via stdin to ONE ephemeral nonroot isolated Docker
process. It neither writes QA financial rows nor touches production/Caddy.
The temporary external-egress network + ADC copy and container are removed.

No secret material in args, env, Docker build context, command output or
persistent files (except a short-lived protected ADC copy removed in finally).
We never run Firebase revoke or modify user claims.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import r31_11_4e_session_binding_readiness as gate
import r31_11_4c_firebase_bound_login_roles as roles
import r31_11_4a_isolated_postgres_provision as infra

SRC = Path(__file__).resolve().parents[2]
PG = "sbi-r3114-private-postgres"
DB = "sbi_r31_11_4_auth_qa_20261126"
QA_NET = "sbi-r3114-private-isolated"
STAGE = "sbi-r31-auth-private-qa"
STAGE_IMAGE = "sbi-r31-auth-qa:7a2298d93b6ace5977dc959acea3c7aa7c7ce4f0"
IMG = "sbi-r3114f-private-one-shot"
APP = "sbi-r3114f-private-probe"
EGRESS = "sbi-r3114f-firebase-egress"
MARKER = "sbi.r3114f.ephemeral"
EXACT_APPROVAL = "R3114F_TWO_REAL_FIREBASE_TESTS_QA_ONLY"
TEMP_DIR = Path("/home/ubuntu/sbi-r3114f-tmp-adc")
TEMP_ADC = TEMP_DIR / "adc.json"
HOST_ADC = Path.home()/".config/gcloud/application_default_credentials.json"
SECRETS = Path("/home/ubuntu/sbi-r3114c-app-secrets")
DFILE = SRC/"staging/aws_login_v150/Dockerfile.r31_11_4f_private_one_shot_qa"
EXPECTED_LINES = frozenset({
    "DB_R31_11_4F_REAL_FIREBASE_TWO_TOKEN_IDENTITIES=PASS_VERIFIED",
    "DB_R31_11_4F_ANONYMOUS_AND_INVALID_COOKIE=DENIED_PASS",
    "DB_R31_11_4F_TENANT_A_FIREBASE_SESSION_TO_PG=PASS_READONLY",
    "DB_R31_11_4F_TENANT_B_FIREBASE_SESSION_TO_PG=PASS_READONLY",
    "DB_R31_11_4F_FORGED_UID_AND_PG_ROLE=IGNORED_PASS",
    "DB_R31_11_4F_FINANCIAL_WRITE_ENDPOINT=DENIED_PASS",
    "DB_R31_11_4F_RUNTIME_MODE=ONE_SHOT_FLASK_IN_PROCESS_NO_HTTP_LISTENER",
    "DB_R31_11_4F_REAL_REVOKED_OR_EXPIRED_SESSION=NOT_TESTED",
    "DB_R31_11_4F_EXTERNAL_MTLS_HTTPS=PENDING",
    "DB_R31_11_4F_FINANCIAL_APPLY=LOCKED",
    "DB_R31_11_4F_R3112=QUARANTINED",
    "DB_R31_11_4F_RELEASE=PRODUCTION_BLOCKED",
})


class Blocked(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Blocked(code)


def docker(*args, stdin=None, timeout=45):
    try:
        p=subprocess.run(["sudo","-n","docker",*args],input=stdin,
                         text=True,capture_output=True,check=False,
                         timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise Blocked("DOCKER_COMMAND_UNAVAILABLE") from None
    if p.returncode:
        raise Blocked("DOCKER_COMMAND_FAILED")
    return p.stdout.strip()


def source_guard(expected):
    require(type(expected) is str and len(expected)==40
            and all(x in "0123456789abcdef" for x in expected),
            "SOURCE_SHA_INVALID")
    current=subprocess.run(["git","-C",str(SRC),"rev-parse","HEAD"],
                           capture_output=True,text=True,check=False)
    clean=subprocess.run(["git","-C",str(SRC),"status","--porcelain"],
                         capture_output=True,text=True,check=False)
    require(current.returncode==0 and clean.returncode==0
            and current.stdout.strip()==expected
            and clean.stdout.strip()=="","SOURCE_REVISION_OR_FILES_CHANGED")
    require(DFILE.is_file() and not DFILE.is_symlink()
            and (SRC/"staging/aws_login_v150/r31_11_4f_private_session_probe.py").is_file(),
            "QA_CANDIDATE_SOURCE_MISSING")


def baseline():
    text=docker("exec",PG,"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
               "-U","postgres","-d",DB,"-c",
               """BEGIN READ ONLY;
               SELECT json_build_object(
                 'db',current_database(),
                 'mappings',(SELECT count(*) FROM r311_auth.role_owner_map),
                 'rows',(SELECT count(*) FROM sbi.import_batches)+
                        (SELECT count(*) FROM sbi.payment_source_rows)+
                        (SELECT count(*) FROM sbi.payments)+
                        (SELECT count(*) FROM sbi.payment_source_status_v1)
                 )::text;
               COMMIT;""")
    try:
        data=json.loads(text)
    except (ValueError,TypeError):
        raise Blocked("QA_BASELINE_UNEXPECTED") from None
    require(data=={"db":DB,"mappings":2,"rows":0},"QA_BASELINE_UNEXPECTED")
    return data


def no_preexisting_resources():
    for name in (APP,EGRESS):
        try:
            if name == APP:
                result=subprocess.run(["sudo","-n","docker","container","inspect",name],
                                      capture_output=True,text=True,check=False)
            else:
                result=subprocess.run(["sudo","-n","docker","network","inspect",name],
                                      capture_output=True,text=True,check=False)
            require(result.returncode==1,"QA_PRIOR_RESOURCES_REQUIRE_REVIEW")
        except OSError:
            raise Blocked("DOCKER_COMMAND_UNAVAILABLE") from None
    require(not TEMP_DIR.exists() and not TEMP_DIR.is_symlink(),
            "QA_PRIOR_TEMP_SECRETS_REQUIRE_REVIEW")


def firebase_key_from_existing_stage():
    raw=docker("inspect",STAGE)
    try:
        info=json.loads(raw)[0]
    except (ValueError,TypeError,IndexError,KeyError):
        raise Blocked("QA_EXISTING_STAGE_NOT_VERIFIED") from None
    require(info.get("State",{}).get("Running") is True
            and info.get("Config",{}).get("Image")==STAGE_IMAGE
            and info.get("HostConfig",{}).get("PortBindings") in (None,{}),
            "QA_EXISTING_STAGE_NOT_VERIFIED")
    key=docker("exec",STAGE,"python3","-c",
               "import os;print(os.environ.get('FIREBASE_WEB_API_KEY',''))")
    require(20<=len(key)<=256 and key.isascii() and " " not in key,
            "QA_EXISTING_FIREBASE_API_KEY_UNAVAILABLE")
    return key


def sign_in(key,email,password):
    require(sys.stdin.isatty(),"QA_INTERACTIVE_TERMINAL_REQUIRED")
    require(3<=len(email)<=254 and 1<=len(password)<=512,
            "QA_TEST_ACCOUNT_INPUT_INVALID")
    uri=("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
         +urllib.parse.quote(key,safe=""))
    body=json.dumps({"email":email,"password":password,
                     "returnSecureToken":True}).encode("utf-8")
    req=urllib.request.Request(uri,data=body,method="POST",
                               headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=35) as resp:
            result=json.loads(resp.read(26000))
    except (urllib.error.HTTPError,urllib.error.URLError,
            OSError,TimeoutError,ValueError):
        raise Blocked("QA_FIREBASE_PASSWORD_SIGNIN_FAILED") from None
    require(type(result) is dict and type(result.get("idToken")) is str
            and 200<=len(result["idToken"])<=12000
            and type(result.get("localId")) is str,
            "QA_FIREBASE_SIGNIN_RESPONSE_UNEXPECTED")
    return result["idToken"],result["localId"]


def tokens_from_two_real_test_users(key,approved):
    require(len(approved)==2 and approved[0]["uid"]!=approved[1]["uid"],
            "QA_APPROVED_USERS_NOT_DISTINCT")
    sdk,app=roles._admin_api()
    tokens=[]
    for i,person in enumerate(approved):
        print("DB_R31_11_4F_SIGNIN_TEST_"+("A" if i==0 else "B")+
              "=PASSWORD_PROMPT_HIDDEN",flush=True)
        password=getpass.getpass("Approved Firebase Test "+("A" if i==0 else "B")+
                                " password (hidden): ")
        try:
            token,uid=sign_in(key,person["email"],password)
        finally:
            password=None
        require(uid==person["uid"],"QA_FIREBASE_SIGNIN_UID_MISMATCH")
        try:
            real=sdk.verify_id_token(token,check_revoked=True,app=app)
        except Exception:
            raise Blocked("QA_REAL_FIREBASE_ID_TOKEN_VERIFICATION_FAILED") from None
        require(real.get("uid")==person["uid"],
                "QA_REAL_FIREBASE_ID_TOKEN_UID_MISMATCH")
        tokens.append(token)
        print("DB_R31_11_4F_TEST_"+("A" if i==0 else "B")+
              "_PASSWORD_SIGNIN=PASS_REAL_FIREBASE",flush=True)
    return tokens


def host_adc_ready():
    require(HOST_ADC.is_file() and not HOST_ADC.is_symlink()
            and HOST_ADC.stat().st_uid==os.geteuid()
            and HOST_ADC.stat().st_mode & 0o077 == 0
            and 1<=HOST_ADC.stat().st_size<=32768,
            "QA_AWS_GOOGLE_ADC_FILE_NOT_RESTRICTED")


def sudo(*args,timeout=30):
    try:
        p=subprocess.run(["sudo","-n",*args],capture_output=True,
                         text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Blocked("QA_PRIVILEGED_COMMAND_UNAVAILABLE") from None
    if p.returncode:
        raise Blocked("QA_PRIVILEGED_COMMAND_FAILED")


def prepare_temp_adc():
    require(not TEMP_DIR.exists() and not TEMP_DIR.is_symlink(),
            "QA_TEMP_ADC_ALREADY_EXISTS")
    sudo("install","-d","-m","0700","-o","10001","-g","10001",str(TEMP_DIR))
    sudo("install","-m","0600","-o","10001","-g","10001",
         str(HOST_ADC),str(TEMP_ADC))
    out=subprocess.run(["sudo","-n","stat","-c","%a %u:%g %F","--",
                        str(TEMP_DIR),str(TEMP_ADC)],capture_output=True,
                       text=True,check=False)
    require(out.returncode==0 and out.stdout.strip().splitlines()
            ==["700 10001:10001 directory","600 10001:10001 regular file"],
            "QA_TEMP_ADC_METADATA_INVALID")


def make_image(expected):
    name=IMG+":"+expected[:12]
    docker("build","--pull=false","--no-cache","-f",str(DFILE),
           "--build-arg","SBI_SOURCE_SHA="+expected,
           "-t",name,str(SRC),timeout=360)
    revision=docker("image","inspect","--format",
                    "{{index .Config.Labels \"org.opencontainers.image.revision\"}}",
                    name)
    require(revision==expected,"QA_IMAGE_REVISION_UNVERIFIED")
    return name


def create_private_runtime(image_name):
    docker("network","create","--driver","bridge","--opt",
           "com.docker.network.bridge.enable_icc=false",
           "--label",MARKER+"=true",EGRESS)
    # DO NOT publish ports, mount Docker socket, or connect Caddy.
    # Only a disposable egress bridge plus the existing isolated QA DB bridge.
    docker("create","--name",APP,"-i",
           "--label",MARKER+"=true",
           "--network",EGRESS,
           "--user","10001:10001",
           "--read-only","--cap-drop","ALL",
           "--security-opt","no-new-privileges",
           "--pids-limit","64","--memory","512m","--cpus","1",
           "--tmpfs","/tmp:rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700",
           "--mount","type=bind,source="+str(SECRETS)+",target=/run/secrets,readonly",
           "--mount","type=bind,source="+str(TEMP_ADC)+",target=/run/firebase/adc.json,readonly",
           "--env","GOOGLE_APPLICATION_CREDENTIALS=/run/firebase/adc.json",
           "--env","SBI_R31_PRIVATE_STAGING_ENABLED=isolated-ownerqa-firebase-csrf-v1",
           "--env","SBI_R31_11_4_RUNTIME_ENABLED=private-firebase-rls-auth-acceptance-v1",
           image_name)
    docker("network","connect",QA_NET,APP)
    candidate=json.loads(docker("inspect",APP))[0]
    config=candidate.get("Config",{})
    host=candidate.get("HostConfig",{})
    networks=candidate.get("NetworkSettings",{}).get("Networks",{})
    mounts=candidate.get("Mounts",[])
    require(candidate.get("State",{}).get("Running") is False
            and set(networks)=={EGRESS,QA_NET}
            and host.get("PortBindings") in (None,{})
            and host.get("Privileged") is False
            and host.get("ReadonlyRootfs") is True
            and set((m.get("Source"),m.get("Destination"),m.get("RW"))
                    for m in mounts)=={
                (str(SECRETS),"/run/secrets",False),
                (str(TEMP_ADC),"/run/firebase/adc.json",False)}
            and config.get("User")=="10001:10001"
            and config.get("Labels",{}).get(MARKER)=="true"
            and not config.get("ExposedPorts"),
            "QA_EPHEMERAL_CONTAINER_NOT_ISOLATED")
    print("DB_R31_11_4F_PRIVATE_CANDIDATE=PASS_NO_PUBLIC_PORTS",flush=True)


def run_one_shot(tokens):
    require(type(tokens) is list and len(tokens)==2,
            "QA_PRIVATE_TOKEN_PAYLOAD_INVALID")
    payload=json.dumps({"tokens":tokens},separators=(",",":"))
    try:
        process=subprocess.run(
            ["sudo","-n","docker","start","-ai",APP],
            input=payload,text=True,capture_output=True,check=False,
            timeout=240)
    except (OSError,subprocess.TimeoutExpired):
        raise Blocked("QA_EPHEMERAL_TEST_RUNTIME_UNAVAILABLE") from None
    seen=set(process.stdout.splitlines())
    # No unfiltered stdout/stderr. Only allowlisted exact status receipts.
    for row in EXPECTED_LINES:
        if row in seen:
            print(row,flush=True)
    require(process.returncode==0 and EXPECTED_LINES.issubset(seen)
            and not any(row.startswith("STOP=") for row in seen),
            "QA_REAL_SESSION_ACCEPTANCE_FAILED")
    print("DB_R31_11_4F_REAL_SESSIONS=PASS_TWO_FIREBASE_UID_BOUND_TO_PG",flush=True)


def clean_exact_resources(image_name=None):
    # Cleanup owns only exact DB-R31.11.4F names. NEVER touch PG, qa network,
    # Firebase approval receipt, source secret bundle, production containers.
    # Never dump, change or truncate any database.
    errors=[]
    # Resource names may only be cleaned if absent or bearing our exact QA
    # marker; never delete a same-named foreign container/network.
    for kind,name in (("container",APP),("network",EGRESS)):
        try:
            p=subprocess.run(["sudo","-n","docker",kind,"inspect",name],
                             capture_output=True,text=True,check=False,timeout=20)
            if p.returncode==0:
                parsed=json.loads(p.stdout)
                item=parsed[0]
                labels=(item.get("Config",{}).get("Labels",{})
                        if kind=="container"
                        else item.get("Labels",{}))
                if labels.get(MARKER)!="true":
                    raise Blocked("QA_RESOURCE_OWNERSHIP_NOT_PROVEN")
            elif p.returncode!=1:
                raise Blocked("QA_RESOURCE_INSPECTION_UNAVAILABLE")
        except (ValueError,TypeError,IndexError,OSError,subprocess.TimeoutExpired):
            raise Blocked("QA_RESOURCE_INSPECTION_UNAVAILABLE") from None
    for cmd in (
        ["sudo","-n","docker","rm","-f",APP],
        ["sudo","-n","docker","network","rm",EGRESS],
        ["sudo","-n","rm","-f","--",str(TEMP_ADC)],
        ["sudo","-n","rmdir","--",str(TEMP_DIR)],
    ):
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,
                             check=False,timeout=40)
            # Missing resources are normal only if the resource was never
            # created in this invocation; exact existence is checked later.
        except (OSError,subprocess.TimeoutExpired):
            errors.append(cmd[-1])
    if image_name is not None:
        try:
            subprocess.run(["sudo","-n","docker","image","rm",image_name],
                           capture_output=True,text=True,check=False,timeout=45)
        except (OSError,subprocess.TimeoutExpired):
            pass
    if (TEMP_DIR.exists() or TEMP_DIR.is_symlink()):
        errors.append("adc")
    for kind,name in (("container",APP),("network",EGRESS)):
        p=subprocess.run(["sudo","-n","docker",kind,"inspect",name],
                         capture_output=True,text=True,check=False)
        if p.returncode != 1:
            errors.append(kind)
    require(not errors,"QA_TEMP_RESOURCE_CLEANUP_REVIEW_REQUIRED")
    print("DB_R31_11_4F_EPHEMERAL_RESOURCES=REMOVED",flush=True)


def execute(expected):
    # Permission to execute approved ONLY with explicit one-time operator flag.
    # The 4E gate uses Firebase Admin read-only access plus SQL SELECT, so
    # no real test accounts / data / roles are modified.
    approved=roles._approved_users()
    key=firebase_key_from_existing_stage()
    host_adc_ready()
    tokens=None
    image=None
    before=infra.caddy_fingerprint()
    entered=False
    try:
        entered=True
        # Build the image and finish all Docker networking BEFORE acquiring
        # short-lived Firebase password-login tokens. /auth/session requires
        # auth_time within five minutes, so never spend Docker build time
        # after asking for Test A/B passwords.
        image=make_image(expected)
        prepare_temp_adc()
        create_private_runtime(image)
        tokens=tokens_from_two_real_test_users(key,approved)
        run_one_shot(tokens)
    finally:
        tokens=None
        if entered:
            clean_exact_resources(image)
        require(infra.caddy_fingerprint()==before,
                "QA_CADDY_FINGERPRINT_CHANGED")
        baseline()
        print("DB_R31_11_4F_AFTER_DB_ROWS=ZERO_OWNER_MAPS_TWO",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="QA-only private one-shot 4F")
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--approve",default="")
    args=parser.parse_args(argv)
    print("=== DB-R31.11.4F GUARDED PRIVATE REAL SESSION QA ===",flush=True)
    try:
        source_guard(args.source_sha)
        gate.run_checks()
        baseline()
        no_preexisting_resources()
        print("DB_R31_11_4F_READONLY_PREFLIGHT=PASS",flush=True)
        if not args.execute:
            print("DB_R31_11_4F_MODE=READONLY_PLAN_NO_DOCKER_CHANGES",flush=True)
            return 0
        require(args.approve==EXACT_APPROVAL,
                "QA_EXPLICIT_APPROVAL_MISSING")
        require(sys.stdin.isatty(),"QA_INTERACTIVE_TERMINAL_REQUIRED")
        execute(args.source_sha)
        print("DB_R31_11_4F_MODE=APPROVED_EPHEMERAL_QA_COMPLETED",flush=True)
        return 0
    except Exception:
        # No raw exception messages: OAuth, Docker and private network errors
        # might expose credentials, egress config or Firebase account IDs.
        print("STOP=DB_R31_11_4F_PRIVATE_ACCEPTANCE_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4F_EXTERNAL_MTLS_HTTPS=PENDING",flush=True)
        print("DB_R31_11_4F_RUNTIME_ADAPTER=NOT_DEPLOYED_TO_PUBLIC_OR_STAGING",flush=True)
        print("DB_R31_11_4F_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4F_R3112=QUARANTINED",flush=True)
        print("DB_R31_11_4F_RELEASE=PRODUCTION_BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
