FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py pipeline_data.py pipeline.html priority_tasks.py ui_preview.html ui_preview.css ./
ARG SBI_SOURCE_SHA=unknown
ARG SBI_RELEASE_CHANNEL=unverified
LABEL org.opencontainers.image.revision="${SBI_SOURCE_SHA}"
ENV SBI_SOURCE_SHA=${SBI_SOURCE_SHA} SBI_RELEASE_CHANNEL=${SBI_RELEASE_CHANNEL}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin g69app \
    && chown -R 10001:10001 /app
USER 10001:10001
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 app:app"]
