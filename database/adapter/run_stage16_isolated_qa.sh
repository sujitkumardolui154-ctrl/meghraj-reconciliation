#!/usr/bin/env bash
# Stage 16. Isolated PR129 PostgreSQL reporting adapter QA.
# No modifications to existing PR129 services or PostgreSQL financial data.
set -Eeuo pipefail

STAGE="/home/ubuntu/sbi-pr129-pg-readonly-qa"
BASE="https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/c8075f13efe8db86e57410f2f995d96522a2a76a/database/adapter"
mkdir -p "$STAGE"
chmod 700 "$STAGE"
cd "$STAGE"

for filename in sbi_pg_reporting.py test_sbi_pg_reporting.py test_live_readonly.py Dockerfile.qa; do
  curl -4 -fLsS --retry 3 -o "$filename" "$BASE/$filename"
done

echo "=== SOURCE PYTHON SYNTAX ==="
python3 -m py_compile sbi_pg_reporting.py test_sbi_pg_reporting.py test_live_readonly.py
echo "PYTHON_SYNTAX=PASS"

echo "=== BUILD SEPARATE TEST IMAGE (NOT PR129) ==="
sudo docker build -f Dockerfile.qa -t sbi-pr129-pg-report-qa:isolated .
echo "ISOLATED_IMAGE_BUILD=PASS"

echo "=== LOCAL UNIT TESTS IN ISOLATED CONTAINER ==="
sudo docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$STAGE,target=/opt/sbi-adapter,readonly" \
  sbi-pr129-pg-report-qa:isolated \
  python3 -m unittest -v test_sbi_pg_reporting.py

echo "=== LIVE READ-ONLY ADAPTER TEST VIA PRIVATE SOCKET ==="
echo "You will be prompted for sbi_pr129_report_login password, which is not displayed."
sudo docker run --rm -it --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$STAGE,target=/opt/sbi-adapter,readonly" \
  --mount type=bind,source=/var/run/postgresql,target=/var/run/postgresql,readonly \
  -e PGHOST=/var/run/postgresql \
  -e PGDATABASE=sbi_reconciliation_main \
  -e PGUSER=sbi_pr129_report_login \
  sbi-pr129-pg-report-qa:isolated \
  python3 test_live_readonly.py

echo "STAGE16_ISOLATED_ADAPTER_QA=PASS"
echo "LIVE_PR129_DEPLOYMENT=NOT_PERFORMED"
echo "FINANCIAL_ENGINE=UNCHANGED"
