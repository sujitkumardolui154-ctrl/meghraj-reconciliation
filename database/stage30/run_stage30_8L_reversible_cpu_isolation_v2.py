#!/usr/bin/env python3
"""Stage 30.8L v2: guarded, reversible SIGSTOP/SIGCONT of verified Docker CLI."""
import datetime
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

PID=204785
EXPECTED_EPOCH=datetime.datetime(2026,11,21,19,25,58,tzinfo=datetime.timezone.utc).timestamp()
SITE="pr129.13-232-241-221.sslip.io"
CADDY=Path("/home/ubuntu/sbi-aws-app/staging/aws_lightsail/Caddyfile")
CADDY_SHA="61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b"
ROOT=Path("/home/ubuntu/sbi-release-evidence")
HZ=os.sysconf("SC_CLK_TCK")

def record():
    p=Path("/proc")/str(PID)
    try:
        x=(p/"stat").read_text()
        f=x[x.rfind(")")+2:].split()
        args=[t.decode("utf8","replace") for t in (p/"cmdline").read_bytes().split(b"\0") if t]
        return {"state":f[0],"ppid":int(f[1]),"ticks":int(f[11])+int(f[12]),
                "start":int(f[19]),"name":(p/"comm").read_text().strip(),"args":args}
    except (OSError,ValueError,IndexError):
        return None

def same(start):
    r=record()
    return bool(r and r["name"]=="docker" and r["start"]==start)

def cont(start,tag):
    if not same(start):
        print(tag+"=TARGET_EXITED_OR_CHANGED_NO_SIGNAL",flush=True)
        return False
    os.kill(PID,signal.SIGCONT)
    print(tag+"=SIGCONT_SENT_TO_VERIFIED_CLIENT",flush=True)
    return True

def watch(start,folder):
    ready=folder/"watchdog_ready"
    done=folder/"controller_resumed"
    log=folder/"watchdog.log"
    try:
        ready.write_text("ARMED\n")
        limit=time.monotonic()+30
        while not done.exists() and time.monotonic()<limit:
            time.sleep(.25)
        with log.open("a") as f:
            if same(start):
                os.kill(PID,signal.SIGCONT)
                f.write("STAGE30_8L_WATCHDOG=VERIFIED_CLIENT_RESUMED\n")
            else:
                f.write("STAGE30_8L_WATCHDOG=PID_GONE_OR_CHANGED\n")
    except Exception as exc:
        with log.open("a") as f:f.write("STAGE30_8L_WATCHDOG_ERROR="+type(exc).__name__+"\n")

def pressure():
    try:
        line=next(x for x in Path("/proc/pressure/cpu").read_text().splitlines() if x.startswith("some "))
        return next(x.split("=",1)[1] for x in line.split() if x.startswith("avg10="))
    except (OSError,StopIteration):
        return "NA"

def cpu(start,seconds=4):
    a=record()
    if not a or a["start"]!=start:return None
    time.sleep(seconds)
    b=record()
    if not b or b["start"]!=start:return None
    return round(100*max(0,b["ticks"]-a["ticks"])/(HZ*seconds),1)

def http(path):
    cmd=["curl","--noproxy","*","-sS","-o","/dev/null",
         "-w","%{http_code} %{time_appconnect} %{time_starttransfer} %{time_total}",
         "--connect-timeout","3","--max-time","8",
         "--resolve",SITE+":443:127.0.0.1","https://"+SITE+path]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
        data=p.stdout.strip().split()
        return (data[0] if data else "NONE",
                data[-1] if len(data)==4 else "NA",
                data[1] if len(data)==4 else "NA",
                data[2] if len(data)==4 else "NA",p.returncode)
    except subprocess.TimeoutExpired:
        return ("TIMEOUT","NA","NA","NA",124)

def phase(label,start):
    print("STAGE30_8L_"+label+"_CPU_PSI_AVG10="+pressure(),flush=True)
    print("STAGE30_8L_"+label+"_DOCKER_CLIENT_CPU_4S="+str(cpu(start)),flush=True)
    endpoints=[("login","/login","200"),
               ("anonymous_report","/api/reporting/v2/postgresql-summary","401")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda x:http(x[1]),endpoints))
    errors=0
    for (name,path,want),(status,total,tls,ttfb,rc) in zip(endpoints,results):
        print("STAGE30_8L_"+label+"_HTTP="+name+" status:"+status+
              " total:"+total+" tls:"+tls+" ttfb:"+ttfb,flush=True)
        if rc!=0 or status!=want:errors+=1
    print("STAGE30_8L_"+label+"_AUTH_ERRORS="+str(errors),flush=True)

def main():
    if os.geteuid()!=0:
        print("STAGE30_8L=REQUIRES_SUDO_N_ROOT");return 2
    os.umask(0o077)
    ROOT.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix="stage30_8L_reversible_",dir=ROOT))
    print("STAGE30_8L_EVIDENCE_DIR="+str(folder),flush=True)
    paused=False
    start=None
    didresume=False
    try:
        r=record()
        if r is None:
            print("STAGE30_8L_PRECHECK=TARGET_EXITED_OR_PROC_UNREADABLE",flush=True)
            raise RuntimeError("TARGET_EXITED_OR_PROC_UNREADABLE_NO_PAUSE")
        argv0_ok=bool(r["args"]) and Path(r["args"][0]).name=="docker"
        try:
            exe=os.readlink("/proc/"+str(PID)+"/exe")
            exe_ok=Path(exe.removesuffix(" (deleted)")).name=="docker"
        except OSError:
            exe_ok=False
        print("STAGE30_8L_PRECHECK_PROC_NAME="+r["name"],flush=True)
        print("STAGE30_8L_PRECHECK_ARGV0_DOCKER="+str(argv0_ok),flush=True)
        print("STAGE30_8L_PRECHECK_EXECUTABLE_DOCKER="+str(exe_ok),flush=True)
        print("STAGE30_8L_PRECHECK_ARGCOUNT="+str(len(r["args"])),flush=True)
        print("STAGE30_8L_PRECHECK_PARENT_MATCH="+str(r["ppid"]==204784),flush=True)
        print("STAGE30_8L_PRECHECK_RUN_RM="+str(bool(r["args"]) and "run" in r["args"] and "--rm" in r["args"]),flush=True)
        if r["name"]!="docker" or not exe_ok or not r["args"]:
            raise RuntimeError("TARGET_NOT_VERIFIED_DOCKER_EXECUTABLE_NO_PAUSE")
        if r["ppid"]!=204784 or r["state"] in ("T","t"):
            raise RuntimeError("TARGET_PARENT_CHANGED_OR_ALREADY_PAUSED")
        if "run" not in r["args"] or "--rm" not in r["args"]:
            raise RuntimeError("TARGET_NOT_EXPECTED_RUN_RM")
        boot=int(next(x.split()[1] for x in Path("/proc/stat").read_text().splitlines() if x.startswith("btime ")))
        started=boot+r["start"]/HZ
        if abs(started-EXPECTED_EPOCH)>2:
            raise RuntimeError("TARGET_START_TIME_MISMATCH")
        start=r["start"]
        original_sha=hashlib.sha256(CADDY.read_bytes()).hexdigest()
        if original_sha!=CADDY_SHA:
            raise RuntimeError("CADDY_PRODUCTION_HASH_MISMATCH")
        print("STAGE30_8L_VERIFIED_PID_EXECUTABLE_START_TIME_AND_PRODUCTION_CONFIG=PASS",flush=True)
        phase("BEFORE",start)
        load=cpu(start,3)
        print("STAGE30_8L_PRESTOP_DOCKER_CPU_3S="+str(load),flush=True)
        if load is None or load<50:
            print("STAGE30_8L_ISOLATION=SKIPPED_CLIENT_NOT_CURRENTLY_CPU_HEAVY",flush=True)
            return 0
        # Watchdog must be alive and have acknowledged readiness before stop.
        fd=(folder/"watchdog_stdout.log").open("a")
        try:
            watcher=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),
                                     "--watchdog",str(start),str(folder)],
                                     stdin=subprocess.DEVNULL,stdout=fd,
                                     stderr=subprocess.STDOUT,close_fds=True,
                                     start_new_session=True)
        finally:
            fd.close()
        for _ in range(60):
            if (folder/"watchdog_ready").exists() and watcher.poll() is None:break
            time.sleep(.1)
        else:
            raise RuntimeError("WATCHDOG_NOT_READY_NO_PAUSE")
        print("STAGE30_8L_INDEPENDENT_WATCHDOG=ARMED_30_SECONDS",flush=True)
        if not same(start):raise RuntimeError("TARGET_CHANGED_BEFORE_PAUSE")
        paused=True
        os.kill(PID,signal.SIGSTOP)
        print("STAGE30_8L_PAUSE=SIGSTOP_SENT_TO_DOCKER_CLIENT_ONLY",flush=True)
        phase("PAUSED",start)
        if not cont(start,"STAGE30_8L_MAIN_RESUME"):
            raise RuntimeError("PROCESS_CHANGED_BEFORE_RESUME")
        didresume=True
        (folder/"controller_resumed").write_text("MAIN_SIGCONT_SENT\n")
        paused=False
        phase("AFTER",start)
        if hashlib.sha256(CADDY.read_bytes()).hexdigest()!=original_sha:
            raise RuntimeError("CADDY_CONFIG_CHANGED")
        print("STAGE30_8L_COMPARATIVE_DIAGNOSTIC=COMPLETE",flush=True)
        return 0
    except Exception as exc:
        print("STAGE30_8L_COMPARATIVE_DIAGNOSTIC=REVIEW_REQUIRED reason:"+str(exc),flush=True)
        return 1
    finally:
        if paused and start is not None:
            try:
                if cont(start,"STAGE30_8L_EMERGENCY_MAIN_RESUME"):
                    didresume=True
                    (folder/"controller_resumed").write_text("EMERGENCY_SIGCONT_SENT\n")
            except Exception as exc:
                print("STAGE30_8L_RESUME_FALLBACK=WATCHDOG_ARMED error:"+type(exc).__name__,flush=True)
        print("STAGE30_8L_MAIN_SIGCONT_CONFIRMED="+str(didresume),flush=True)
        print("STAGE30_8L_DOCKER_DAEMON_CONTACT=NONE",flush=True)
        print("STAGE30_8L_CADDY_RELOAD=NONE",flush=True)
        print("STAGE30_8L_CONTAINERS_STOPPED_BY_TEST=NONE",flush=True)
        print("STAGE30_8L_FINANCIAL_WRITES_BY_TEST=NONE",flush=True)
        print("STAGE30_8L_STAGE30_8_HANDOVER=STILL_PENDING_STRICT_LATENCY_QA",flush=True)

if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--watchdog":
        watch(int(sys.argv[2]),Path(sys.argv[3]))
    else:
        sys.exit(main())
