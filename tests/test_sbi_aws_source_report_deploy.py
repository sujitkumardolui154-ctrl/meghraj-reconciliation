"""Source-only AWS reports release must keep authenticated app and finance locks."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOGIN=ROOT/"staging/aws_login_v150"

class SourceReportDeploymentQA(unittest.TestCase):
    def test_exact_existing_baseline_and_rollback(self):
        sh=(LOGIN/"deploy_source_reports_v1.sh").read_text()
        caddy=(LOGIN/"Caddyfile.source_reports_v1").read_text()
        for line in (
            'PREV="sbi-payment-evidence-stage"',
            'NEW="sbi-source-reports-v1-stage"',
            'BASELINE="$ROOT/staging/aws_login_v150/Caddyfile.payment_evidence_v1"',
            'CANDIDATE="$ROOT/staging/aws_login_v150/Caddyfile.source_reports_v1"',
            'BACKUP="$CONF/Caddyfile.before-source-reports-v1"',
            "BLOCKED_EXISTING_CADDY_CHANGED",
            "SBI_SOURCE_REPORTS_PRIVATE_HTTP=PASS",
            "SBI_SOURCE_REPORTS_STAGE=PASS",
            "SBI_SOURCE_REPORTS_PUBLIC_ROUTE=ACTIVE",
            "SBI_SOURCE_REPORTS_ROLLBACK=ATTEMPTED",
            "PRODUCTION_FINANCIAL_CUTOVER=BLOCKED",
            "FINANCIAL_WRITES=DISABLED",
            'EVIDENCE_DIR="/var/lib/sbi-payment-evidence-staging"',
            'WORKSPACE_DIR="/var/lib/sbi-control-tower-workspace"',
            'ACTUAL_REPORT_MOUNT=',
            'BLOCKED_STAGED_REPORT_VOLUME_NOT_MATCHING_APPROVED_SOURCE',
            "PRIVATE_SOURCE_REPORT_PARITY=PASS",
        ):
            self.assertIn(line,sh,line)
        self.assertIn(
            'git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_source_reports_v1.sh" |',
            sh
        )
        self.assertNotIn(
            'git -C "$ROOT" show "$SHA:staging/aws_login_v150/deploy_payment_evidence_v1.sh" |',
            sh
        )
        self.assertIn("reverse_proxy sbi-source-reports-v1:8080",caddy)
        self.assertIn("reverse_proxy sbi-preview:8080",caddy)
        self.assertIn("/api/*",caddy)
        self.assertIn("/auth/*",caddy)
        self.assertIn("/pipeline",caddy)
        self.assertNotIn("reverse_proxy sbi-payment-evidence:8080",caddy)

    def test_report_snapshot_is_opt_in_and_never_in_docker_image(self):
        sh=(LOGIN/"deploy_source_reports_v1.sh").read_text()
        docker=(LOGIN/"Dockerfile").read_text()
        for marker in (
            'REPORT_ENV="$CONF/certified-reports.env"',
            'REPORT_DIR="/var/lib/sbi-certified-report-snapshot"',
            "REPORT_DATA=NOT_CONNECTED",
            "BLOCKED_REPORT_INDEPENDENT_PIN_REQUIRED",
            "--env-file \"$REPORT_ENV\"",
            "dst=/report-snapshot,readonly",
            "SBI_AWS_REPORT_SNAPSHOT_DIR=/report-snapshot",
            "BLOCKED_PRIVATE_REPORT_FILE=",
        ):
            self.assertIn(marker,sh,marker)
        self.assertIn("COPY backend_source/aws_readonly_snapshot_reports.py",docker)
        self.assertNotIn("certified-reports.env",docker)
        self.assertNotIn("source-report-contents.csv",docker)
        self.assertNotIn("firebase-service-account.json",docker)

if __name__=="__main__":unittest.main()
