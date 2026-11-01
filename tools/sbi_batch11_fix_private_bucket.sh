#!/usr/bin/env bash
# Batch 11 security gate repair: enforce bucket PAP + uniform IAM access
# then correct local staging script to parse raw Cloud Storage API fields.
# No Firestore edits, no financial engine changes, no public IAM grants.
set -Eeuo pipefail
umask 077

PROJECT="meghraj-reconciliation"
BUCKET="meghraj-sbi-reports-private-109590290120"
SOURCE="$HOME/sbi_credit_dashboard_batch11.sh"
BUCKET_URI="gs://$BUCKET"

if [ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]; then
  echo "STOP: Switch to the approved project before proceeding"; exit 2
fi
if [ ! -f "$SOURCE" ]; then
  echo "STOP: $SOURCE not found — upload the original Batch 11 script"; exit 2
fi
if ! gcloud storage buckets describe "$BUCKET_URI" >/dev/null; then
  echo "STOP: Expected private report bucket missing or not accessible"; exit 2
fi

echo "===== CORRECT PRIVATE STORAGE SETTINGS ====="
gcloud storage buckets update "$BUCKET_URI" --public-access-prevention --uniform-bucket-level-access --quiet

RAW="$(mktemp)"
trap 'rm -f "$RAW"' EXIT
gcloud storage buckets describe "$BUCKET_URI" --raw --format=json > "$RAW"
python3 - "$RAW" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding="utf-8"))
iam=data.get("iamConfiguration",{})
pap=str(iam.get("publicAccessPrevention","")).lower()
uba=iam.get("uniformBucketLevelAccess",{})
if pap!="enforced":
    raise SystemExit("STOP: Bucket public-access prevention is not explicitly enforced")
if not isinstance(uba,dict) or uba.get("enabled") is not True:
    raise SystemExit("STOP: Uniform bucket-level access is not enabled")
print("PUBLIC ACCESS PREVENTION: ENFORCED")
print("UNIFORM BUCKET-LEVEL ACCESS: ENABLED")
print("PRIVATE BUCKET SECURITY: PASS")
PY

python3 - "$SOURCE" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import shutil,sys,ast
path=Path(sys.argv[1])
raw=path.read_text(encoding="utf-8")
before='gcloud storage buckets describe "gs://$BUCKET" --format=json > "$BUCKET_JSON"'
after='gcloud storage buckets describe "gs://$BUCKET" --raw --format=json > "$BUCKET_JSON"'
if after in raw:
    print("BATCH 11 STORAGE CHECK: ALREADY CORRECTED")
elif raw.count(before)==1 and 'STOP: Bucket public-access prevention is not enforced' in raw:
    backup=path.with_name(path.name+".before_pap_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(path,backup)
    path.write_text(raw.replace(before,after,1),encoding="utf-8")
    print("BATCH 11 STORAGE CHECK: CORRECTED")
    print("ORIGINAL SCRIPT BACKUP:",backup)
else:
    raise SystemExit("STOP: Batch 11 script security check has an unexpected structure")
PY
bash -n "$SOURCE"
echo "===== RESUME BATCH 11 PRIVATE STAGING ====="
bash "$SOURCE"
