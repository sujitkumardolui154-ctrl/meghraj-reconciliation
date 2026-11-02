from report_freshness import classify_report_freshness
import json
import re
from google.cloud import storage
from agent_report_validator import validate_agent_report

BUCKET = "meghraj-sbi-agent-monitoring-109590290120"
MAX_BYTES = 65536

def read_monitoring_report(object_name, contract):
    if not isinstance(object_name, str) or not re.fullmatch(
        r"reports/[a-z_]+/[A-Za-z0-9_-]{1,80}\.json",
        object_name
    ):
        raise ValueError("Invalid report object path")

    blob = storage.Client().bucket(BUCKET).blob(object_name)
    blob.reload()

    if blob.size is None or blob.size > MAX_BYTES:
        raise ValueError("Report exceeds size limit")

    raw = blob.download_as_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Report exceeds size limit")

    report = json.loads(raw.decode("utf-8"))
    valid, reason = validate_agent_report(report, contract)

    if not valid:
        raise ValueError("Report validation failed: " + reason)


    path_agent = object_name.split("/")[1]

    if path_agent not in contract["allowed_agents"]:
        raise ValueError("Agent path not approved")

    if report["agent_id"] != path_agent:
        raise ValueError("Report agent identity does not match storage path")

    freshness_status = classify_report_freshness(
        report["completed_at"]
    )

    return {
        "verification_status": "SCHEMA_VALID_ONLY",
        "freshness_status": freshness_status,
        "object_name": object_name,
        "report": report
    }
