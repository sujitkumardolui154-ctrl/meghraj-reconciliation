"""SBI Bulk Report AWS blue-green delivery must be fail-closed."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/"staging/aws_login_v150"

class BulkReportDeploymentInvariants(unittest.TestCase):
    def test_exact_release_source_and_blue_green_rollback(self):
        source=(STAGE/"deploy_bulk_reports_v1.sh").read_text(encoding="utf-8")
        config=(STAGE/"Caddyfile.bulk_reports_v1").read_text(encoding="utf-8")
        for required in (
            'git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_bulk_reports_v1.sh"',
            'PREV="sbi-source-reports-v1-stage"',
            'NEW="sbi-bulk-reports-v1-stage"',
            'IMAGE="sbi-aws-bulk-reports-v1:$SHORT"',
            'BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.source_reports_v1"',
            'CANDIDATE="$ROOT/staging/aws_login_v150/Caddyfile.bulk_reports_v1"',
            'BACKUP="$CONF/Caddyfile.before-bulk-reports-v1"',
            "BLOCKED_EXISTING_CADDY_CHANGED",
            "SBI_BULK_REPORTS_PRIVATE_HTTP=PASS",
            "SBI_BULK_REPORTS_STAGE=PASS",
            "SBI_BULK_REPORTS_PUBLIC_ROUTE=ACTIVE",
            "SBI_BULK_REPORTS_ROLLBACK=ATTEMPTED",
            "LEGACY_PIPELINE=UNCHANGED_BASIC_AUTH",
            "PRODUCTION_FINANCIAL_CUTOVER=BLOCKED",
            "FINANCIAL_WRITES=DISABLED",
            "BULK_REPORT=ENABLED_SOURCE_ONLY_XLSX",
            "BULK_REPORT_FINANCIAL_WRITES=DISABLED",
            'WORKSPACE_DIR="/var/lib/sbi-control-tower-workspace"',
            'EVIDENCE_DIR="/var/lib/sbi-payment-evidence-staging"',
            'ACTUAL_REPORT_MOUNT=',
            "PRIVATE_SOURCE_REPORT_PARITY=NOT_CONNECTED_SAFE",
        ):
            self.assertIn(required,source,required)
        self.assertNotIn('show "$SHA:staging/aws_login_v150/deploy_source_reports_v1.sh"',source)
        self.assertIn("reverse_proxy sbi-bulk-reports-v1:8080",config)
        self.assertIn("reverse_proxy sbi-preview:8080",config)
        self.assertIn("/pipeline",config)
        self.assertIn("/api/*",config)

    def test_bulk_generator_sealed_without_payment_engine(self):
        docker=(STAGE/"Dockerfile").read_text()
        for required in (
            "COPY staging/aws_login_v150/bulk_reports.py /app/bulk_reports.py",
            "COPY backend_source/invoice_source_schema.py backend_source/sbi_reporting_bundle.py /app/",
            "COPY backend_source/invoice_import_contract.json /app/invoice_import_contract.json",
            "USER 10001:10001",
        ):
            self.assertIn(required,docker)
        for forbidden in (
            "invoice_import_apply.py","payment_report_rules.py",
            "reconciliation_apply","production_gateway.py",
            "firebase-service-account.json",
        ):
            self.assertNotIn("COPY "+forbidden,docker)
if __name__=="__main__":
    unittest.main()
