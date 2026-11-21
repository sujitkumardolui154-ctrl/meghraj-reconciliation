#!/usr/bin/env bash
# RETIRED — the main Lightsail container runs only /app/app.py.
# The validated SBI reporting UI/backend is the PR129 preview.
# Safe replacement: scripts/sbi_promote_verified_pr129_main_live.sh
set -Eeuo pipefail
echo "STOP_RETIRED_SCRIPT_WRONG_MAIN_APP_LAYOUT"
echo "USE=scripts/sbi_promote_verified_pr129_main_live.sh"
echo "PUBLIC_GATEWAY_CHANGED=NO"
echo "FINANCIAL_WRITES=NONE"
exit 2
