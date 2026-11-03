import json
from datetime import datetime, timezone
import functions_framework

PROJECT_ID = "meghraj-reconciliation"

def respond(data, status=200):
    return (
        json.dumps(data),
        status,
        {
            "Content-Type": "application/json",
            "Cache-Control": "no-store"
        }
    )

@functions_framework.http
def supervisor_api(request):
    if request.path.rstrip("/") in ("/change-reports", "/change-reports.csv"):
        from change_report_api import handle_change_report
        return handle_change_report(request)
    # DIL v1.4.0 database import API
    if request.path.startswith("/imports/"):
        # Independent service-to-service verification before ANY Firestore client.
        from invoice_import_security import authorized_import_caller
        if not authorized_import_caller(request):
            return respond({"error": "Import service authentication required"}, 403)
        from invoice_import_api import handle_imports
        return handle_imports(request)
    # DIL v1.3.0 database reports
    if request.path.startswith("/reports/reconciliation-changes/"):
        from change_report_api import handle_change_report
        return handle_change_report(request)
    if request.path.rstrip("/") == "/reports" or request.path.startswith("/reports/"):
        from report_api import handle_reports
        return handle_reports(request)
    # DIL dashboard v1.3.0 Excel intake
    if request.path.rstrip("/") == "/upload":
        from upload_api import handle_upload
        return handle_upload(request)
    if request.method != "GET":
        return respond({"error": "Method not allowed"}, 405)

    path = request.path.rstrip("/") or "/"
    timestamp = datetime.now(timezone.utc).isoformat()

    if path in ("/", "/health"):
        return respond({
            "service": "sbi-supervisor-backend",
            "project": PROJECT_ID,
            "status": "RUNNING",
            "financial_execution_enabled": False,
            "timestamp_utc": timestamp
        })

    if path == "/qa":
        return respond({
            "data_source": "STATIC_BASELINE",
            "qa_status": "PENDING",
            "production_release": "BLOCKED",
            "issues": [
                {"id": "Q218-D01", "status": "INDEPENDENT_QA_PENDING"},
                {"id": "SBISA_NEGATIVE", "status": "UNRESOLVED"}
            ]
        })

    if path == "/supervisor":
        return respond({
            "supervisor": "DIL",
            "monitoring_mode": "STATIC_BASELINE",
            "production_release": "BLOCKED",
            "financial_engine": "NOT_DEPLOYED",
            "financial_execution_enabled": False,
            "timestamp_utc": timestamp
        })

    if path == "/agents":
        return respond({
            "data_source": "DEMONSTRATION_ONLY",
            "live_agent_connection": False,
            "agents": [
                {"name": "Supervisor", "status": "NOT_CONNECTED"},
                {"name": "Independent QA", "status": "NOT_CONNECTED"},
                {"name": "Reconciliation Builder", "status": "NOT_CONNECTED"}
            ]
        })


    if path == "/monitoring-feed":
        import os
        if os.environ.get("ENABLE_MONITORING_FEED") != "true":
            return respond({
                "status": "NOT_ENABLED",
                "financial_execution_enabled": False
            }, 503)

        try:
            from monitoring_feed import get_monitoring_feed
            return respond(get_monitoring_feed())
        except Exception:
            return respond({
                "status": "MONITORING_SOURCE_UNAVAILABLE",
                "financial_execution_enabled": False
            }, 503)

    return respond({"error": "Not found"}, 404)
