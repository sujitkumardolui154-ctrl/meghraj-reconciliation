#!/usr/bin/env bash
# SBI Stage 30.9 — install one read-only user cron job, no server/finance changes.
set -Eeuo pipefail
umask 077
if [[ "$(id -un)" != "ubuntu" ]];then
  echo "STAGE30_9_INSTALL=BLOCKED_RUN_AS_UBUNTU_NONROOT";exit 10
fi
SCRIPT=/home/ubuntu/sbi_pr129_monitor.py
EXPECTED_SHA=f7dc687ad82114c487e5dcf21f45d2e39f91f427
MARKER="SBI_PR129_READ_ONLY_MONITOR_STAGE30_9"
ENTRY="*/10 * * * * /usr/bin/python3 $SCRIPT >/dev/null 2>&1 # $MARKER"
echo "=== STAGE 30.9 — PINNED READ-ONLY MONITOR INSTALLATION ==="
test -f "$SCRIPT" && test "$(git hash-object "$SCRIPT")" = "$EXPECTED_SHA" || {
  echo "STAGE30_9_SOURCE_INTEGRITY=BLOCKED";exit 11;
}
python3 -m py_compile "$SCRIPT"
echo "STAGE30_9_SOURCE_INTEGRITY=PASS"
command -v crontab >/dev/null || { echo "STAGE30_9_CRONTAB=NOT_INSTALLED";exit 12; }
CURRENT="$(crontab -l 2>/dev/null || true)"
if printf '%s\n' "$CURRENT" | grep -Fq "$MARKER";then
  if printf '%s\n' "$CURRENT" | grep -Fxq "$ENTRY";then
    echo "STAGE30_9_CRON=ALREADY_INSTALLED_IDENTICAL"
  else
    echo "STAGE30_9_CRON=CONFLICTING_EXISTING_ENTRY_REVIEW_REQUIRED"
    exit 13
  fi
else
  { printf '%s\n' "$CURRENT"; printf '%s\n' "$ENTRY"; } | crontab -
  echo "STAGE30_9_CRON=INSTALLED_EVERY_10_MINUTES"
fi
if command -v systemctl >/dev/null && systemctl is-active --quiet cron;then
 echo "STAGE30_9_CRON_SERVICE=RUNNING"
else
 echo "STAGE30_9_CRON_SERVICE=NOT_CONFIRMED_RUNNING"
fi
echo "=== FIRST MANUAL SAMPLE; IF PUBLIC DNS DIFFERS, LOG DEGRADED WITHOUT HIDING IT ==="
set +e
python3 "$SCRIPT"
SAMPLE_CODE=$?
set -e
echo "STAGE30_9_INITIAL_SAMPLE_EXIT=$SAMPLE_CODE"
echo "STAGE30_9_MONITOR_LOG=/home/ubuntu/sbi-production-monitoring/monitor.jsonl"
echo "STAGE30_9_MONITOR_ALERTS=/home/ubuntu/sbi-production-monitoring/alerts.jsonl"
echo "STAGE30_9_MONITOR_CADENCE=10_MINUTES"
echo "STAGE30_9_FINANCIAL_WRITES=NONE"
echo "STAGE30_9_CADDY_AND_DOCKER_CHANGES=NONE"
echo "STAGE30_9_MONITORING_SETUP=COMPLETE_CRON_REQUIRES_RUNNING_SERVICE"
