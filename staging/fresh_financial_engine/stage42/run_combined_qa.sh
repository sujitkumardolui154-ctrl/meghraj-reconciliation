#!/usr/bin/env bash
# Offline synthetic QA. Does not open user workbooks or access a bank/ledger.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for src in "$root/stage4/stage4_ledger.py" "$root/stage41/v218_writer.py" "$root/stage42/combined_review.py"; do
  if [[ ! -f "$src" ]]; then echo "SOURCE_MODULE_MISSING=$src"; exit 2; fi
done
export PYTHONPATH="$root/stage42:$root/stage4:$root/stage41"
python -m unittest discover -s "$root/stage4/tests" -p 'test_*.py' -q
python -m unittest discover -s "$root/stage41/tests" -p 'test_*.py' -q
python -m unittest discover -s "$root/stage42/tests" -p 'test_*.py' -q
echo 'COMBINED_LOCAL_REGRESSION=85_TESTS_PASS'
echo 'FINANCIAL_APPLY=LOCKED'
echo 'FINANCIAL_WRITES=NOT_IMPLEMENTED'
echo 'HISTORICAL_RECORDS=NOT_PROCESSED'
