FROM python:3.12-slim-bookworm
WORKDIR /app
COPY staging/aws_backend_readonly/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
# Copy ONLY the sealed read-only gateway, never the import/payment writers.
COPY backend_source/aws_readonly_reporting_app.py /app/app.py
ARG SBI_SOURCE_SHA=UNVERIFIED
LABEL org.opencontainers.image.revision="${SBI_SOURCE_SHA}"
ENV SBI_SOURCE_SHA=${SBI_SOURCE_SHA} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "app:app"]
