#!/usr/bin/env bash
# Read-only AWS staging attestation; Python owns validation and HTTP requests.
set -Eeuo pipefail
exec python3 "$(dirname "$0")/g_aws_ui_preview_readonly_attest.py"
