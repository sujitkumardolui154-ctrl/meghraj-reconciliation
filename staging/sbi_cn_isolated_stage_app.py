"""Isolated *read-only* Credit Note staging app factory.

NOT imported or registered by dashboard_source/production_gateway.py.
No Firestore, GCS, AWS or financial database client is constructed.
The service is safe to test locally with synthetic uploads. A genuine
read-only DB identity and IAM audit are prerequisites for real DB integration.

Usage for an operator's PRIVATE isolated staging test (not a deployment):
    SBI_CN_ISOLATED_STAGE=1 SBI_CN_STAGING_PREVIEW_ENABLED=true \
      gunicorn 'staging.sbi_cn_isolated_stage_app:create_app()' \
      --bind 127.0.0.1:18089
"""
import os
import sys
from pathlib import Path

from flask import Flask, jsonify

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "dashboard_source", ROOT / "backend_source"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from dashboard_sessions import install_sessions
from sbi_cn_staging_preview import create_credit_note_staging_blueprint
from credit_note_import_file import parse_credit_note_upload, error_report_csv
from credit_note_registry_readonly import _blocked_preview

STAGE_ENV = "SBI_CN_ISOLATED_STAGE"


def offline_preview(filename, data):
    """Validate a file locally and fail closed on unverified registry evidence."""
    rows = parse_credit_note_upload(filename, data)
    audit = _blocked_preview(rows, "STAGING_FINANCIAL_DATABASE_NOT_CONNECTED")
    return audit, error_report_csv(audit)


def create_app():
    """Factory for the dedicated isolated staging service only."""
    if os.environ.get(STAGE_ENV) != "1":
        raise RuntimeError("ISOLATED_STAGING_PROFILE_REQUIRED")

    app = Flask("sbi_cn_isolated_stage")

    @app.get("/healthz")
    def healthz():
        # Authenticated by the dashboard session guard; no sensitive data.
        return jsonify(
            status="READ_ONLY",
            registry="NOT_CONNECTED",
            financial_writes=False,
            production_release="BLOCKED",
        )

    # The guard is installed before the staging-only blueprint; it verifies
    # Firebase session cookies with check_revoked=True on every request.
    install_sessions(app)
    app.register_blueprint(create_credit_note_staging_blueprint(offline_preview))
    app.config["SBI_CN_STAGING_ONLY"] = True
    return app
