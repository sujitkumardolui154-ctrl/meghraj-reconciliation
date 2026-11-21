#!/usr/bin/env bash
# Read-only application-layout probe after /app/index.html was not found.
# Does not print environment secrets, file content or invoice/customer data.
# No rebuild, restart, proxy reload, financial reads or writes.
set -Eeuo pipefail
MAIN=aws_lightsail-sbi-preview-1
CADDY=aws_lightsail-caddy-1
echo '=== SBI LIVE APP FILE LAYOUT PROBE ==='
for c in "$MAIN" "$CADDY"; do
  test "$(sudo docker inspect "$c" --format '{{.State.Running}}')" = true || {
    echo "STOP_CONTAINER_NOT_RUNNING=$c"; exit 1;
  }
done
sudo docker inspect "$MAIN" --format 'MAIN_IMAGE={{.Config.Image}}'
sudo docker inspect "$MAIN" --format 'MAIN_WORKDIR={{.Config.WorkingDir}}'
sudo docker inspect "$MAIN" --format 'MAIN_USER={{.Config.User}}'
sudo docker inspect "$MAIN" --format 'MAIN_NETWORK={{.HostConfig.NetworkMode}}'
sudo docker inspect "$MAIN" --format 'MAIN_MOUNT_DESTINATIONS={{range .Mounts}}{{.Destination}};{{end}}'
sudo docker exec -i "$MAIN" python -B - <<'PY'
from pathlib import Path
from importlib.util import find_spec
import os,sys
print("PYTHON_CWD="+os.getcwd())
module_roots=set()
for name in ("app","production_gateway","main","dashboard_sessions",
             "bulk_reports","sbi_report_access","cloud_auth"):
    try:
        spec=find_spec(name)
        origin=spec.origin if spec is not None else None
        print("MODULE_"+name.upper()+"="+str(origin or "NOT_FOUND"))
        if origin and origin not in ("built-in","frozen"):
            module_roots.add(str(Path(origin).parent))
    except (ImportError,AttributeError,ValueError) as exc:
        print("MODULE_"+name.upper()+"_LOOKUP_ERROR="+type(exc).__name__)
roots=("/app","/code","/srv","/workspace","/opt/app",
       "/usr/src/app","/home/ubuntu",os.getcwd(),*sorted(module_roots))
seen=set()
for raw in roots:
    root=Path(raw)
    if str(root) in seen or not root.is_dir():
        continue
    seen.add(str(root))
    for name in ("index.html","production_gateway.py","app.py","main.py",
                 "dashboard_sessions.py","bulk_reports.py","bulk_report_excel.py"):
        p=root/name
        if p.is_file():
            print("FOUND_FILE="+str(p))
    subfolders=("dashboard_source","static","templates","src","backend_source")
    for sub in subfolders:
        for name in ("index.html","production_gateway.py","app.py"):
            p=root/sub/name
            if p.is_file():
                print("FOUND_FILE="+str(p))
print("ROOTS_INSPECTED="+str(len(seen)))
print("LIVE_LAYOUT_DISCOVERY=COMPLETE")
PY

echo '=== CADDY REPORT UPSTREAM TOKENS (NO SECRETS OR CONTENT) ==='
sudo docker exec "$CADDY" python3 -B - <<'PY' || echo 'CADDY_PYTHON_UNAVAILABLE_SKIPPED'
from pathlib import Path
p=Path("/etc/caddy/Caddyfile")
if not p.is_file(): raise SystemExit("STOP_CADDYFILE_MISSING")
lines=p.read_text().splitlines()
for i,line in enumerate(lines,1):
    t=line.strip()
    if t.startswith(("#","header","env","basicauth")): continue
    if any(token in t for token in ("reverse_proxy","handle","route","sbi-preview","bulk-report")):
        if any(x in t.lower() for x in ("password","secret","bearer","token","authorization")):continue
        print("ROUTE_LINE_"+str(i)+"="+t[:180])
PY
echo 'EXISTING_GATEWAY=UNCHANGED'
echo 'RUNNING_CONTAINERS=UNCHANGED'
echo 'INVOICE_ROWS_READ=NONE'
echo 'FINANCIAL_DATABASE_WRITES=NONE'
echo 'SBI_LIVE_LAYOUT_PROBE=COMPLETE'
