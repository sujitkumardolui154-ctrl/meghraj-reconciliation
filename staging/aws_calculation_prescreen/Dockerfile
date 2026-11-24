FROM python:3.12-slim-bookworm
WORKDIR /app
COPY staging/aws_calculation_prescreen/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
# Intentionally copy ONLY the R28 source-screen partitioner and the isolated
# R29 preview gateway, never bank secrets, XLSX, financial writers, or DB clients.
COPY scripts/ci/sbi_r28_owner_deployment_and_row_exclusion_policy.py /app/sbi_r28_owner_deployment_and_row_exclusion_policy.py
COPY backend_source/aws_calculation_prescreen_app.py /app/app.py
RUN chmod 0644 /app/app.py /app/sbi_r28_owner_deployment_and_row_exclusion_policy.py
ARG SBI_SOURCE_SHA=UNVERIFIED
LABEL org.opencontainers.image.revision="${SBI_SOURCE_SHA}"
ENV SBI_SOURCE_SHA=${SBI_SOURCE_SHA} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SBI_FINANCIAL_APPLY=LOCKED
USER 10001:10001
EXPOSE 8080
CMD ["gunicorn","--bind","0.0.0.0:8080","--workers","1","--threads","4","--worker-tmp-dir","/dev/shm","app:app"]
