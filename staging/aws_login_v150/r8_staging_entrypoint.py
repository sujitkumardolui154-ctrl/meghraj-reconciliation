"""R8 separate Firebase staging launcher — never use for SBI production.

This module is a separate Gunicorn entrypoint, NOT a change to the production
app.py entrypoint. It rejects existing production Auth project/origin/credentials
and private evidence volumes before importing the application.

No staging project or AWS instance is created by this code.
"""
from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

_GUARD = "SBI_R8_STAGING_ONLY_NONFINANCIAL"
_PROJECT_RE = re.compile(r"sbi-r8-staging-[a-z][a-z0-9-]{2,12}\Z")
_PROD_PROJECT = "meghraj-reconciliation"
_PROD_ORIGIN = "https://sbi-preview.13-232-241-221.sslip.io"


def refuse(message: str) -> None:
    raise RuntimeError("R8_STAGING_STARTUP_REFUSED: " + message)


def checked_settings() -> tuple[str, str, str]:
    if os.environ.get("SBI_R8_STAGING_MODE") != _GUARD:
        refuse("explicit nonproduction mode required")
    if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        refuse("emulator must be disabled for real signed-token staging")
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        refuse("service-account file path is forbidden; use isolated runtime identity")

    project = os.environ.get("SBI_R8_STAGING_FIREBASE_PROJECT_ID", "")
    if project == _PROD_PROJECT or not _PROJECT_RE.fullmatch(project):
        refuse("staging Firebase project must have the separate sbi-r8-staging prefix")
    for env_name in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        inherited = os.environ.get(env_name)
        if inherited and inherited != project:
            refuse("inherited Google project does not match staging project")

    origin = os.environ.get("SBI_R8_STAGING_SITE_ORIGIN", "")
    try:
        u = urlsplit(origin)
    except ValueError:
        refuse("invalid staging origin")
    if (
        origin == _PROD_ORIGIN
        or u.scheme != "https"
        or not u.hostname
        or not u.hostname.startswith("sbi-r8-staging-")
        or u.username or u.password or u.port is not None
        or u.path or u.query or u.fragment
        or origin != ("https://" + u.hostname)
    ):
        refuse("separate HTTPS staging origin is required")

    if os.environ.get("FIREBASE_WEB_API_KEY"):
        refuse("inherited production web API key is not allowed")
    staging_key = os.environ.get("SBI_R8_STAGING_FIREBASE_WEB_API_KEY", "")
    if not (20 <= len(staging_key) <= 120) or any(x.isspace() for x in staging_key):
        refuse("independently supplied staging web API key required")

    if os.environ.get("SBI_PAYMENT_EVIDENCE_DIR"):
        refuse("inherited evidence directory forbidden")
    if os.environ.get("SBI_PRIVATE_WORKSPACE_DB"):
        refuse("inherited workspace database forbidden")

    raw_dir = os.environ.get("SBI_R8_STAGING_EVIDENCE_DIR", "")
    p = Path(raw_dir)
    if (
        not p.is_absolute()
        or p.name.startswith(".")
        or not p.name.startswith("sbi-r8-staging-")
        or str(p.parent) not in ("/tmp", "/var/lib", "/srv")
        or p.is_symlink()
        or not p.is_dir()
    ):
        refuse("dedicated private staging evidence directory required")
    st = p.stat()
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700:
        refuse("staging evidence directory must belong to process UID and be mode 0700")

    # This is a development-only sanity check. Actual approved key identity is
    # a PRIVATE operations decision and cannot be proved from a public repo.
    raw_keys = os.environ.get("SBI_READONLY_QUARANTINE_SOL_KEYS", "")
    keys = [s.strip() for s in raw_keys.split(",")]
    if not keys or not all(re.fullmatch(r"[0-9]{1,12}", k) for k in keys):
        refuse("private quarantine SOL group registry is required")

    return project, origin, raw_dir


project, origin, data_dir = checked_settings()

# Set the legacy app's currently hard-coded defaults only in this separate
# process. The existing app.py and its production entrypoint stay unchanged.
os.environ["SBI_PAYMENT_EVIDENCE_DIR"] = data_dir
os.environ["FIREBASE_WEB_API_KEY"] = os.environ["SBI_R8_STAGING_FIREBASE_WEB_API_KEY"]

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
for folder in (
    ROOT / "dashboard_source",
    ROOT / "staging/aws_login_v150",
    ROOT / "staging/railway_public",
):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import dashboard_sessions as session_config

session_config.PROJECT = project
# No master user privileges are inherited from the production project.
session_config.MASTER_UID = "R8_STAGING_ADMIN_DISABLED"
session_config.MASTER_EMAIL = "disabled-r8@example.invalid"
session_config.ORIGINS.clear()
session_config.ORIGINS.add(origin)

import app as original_app

# app.py adds its production SITE_ORIGIN at import. Remove it in the R8
# staging-only process and keep exactly the owner-approved separate origin.
session_config.ORIGINS.clear()
session_config.ORIGINS.add(origin)
original_app.SITE_ORIGIN = origin

app = original_app.app
app.config.update(
    SBI_R8_STAGING_ONLY=True,
    SBI_R8_FINANCIAL_APPLY_LOCKED=True,
    SBI_R8_FIREBASE_PROJECT_ID=project,
    SBI_R8_STAGING_ORIGIN=origin,
)

@app.after_request
def mark_nonproduction(response):
    response.headers["X-SBI-Environment"] = "R8-STAGING-NONFINANCIAL"
    return response
