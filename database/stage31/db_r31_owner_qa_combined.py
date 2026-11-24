#!/usr/bin/env python3
"""Single safe AWS runner for DB-R31 persistent isolated QA + parser/report parity.

Creates ONLY an isolated schema-only QA clone within sbi-synthetic-postgres-38-31,
never edits sbi_reconciliation_main or the running FT04 database/containers.
No network ports, no deployment. Each test run writes only synthetic data to
new QA clone and verifies repeat imports do not add rows.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess

PG="sbi-synthetic-postgres-38-31"
NETWORK="sbi-synthetic-isolated-38-31"
SOURCE="sbi_ft04g_clean_0e858f93"
DB="sbi_r31_owner_qa_20261125"
APP="sbi-pr129-modern-release-final"
ROLES={"ingest":"sbi_r31_ownerqa_ingest","report":"sbi_r31_ownerqa_report"}
ROOT=Path(__file__).resolve().parent
PRIVATE=Path("/home/ubuntu/sbi-db-management/db-r31-ownerqa")
QA_SQL=ROOT/"db_r31_owner_persistent_qa.sql"

def run(args, *, source=None, timeout=90):
    p=subprocess.run(args,input=source,text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        lines=(p.stderr or p.stdout).splitlines()
        errors=[x for x in lines if any(
            k in x for k in ("ERROR:","FATAL:","Traceback","AssertionError","STOP="))]
        reason="\n".join(errors[:8]) if errors else "\n".join(lines[-10:])
        raise RuntimeError(reason[-1000:] or "COMMAND_FAILED")
    return p.stdout.strip()

def docker(*args,**kw):
    return run(["sudo","-n","docker",*args],**kw)

def inspect(name):
    return json.loads(docker("inspect",name))[0]

def psql(database,sql):
    return docker("exec","-i",PG,"psql","-X","-qAt",
                 "-v","ON_ERROR_STOP=1","-U","postgres","-d",database,
                 "-f","-",source=sql,timeout=45).strip()

def quote(s):
    return "'"+s.replace("'","''")+"'"

def db_exists(db):
    return psql("postgres",
        "SELECT count(*) FROM pg_database WHERE datname="+quote(db)+";")=="1"

def count_rows(db):
    return psql(db,"""SELECT
       (SELECT count(*) FROM sbi.import_batches)::text||'|'||
       (SELECT count(*) FROM sbi.payment_source_rows)::text||'|'||
       (SELECT count(*) FROM sbi.payments)::text||'|'||
       (SELECT count(*) FROM sbi.invoices)::text;""")

def validate_safety():
    n=json.loads(docker("network","inspect",NETWORK))[0]
    pg=inspect(PG)
    names={x.get("Name") for x in (n.get("Containers") or {}).values()}
    allowed={PG,"sbi-ft04-payment-staging-overlay",
              "sbi-ft04-payment-staging-v2","sbi-ft04-payment-outbox-v2"}
    if not (n.get("Internal") is True and PG in names and
            names<=allowed and pg["State"]["Status"]=="running" and
            set((pg["NetworkSettings"].get("Networks") or {}))=={NETWORK}
            and not pg["HostConfig"].get("PortBindings")):
        raise RuntimeError("QA_NETWORK_ISOLATION_FAILED")
    for name in names:
        c=inspect(name)
        if c["State"]["Status"]!="running" or c["HostConfig"].get("PortBindings") or any(
            m.get("Destination","").startswith("/var/run/postgresql")
            for m in c.get("Mounts") or []):
            raise RuntimeError("QA_CONTAINER_MOUNT_OR_PUBLIC_PORT_UNSAFE")
    if db_exists("sbi_reconciliation_main"):
        raise RuntimeError("PRODUCTION_DATABASE_VISIBLE_IN_TEST_INSTANCE")
    if not db_exists(SOURCE):
        raise RuntimeError("FT04_SOURCE_QA_DATABASE_MISSING")
    if not QA_SQL.is_file() or not ROOT.joinpath(
         "db_r31_owner_qa_runtime.py").is_file():
        raise RuntimeError("PINNED_QA_SOURCE_FILES_MISSING")
    print("DB_R31_PHYSICAL_QA_ISOLATION=PASS",flush=True)

def bootstrap_database():
    if not db_exists(DB):
        psql("postgres","CREATE DATABASE "+DB+";")
        print("DB_R31_SCHEMA_ONLY_QA_DATABASE=CREATED",flush=True)
    has_table=psql(DB,"SELECT to_regclass('sbi.import_batches') IS NOT NULL;")
    if has_table=="f":
        # stream schema, never data or production permissions, from the
        # already isolated FT04 QA DB into the separate R31 QA DB.
        dumped=docker("exec",PG,"pg_dump","-U","postgres","--schema-only",
                      "--no-owner","--no-acl","--no-comments","-d",SOURCE,
                      timeout=60)
        if "CREATE TABLE" not in dumped or "CREATE SCHEMA sbi" not in dumped:
            raise RuntimeError("SOURCE_QA_SCHEMA_DUMP_INCOMPLETE")
        psql(DB,dumped)
        print("DB_R31_QA_SCHEMA_ONLY_CLONE=PASS",flush=True)
    elif has_table!="t":
        raise RuntimeError("R31_QA_SCHEMA_IDENTITY_AMBIGUOUS")
    if (psql(DB,"SELECT to_regclass('sbi.payment_received_source_v1') IS NOT NULL;")
        !="t"):
        raise RuntimeError("R31_2_QA_SOURCE_VIEW_NOT_PRESENT")
    old=psql(DB,"""SELECT count(*) FROM pg_constraint
       WHERE conrelid='sbi.import_batches'::regclass AND contype='u'
       AND pg_get_constraintdef(oid) LIKE
       'UNIQUE (source_system, source_kind, source_sha256)%';""")
    owned=psql(DB,"""SELECT count(*) FROM pg_indexes
       WHERE schemaname='sbi' AND
       indexname IN ('ux_r31_qa_owned_source_sha',
                     'ux_r31_qa_legacy_source_sha');""")
    if (old,owned)==("1","0"):
        if count_rows(DB)!="0|0|0|0":
            raise RuntimeError("QA_NEW_SCHEMA_REQUIRES_EMPTY_CLONE")
        print(psql(DB,QA_SQL.read_text()),flush=True)
    elif (old,owned)==("0","2"):
        print("DB_R31_OWNER_QA_SCHEMA=ALREADY_PREPARED",flush=True)
    else:
        raise RuntimeError("R31_QA_SCHEMA_PARTIALLY_MIGRATED_REVIEW_REQUIRED")

def credentials():
    os.umask(0o077)
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if PRIVATE.is_symlink() or (PRIVATE.stat().st_mode & 0o077):
        raise RuntimeError("QA_CREDENTIAL_DIRECTORY_NOT_PRIVATE")
    paths={}
    for kind,role in ROLES.items():
        path=PRIVATE/(kind+".env")
        if path.exists():
            if path.is_symlink() or (path.stat().st_mode & 0o077):
                raise RuntimeError("QA_CREDENTIAL_FILE_UNSAFE")
            items=dict(x.strip().split("=",1) for x in path.read_text().splitlines() if "=" in x)
            if items.get("PGDATABASE")!=DB or items.get("PGUSER")!=role or \
                items.get("PGHOST")!=PG or not items.get("PGPASSWORD"):
                raise RuntimeError("QA_CREDENTIAL_FILE_IDENTITY_MISMATCH")
            password=items["PGPASSWORD"]
        else:
            password=secrets.token_hex(32)
            data=f"PGHOST={PG}\nPGPORT=5432\nPGDATABASE={DB}\nPGUSER={role}\nPGPASSWORD={password}\n"
            fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w") as f:f.write(data)
        paths[kind]=(path,password)
    return paths

def configure_roles(passwords):
    sql=["REVOKE ALL ON DATABASE "+DB+" FROM PUBLIC;",
         "REVOKE ALL ON SCHEMA sbi FROM PUBLIC;"]
    for kind,role in ROLES.items():
        pwd=passwords[kind][1]
        sql.append(f"""DO $r$ BEGIN
         IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname={quote(role)})
         THEN CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB
              NOCREATEROLE NOREPLICATION NOINHERIT;
         END IF; END $r$;
         ALTER ROLE {role} PASSWORD {quote(pwd)};
         GRANT CONNECT ON DATABASE {DB} TO {role};
         GRANT USAGE ON SCHEMA sbi TO {role};""")
    ingest=ROLES["ingest"]
    reader=ROLES["report"]
    sql += [
      f"""GRANT SELECT, INSERT ON
       sbi.import_batches, sbi.payment_source_rows,
       sbi.payments, sbi.payment_source_status_v1 TO {ingest};""",
      f"""GRANT SELECT ON sbi.payment_received_source_v1 TO {reader};""",
      f"""REVOKE ALL ON sbi.import_batches,sbi.payment_source_rows,
       sbi.payments,sbi.payment_source_status_v1 FROM {reader};""",
    ]
    psql(DB,"\n".join(sql))
    print("DB_R31_DISTINCT_RESTRICTED_QA_ROLES=PASS",flush=True)

def run_app(role,path,image):
    args=["run","--rm","--network",NETWORK,"--read-only",
          "--tmpfs","/tmp:rw,nosuid,size=64m",
          "--cap-drop=ALL","--security-opt","no-new-privileges",
          "--pids-limit","128","--memory","512m",
          "--mount",f"type=bind,src={ROOT},dst=/qa-code,readonly",
          "--env-file",str(path),
          "-e","PYTHONDONTWRITEBYTECODE=1",
          "-e","PYTHONPATH=/qa-code:/app",
          "--entrypoint","python3",image,
          "-B","/qa-code/db_r31_owner_qa_runtime.py",role]
    output=docker(*args,timeout=100)
    print(output,flush=True)

def main():
    print("=== DB-R31 OWNER SOURCE PERSISTENT QA COMBINED ===",flush=True)
    validate_safety()
    live=inspect(APP)
    img=live.get("Image")
    if not isinstance(img,str) or not img.startswith("sha256:"):
        raise RuntimeError("LIVE_IMAGE_DIGEST_UNVERIFIED")
    ft04_before=count_rows(SOURCE)
    bootstrap_database()
    passwords=credentials()
    configure_roles(passwords)
    run_app("writer",passwords["ingest"][0],img)
    run_app("reader",passwords["report"][0],img)
    ft04_after=count_rows(SOURCE)
    if ft04_before!=ft04_after:
        raise RuntimeError("FT04_QA_ROW_COUNTS_CHANGED_DURING_TEST")
    print("DB_R31_FT04_QA_EXISTING_ROW_COUNTS_UNCHANGED=PASS",flush=True)
    print("DB_R31_PRODUCTION_DATABASE_WRITES=NONE_BY_TEST",flush=True)
    print("DB_R31_REAL_FIREBASE_AUTH=NOT_TESTED",flush=True)
    print("DB_R31_PRODUCTION_ROLE_GRANTS=NONE",flush=True)
    print("DB_R31_RELEASE_STATUS=ISOLATED_PERSISTENT_SOURCE_QA_ONLY",flush=True)
    print("=== DB-R31 COMBINED OWNER QA COMPLETE ===",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("DB_R31_COMBINED_OWNER_QA=REVIEW_REQUIRED",flush=True)
        print("STOP="+str(exc)[:900],flush=True)
        raise SystemExit(1)
