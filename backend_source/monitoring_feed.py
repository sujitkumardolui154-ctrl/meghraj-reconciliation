
import json
from pathlib import Path
from monitor_aggregator import collect_monitoring_reports

def get_monitoring_feed():
    contract = json.loads(
        Path(__file__).with_name(
            "agent_report_contract.json"
        ).read_text()
    )

    result = collect_monitoring_reports(contract)

    return {
        "data_source": result["data_source"],
        "verification_status": "UNVERIFIED_CANDIDATES",
        "live_agent_connection": False,
        "candidate_count": len(result["reports"]),
        "rejected_count": result["rejected_records"],
        "financial_execution_enabled": False,
        "production_release": "BLOCKED"
    }
