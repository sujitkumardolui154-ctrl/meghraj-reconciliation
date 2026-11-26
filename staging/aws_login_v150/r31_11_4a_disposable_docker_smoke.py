#!/usr/bin/env python3
"""R31.11.4A disposable Docker initialization/restore smoke test.

RESTRICTED TO GitHub hosted runner with R3114A_DISPOSABLE_CI=YES and a known
empty Docker daemon. No AWS login, Firebase user, real financial data, public
ports or persistent deployment. Uses an isolated Docker internal bridge and
unique disposable database/volume/secret names, then tears down those names.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

import r31_11_4a_isolated_postgres_provision as p


def main():
    if os.getenv("R3114A_DISPOSABLE_CI") != "YES" or not os.getenv("GITHUB_RUN_ID"):
        raise SystemExit("STOP=DISPOSABLE_CI_ONLY")
    identifier = os.environ["GITHUB_RUN_ID"]
    if re.fullmatch(r"[0-9]{1,20}",identifier) is None:
        raise SystemExit("STOP=CI_RUN_ID_INVALID")
    p.NAME = "ci-r3114a-pg-" + identifier
    p.NETWORK = "ci-r3114a-net-" + identifier
    p.VOLUME = "ci-r3114a-volume-" + identifier
    p.DATABASE = "ci_r3114a_empty_" + identifier
    p.PROBE_DB = "ci_r3114a_restore_" + identifier
    p.BASE_ALLOWED = frozenset(("postgres", "template0","template1",p.DATABASE))
    # Do not use the default AWS secret directory even in CI.
    with tempfile.TemporaryDirectory(prefix="r3114a-ci-") as root:
        p.SECRET_DIR = Path(root)/"private"
        p.PASSWORD_PATH = p.SECRET_DIR/"init-password"
        # Official image is downloaded in a dedicated CI step. Do not pull
        # from Python, pin to the exact locally available image digest.
        image_id = p.docker("image","inspect","postgres:16","--format","{{.Id}}")
        if re.fullmatch(r"sha256:[0-9a-f]{64}",image_id) is None:
            raise SystemExit("STOP=DISPOSABLE_IMAGE_SHA_NOT_PINNED")
        local_version=p.docker("run","--rm","--network","none",
                               "--entrypoint","postgres","postgres:16","-V")
        if not re.match(r"^postgres \(PostgreSQL\) 16(?:\.|\s|$)",local_version):
            raise SystemExit("STOP=DISPOSABLE_POSTGRES_MAJOR_NOT_16")
        uid = p.docker("run","--rm","--network","none",
                       "--entrypoint","id","postgres:16","-u","postgres")
        gid = p.docker("run","--rm","--network","none",
                       "--entrypoint","id","postgres:16","-g","postgres")
        if not (uid.isdecimal() and gid.isdecimal()):
            raise SystemExit("STOP=DISPOSABLE_UID_NOT_NUMERIC")
        resources = []
        try:
            p._new_secret(int(uid),int(gid))
            print("DB_R31_11_4A_CI_POSTGRES_SECRET_UID0600=PASS",flush=True)
            p.docker("network","create","--driver","bridge","--internal",
                     "--label",f"{p.LABEL}=true",p.NETWORK)
            resources.append(("network",p.NETWORK))
            p.docker("volume","create","--label",f"{p.LABEL}=true",p.VOLUME)
            resources.append(("volume",p.VOLUME))
            p.docker(*p._run_args(image_id),timeout=45)
            resources.append(("container",p.NAME))
            if not p._ready():
                raise RuntimeError("DISPOSABLE_PG_NOT_READY")
            if not p._exact_topology(image_id):
                raise RuntimeError("DISPOSABLE_TOPOLOGY_NOT_PRIVATE")
            print("DB_R31_11_4A_CI_ACTUAL_CONTAINER_ISOLATION=PASS",flush=True)
            p._catalog()
            p._empty_schema_restore_drill()
            p._catalog()
            print("DB_R31_11_4A_CI_EMPTY_PG_INITIALIZE_AND_RESTORE=PASS",
                  flush=True)
        finally:
            # Cleanup is ONLY on the disposable GitHub runner and unique names.
            # There is deliberately NO cleanup of AWS partial provision attempts.
            for kind,name in reversed(resources):
                try:
                    if kind=="container":
                        p.docker("rm","-f",name,timeout=35)
                    elif kind=="volume":
                        p.docker("volume","rm",name,timeout=35)
                    else:
                        p.docker("network","rm",name,timeout=35)
                except (p.ProvisionBlocked, OSError):
                    print("DB_R31_11_4A_CI_DISPOSABLE_CLEANUP=REVIEW_REQUIRED",
                          flush=True)
                    raise
    print("DB_R31_11_4A_CI_FINANCIAL_APPLY=LOCKED",flush=True)


if __name__=="__main__":
    main()
