#!/usr/bin/env python3
"""SBI Stage 30.9. Read-only, credential-free production HTTPS monitor.

Intended for a 10-minute ubuntu-user cron job. No Docker, Caddy, database,
Firebase session, invoice, reconciliation, SSH, or cloud control-plane calls.
Only HTTPS GET /login and anonymously protected endpoints. Output is
bounded local monitoring data. No source rows or secrets are collected.
"""
from __future__ import annotations
import datetime as dt
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time

SITE = "pr129.13-232-241-221.sslip.io"
THRESHOLD_SECONDS = 3.0
ROUTES = (
    ("login", "/login", "200"),
    ("postgresql-summary", "/api/reporting/v2/postgresql-summary", "401"),
    ("report-catalog", "/api/reporting/v2", "401"),
    ("bulk-report-status", "/api/bulk-report/status", "401"),
)
BASEDIR = Path("/home/ubuntu/sbi-production-monitoring")
STATEFILE = BASEDIR / "state.json"
ALERTFILE = BASEDIR / "alerts.jsonl"
LOGFILE = BASEDIR / "monitor.jsonl"
LOCKFILE = BASEDIR / ".lock"

def curl_get(mode: str, path: str) -> dict:
    """One anonymous request with bounded connection and overall timeouts."""
    cmd = [
        "/usr/bin/curl", "--noproxy", "*", "-sS", "-o", "/dev/null",
        "-w", "%{http_code} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total}",
        "--connect-timeout", "3", "--max-time", "7",
    ]
    if mode == "LOCAL_CADDY":
        # Local loopback Caddy request with the actual HTTPS hostname and SNI.
        cmd += ["--resolve", SITE + ":443:127.0.0.1"]
    cmd += ["https://" + SITE + path]
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=9)
        fields = p.stdout.strip().split()
        if len(fields) == 5:
            status = fields[0]
            tcp, tls, ttfb, total = (float(v) for v in fields[1:])
        else:
            status, tcp, tls, ttfb, total = "NO_STATUS", None, None, None, None
        return {
            "status": status, "curl_exit": p.returncode,
            "seconds": round(total, 4) if total is not None else None,
            "tcp_seconds": round(tcp, 4) if tcp is not None else None,
            "tls_seconds": round(tls, 4) if tls is not None else None,
            "ttfb_seconds": round(ttfb, 4) if ttfb is not None else None,
        }
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "TRANSPORT_ERROR", "curl_exit": 124,
            "seconds": round(time.monotonic() - start, 3),
            "tcp_seconds": None, "tls_seconds": None, "ttfb_seconds": None,
        }

def psi():
    try:
        row=next(s for s in Path("/proc/pressure/cpu").read_text().splitlines()
                 if s.startswith("some "))
        return float(next(v.split("=", 1)[1] for v in row.split()
                          if v.startswith("avg10=")))
    except (OSError, ValueError, StopIteration):
        return None

def load_state():
    try:
        state=json.loads(STATEFILE.read_text())
        return {"consecutive_unhealthy_cycles":max(0,min(100000,int(state.get("consecutive_unhealthy_cycles",0)))),
                "last_alert_cycle":max(0,min(100000,int(state.get("last_alert_cycle",0))))}
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return {"consecutive_unhealthy_cycles":0,"last_alert_cycle":0}

def private_append(file: Path, obj: dict):
    fd=os.open(str(file), os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n")

def save_state(obj:dict):
    tmp=STATEFILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,separators=(",",":"))+"\n")
    os.chmod(tmp,0o600)
    os.replace(tmp,STATEFILE)

def main()->int:
    os.umask(0o077)
    BASEDIR.mkdir(parents=True,exist_ok=True)
    os.chmod(BASEDIR,0o700)
    with LOCKFILE.open("a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("STAGE30_9_MONITOR=SKIPPED_PREVIOUS_JOB_RUNNING",flush=True)
            return 0
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        samples=[]
        errors=0
        for mode in ("LOCAL_CADDY","PUBLIC_DNS"):
            for label,path,want in ROUTES:
                result=curl_get(mode,path)
                ok=(result["status"]==want and result["curl_exit"]==0
                    and result["seconds"] is not None
                    and result["seconds"]<=THRESHOLD_SECONDS)
                samples.append({"mode":mode,"route":label,"expected":want,
                                **result,"ok":ok})
                if not ok:errors+=1
        state=load_state()
        if errors:
            state["consecutive_unhealthy_cycles"]+=1
        else:
            state["consecutive_unhealthy_cycles"]=0
            state["last_alert_cycle"]=0
        streak=state["consecutive_unhealthy_cycles"]
        status="DEGRADED" if errors else "PASS"
        event={"timestamp_utc":now,"release":"PR129_LIMITED_READ_ONLY",
               "status":status,"threshold_seconds":THRESHOLD_SECONDS,
               "sample_count":len(samples),"errors":errors,
               "consecutive_unhealthy_cycles":streak,
               "cpu_psi_avg10":psi(),"samples":samples}
        private_append(LOGFILE,event)
        # 3 failures on consecutive 10-minute monitoring cycles.
        # Record alerts locally; no external notifications / side effects.
        if streak==3 or (streak>3 and streak%6==0):
            private_append(ALERTFILE,{"timestamp_utc":now,"severity":"CRITICAL",
                 "reason":"THREE_OR_MORE_CONSECUTIVE_UNHEALTHY_CYCLES",
                 "consecutive_unhealthy_cycles":streak,
                 "sample_errors":errors,
                 "action":"Operator review; no automatic rollback or container stop"})
            state["last_alert_cycle"]=streak
        save_state(state)
        print("STAGE30_9_MONITOR_UTC="+now)
        print("STAGE30_9_MONITOR_STATUS="+status)
        print("STAGE30_9_HTTP_SAMPLE_COUNT="+str(len(samples)))
        print("STAGE30_9_HTTP_ERRORS="+str(errors))
        print("STAGE30_9_CONSECUTIVE_UNHEALTHY_CYCLES="+str(streak))
        print("STAGE30_9_LOG="+str(LOGFILE))
        print("STAGE30_9_ALERT_LOG="+str(ALERTFILE))
        print("STAGE30_9_MONITORING_COVERAGE=ANONYMOUS_PUBLIC_AND_LOOPBACK_ONLY")
        print("STAGE30_9_DOCKER_AND_CADDY_CHANGES=NONE")
        print("STAGE30_9_FINANCIAL_DATABASE_WRITES=NONE")
        return 0 if not errors else 2

if __name__=="__main__":
    sys.exit(main())
