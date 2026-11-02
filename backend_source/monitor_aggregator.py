import re
from google.cloud import storage
from monitor_report_reader import (
    BUCKET,
    read_monitoring_report
)

def collect_monitoring_reports(contract, limit=30):
    limit = max(1, min(int(limit), 100))
    client = storage.Client()
    reports = []
    rejected = 0

    allowed = set(contract["allowed_agents"])

    blobs = client.list_blobs(
        BUCKET,
        prefix="reports/",
        max_results=limit
    )

    for blob in blobs:
        name = blob.name
        match = re.fullmatch(
            r"reports/([a-z_]+)/[A-Za-z0-9_-]{1,80}\.json",
            name
        )

        if not match or match.group(1) not in allowed:
            rejected += 1
            continue

        try:
            result = read_monitoring_report(name, contract)
            reports.append(result)
        except (ValueError, UnicodeError):
            rejected += 1

    return {
        "data_source": "PRIVATE_CLOUD_STORAGE",
        "authentication_status": "NOT_VERIFIED",
        "financial_execution_enabled": False,
        "reports": reports,
        "rejected_records": rejected
    }
