
import os
from google.cloud import storage

BUCKET = os.environ.get(
    "MONITORING_BUCKET",
    "meghraj-sbi-agent-monitoring-109590290120"
)

def list_monitoring_objects(limit=100):
    client = storage.Client()
    blobs = client.list_blobs(BUCKET, max_results=min(limit, 100))
    return [blob.name for blob in blobs]
