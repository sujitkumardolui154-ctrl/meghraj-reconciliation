#!/usr/bin/env bash
# Prepare isolated read-only invoice lookup service package. NO deployment.
set -Eeuo pipefail
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"
test "$(git branch --show-current)" = ui/bulk-report-reports-tab-20261121
test -z "$(git status --porcelain --untracked-files=no)"

OUTPUT="/home/ubuntu/sbi-bulk-report-integration/PR129-invoice-lookup-stage-source.tar.gz"
if [ "$#" -gt 0 ]; then OUTPUT="$1"; fi
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
FILES="invoice_selection_report.py report_api.py invoice_source_schema.py invoice_import_store.py payment_report_rules.py invoice_import_contract.json"
for f in $FILES; do
  test -f "backend_source/$f"
  install -m 0644 "backend_source/$f" "$STAGE/$f"
done
install -m 0644 backend_source/invoice_lookup_stage_entry.py "$STAGE/main.py"
cat > "$STAGE/requirements.txt" <<'REQ'
functions-framework==3.*
google-cloud-firestore>=2.16,<3
google-auth>=2.35,<3
requests>=2.31,<3
REQ
python3 - "$STAGE" <<'PY'
import ast
from pathlib import Path
import sys
src=Path(sys.argv[1])
main=(src/"main.py").read_text()
tree=ast.parse(main)
names={node.name for node in tree.body if isinstance(node,ast.FunctionDef)}
assert names=={"invoice_lookup_stage"}, names
assert "handle_invoice_selection(request)" in main
assert "/imports/" not in main
assert (src/"invoice_import_contract.json").is_file()
for f in src.glob("*.py"):
    ast.parse(f.read_text(), filename=f.name)
print("LOOKUP_STAGE_SOURCE_SANITY=PASS")
print("EXPOSED_FUNCTION=invoice_lookup_stage")
print("FINANCIAL_WRITE_ENDPOINTS=NOT_INCLUDED")
PY
tar -czf "$OUTPUT" -C "$STAGE" .
sha256sum "$OUTPUT"
echo "LOOKUP_STAGE_SOURCE_ARCHIVE=$OUTPUT"
echo "PACKAGE_ONLY=YES"
echo "CLOUD_RUN_DEPLOYMENT=NOT_PERFORMED"
echo "FINANCIAL_WRITES=NONE"
