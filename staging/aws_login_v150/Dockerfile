# Pinned, separate AWS v1.5 Firebase login + former dashboard frontend.
# Only include the isolated AWS UI entrypoint and approved login assets.
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY staging/aws_login_v150/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY dashboard_source/dashboard_sessions.py dashboard_source/dashboard_login_pages.py /app/
COPY dashboard_source/login.html dashboard_source/login.css dashboard_source/login.js /app/
COPY dashboard_source/index.html dashboard_source/dashboard.js /app/
COPY dashboard_source/account.js dashboard_source/dil_floating_assistant.js /app/
COPY staging/aws_login_v150/app.py /app/app.py
COPY staging/aws_login_v150/tower_readonly.py /app/tower_readonly.py
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
