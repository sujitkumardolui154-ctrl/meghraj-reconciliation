#!/usr/bin/env bash
# SBI fast-track — look for approved *source commits only* in a Git checkout.
# Inspects git object metadata / Python filenames; never opens any bank,
# invoice, PAYMNENT, GST, credit-note, payment receipt, ledger or data file.
# No network calls, no deploy, no checkout, no file writes, no finance actions.
set -euo pipefail

ROOT="${1:-.}"
if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "FINANCIAL_SOURCE_SCAN=NO_GIT_CHECKOUT"
  exit 2
fi

echo "=== SBI FAST-TRACK CANONICAL ENGINE SOURCE DISCOVERY ==="
echo "SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)"
echo "SEARCH_SCOPE=GIT_METADATA_AND_PYTHON_PATHS_ONLY"
echo "FINANCIAL_INPUT_FILES=NOT_OPENED"

scan_commit() {
  local label="$1" sha="$2"
  if ! git -C "$ROOT" cat-file -e "${sha}^{commit}" 2>/dev/null; then
    echo "${label}=NOT_IN_LOCAL_GIT_OBJECTS"
    return
  fi
  echo "${label}=COMMIT_OBJECT_FOUND"
  # This lists source-code filenames only. It does NOT read source contents,
  # financial worksheets or historical data records.
  git -C "$ROOT" ls-tree -r --name-only "$sha" |
    awk '
      /(^|\/)[^/]+[.]py$/ &&
      tolower($0) ~ /(reconcil|allocat|waterfall|settle|finance|financial|engine)/ {
        print "SOURCE_CODE_PATH=" $0
      }
    '
}

# Source identities grounded in the owner's archived engine recovery plan.
# They are historical ENGINE-CODE candidate commit identities, not data.
scan_commit "SB18_BUILDER_CANDIDATE" \
  "189cd6e9cff399412a50520afd0d7520752a3682c707751ec1f853c57c7ad256"
scan_commit "V218_WRITER_CANDIDATE" \
  "85606f226ebb7b6555a648386021b3df2765d29c9f37312d499029b335b0719b"

echo "CURRENT_BRANCH_FINANCIAL_MODULE_PATHS_BEGIN"
git -C "$ROOT" ls-tree -r --name-only HEAD |
  awk '
    /(^|\/)[^/]+[.]py$/ &&
    tolower($0) ~ /(reconcil|allocat|waterfall|settle|finance|financial|engine)/ {
      print "CURRENT_CODE_PATH=" $0
    }
  '
echo "CURRENT_BRANCH_FINANCIAL_MODULE_PATHS_END"
echo "SOURCE_CANDIDATE_APPROVAL=NOT_ESTABLISHED"
echo "FINANCIAL_WRITER_CONNECTED=NOT_VERIFIED"
echo "FINANCIAL_MATCHING_EXECUTION=NOT_PERFORMED"
echo "HISTORICAL_FINANCIAL_RECORDS=NOT_ACCESSED"
echo "FINANCIAL_WRITES=NOT_PERFORMED"
echo "FINANCIAL_PRODUCTION_APPLY=LOCKED"
echo "FASTTRACK_SOURCE_DISCOVERY=COMPLETE"
