#!/usr/bin/env bash
# SBI fast-track: discover exact source ZIP filenames, NOT Git commits.
# Both archival 64-hex identifiers are SHA-256 *code fingerprints*.
# Does not read any file content, unzip, hash, modify, deploy, or access
# PAYMNENT, invoice, financial, GST or historical workbook records.
set -euo pipefail

echo "=== SBI FAST-TRACK ARCHIVED CODE PACKAGE LOCATOR ==="
echo "HASH_TYPE=SHA256_CODE_FINGERPRINT_NOT_GIT_COMMIT"
echo "SOURCE_PACKAGE_INSPECTION=FILENAME_ONLY"
echo "FINANCIAL_RECORDS=NOT_ACCESSED"

# The Builder/Primary handoff inbox path is taken from archived engineering
# correspondence, not inferred from the AWS checkout.
folders=(
  "/DIL_PRIMARY_AGENT_HUB/My_sec_Payment_Reconciliation/INBOX/ENGINE_BUILDER"
  "$HOME/DIL_PRIMARY_AGENT_HUB/My_sec_Payment_Reconciliation/INBOX/ENGINE_BUILDER"
)
names=(
  "ENGINE_BUILDER_SB18_PRE_BC_CHAIN_REMEDIATION_20261028_1939IST.zip"
  "OUT_SCHEMA_V218_STAGING_BUILDER_20261028_1932IST.zip"
)
for i in 0 1; do
  found=0
  for d in "${folders[@]}"; do
    if [ -f "$d/${names[$i]}" ] && [ ! -L "$d/${names[$i]}" ]; then
      echo "SOURCE_PACKAGE_${i}=FOUND_IN_BUILDER_INBOX"
      found=1
      break
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo "SOURCE_PACKAGE_${i}=NOT_FOUND_IN_KNOWN_BUILDER_INBOX"
  fi
done

echo "SOURCE_PACKAGE_0_EXPECTED_ARCHIVE_SHA256=27149c9ab65065db51c14748708d0ee6775176d66d49a555711eb889b22c1e5f"
echo "SOURCE_PACKAGE_1_EXPECTED_ARCHIVE_SHA256=b85bf68b2e241a71da4daccc3ff666f9576eb1c5a7ac7d46239d7003c9670c81"
echo "SOURCE_PACKAGE_0_EXPECTED_CODE_SHA256=189cd6e9cff399412a50520afd0d7520752a3682c707751ec1f853c57c7ad256"
echo "SOURCE_PACKAGE_1_EXPECTED_CODE_SHA256=85606f226ebb7b6555a648386021b3df2765d29c9f37312d499029b335b0719b"
echo "PACKAGE_INTEGRITY=NOT_VERIFIED"
echo "SOURCE_REVIEW_AUTHORIZATION=REQUIRED"
echo "CANONICAL_ENGINE_CERTIFIED=NO"
echo "HISTORICAL_FINANCIAL_DATA_ACCESSED=NO"
echo "FINANCIAL_WRITES=NOT_PERFORMED"
echo "FINANCIAL_APPLY=LOCKED"
echo "FASTTRACK_SOURCE_DISCOVERY=COMPLETE"
