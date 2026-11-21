#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/staging/fresh_financial_engine/stage43:$ROOT/staging/fresh_financial_engine/stage4:$ROOT/staging/fresh_financial_engine"
python -m unittest discover -s staging/fresh_financial_engine/stage4/tests -p 'test_*.py' -q
python -m unittest discover -s staging/fresh_financial_engine/stage43/tests -p 'test_source_contract.py' -q
if python -c 'import artifact_tool' >/dev/null 2>&1; then
  python -m unittest discover -s staging/fresh_financial_engine/stage43/tests -p 'test_workbook_e2e.py' -q
  echo 'STAGE43_SYNTHETIC_WORKBOOK_QA=PASS'
else
  echo 'STAGE43_SYNTHETIC_WORKBOOK_QA=NOT_RUN_RUNTIME_UNAVAILABLE'
fi
echo 'FINANCIAL_APPLY=LOCKED'
