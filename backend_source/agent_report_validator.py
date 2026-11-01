
from datetime import datetime

def validate_agent_report(report, contract):
    if not isinstance(report, dict):
        return False, "Report must be an object"

    for field in contract["required"]:
        value = report.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, "Missing or invalid: " + field

    if report["agent_id"] not in contract["allowed_agents"]:
        return False, "Unknown agent"

    if report["recorded_status"] not in contract["allowed_statuses"]:
        return False, "Invalid status"

    try:
        timestamp = datetime.fromisoformat(
            report["completed_at"].replace("Z", "+00:00")
        )
        if timestamp.tzinfo is None:
            return False, "Timestamp must include timezone"
    except ValueError:
        return False, "Invalid timestamp"

    if len(report["report_summary"]) > 2000:
        return False, "Report summary too long"

    return True, "SCHEMA_VALID_ONLY"
