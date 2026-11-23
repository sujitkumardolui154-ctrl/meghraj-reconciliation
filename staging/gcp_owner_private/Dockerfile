# Phase 2 source-only Cloud Run candidate. Build context MUST be generated from
# the vetted Phase 1 source package plus canary.py; never use repository root.
FROM python:3.12-slim-bookworm

ARG SOURCE_COMMIT_SHA
RUN test ${#SOURCE_COMMIT_SHA} -eq 40
LABEL org.opencontainers.image.revision="${SOURCE_COMMIT_SHA}"
LABEL org.opencontainers.image.title="SBI owner staging canary - NO FINANCE"
LABEL org.opencontainers.image.description="IAM-only staging source verification, no financial app endpoint"

WORKDIR /srv
COPY --chown=10001:10001 canary.py /srv/canary.py
COPY --chown=10001:10001 source/ /opt/sbi/source/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    STAGING_ONLY=true \
    FINANCIAL_WRITES_DISABLED=true \
    RECONCILIATION_EXECUTION_ENABLED=false \
    SOURCE_COMMIT_SHA="${SOURCE_COMMIT_SHA}"
RUN python -m py_compile /srv/canary.py && \
    grep -q PASS_SOURCE_PACKAGE_ONLY /opt/sbi/source/RELEASE_PREFLIGHT_MANIFEST.json
USER 10001:10001
EXPOSE 8080
CMD ["python", "/srv/canary.py"]
