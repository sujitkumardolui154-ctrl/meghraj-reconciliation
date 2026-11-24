"""Dedicated R31 PostgreSQL-report staging WSGI entrypoint; no public AWS cutover.

R31 base app already installs real Firebase cookie revocation/CSRF/Origin
handlers before the payment/report blueprints. Replace report views only.
Explicitly refuse startup unless private QA PostgreSQL report scope is set.
"""
from app import app
from db_r31_pg_report_private_wsgi import attach_private_stage_report
attach_private_stage_report(app)
