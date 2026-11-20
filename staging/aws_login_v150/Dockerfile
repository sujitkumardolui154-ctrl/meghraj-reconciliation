# Pinned, separate AWS v1.5 Firebase login + former dashboard frontend.
# Only include the isolated AWS UI entrypoint and approved login assets.
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY staging/aws_login_v150/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY dashboard_source/dashboard_sessions.py dashboard_source/dashboard_login_pages.py /app/
COPY dashboard_source/login.html dashboard_source/login.css dashboard_source/login.js /app/
COPY dashboard_source/index.html dashboard_source/dashboard.js dashboard_source/dashboard_theme.css /app/
COPY dashboard_source/account.js dashboard_source/dil_floating_assistant.js /app/
COPY staging/aws_login_v150/app.py /app/app.py
COPY staging/aws_login_v150/tower_readonly.py /app/tower_readonly.py
COPY staging/aws_login_v150/project_workspace.py /app/project_workspace.py
COPY staging/aws_login_v150/payment_evidence_upload.py /app/payment_evidence_upload.py
COPY staging/aws_login_v150/reconciliation_readiness.py /app/reconciliation_readiness.py
COPY staging/aws_login_v150/readonly_reports_gateway.py /app/readonly_reports_gateway.py
COPY backend_source/aws_readonly_snapshot_reports.py /app/aws_readonly_snapshot_reports.py
COPY staging/aws_login_v150/bulk_reports.py /app/bulk_reports.py
COPY backend_source/invoice_source_schema.py backend_source/sbi_reporting_bundle.py /app/
COPY backend_source/invoice_import_contract.json /app/invoice_import_contract.json
COPY staging/aws_login_v150/workspace_ui.html /app/workspace_ui.html
COPY staging/aws_login_v150/github_workstream_board.html /app/github_workstream_board.html
COPY staging/aws_login_v150/tower_theme.css /app/tower_theme.css
# Recover the original engineering Control Tower, not a modified placeholder.
COPY staging/railway_public/pipeline.html /app/pipeline.html
COPY staging/railway_public/pipeline_data.py /app/pipeline_data.py
ARG SBI_SOURCE_SHA=UNVERIFIED
LABEL org.opencontainers.image.revision="${SBI_SOURCE_SHA}"
ENV SBI_SOURCE_SHA=${SBI_SOURCE_SHA} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN chmod 0644 /app/*.py /app/*.html /app/*.css /app/*.js
USER 10001:10001
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "app:app"]
