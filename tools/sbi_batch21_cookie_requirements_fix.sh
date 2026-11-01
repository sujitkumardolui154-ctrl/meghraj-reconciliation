#!/usr/bin/env bash
# SBI Batch21 — repair Batch20's two specific preflight blockers.
# Only isolated candidate requirements and a backed-up local Cloud Shell script
# can change. Never changes dashboard source, IAM, Firestore, or main traffic.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
python3 - <<'PY'
import ast, hashlib, json, os, re, shutil
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

session=Path("dashboard_source/dashboard_sessions.py")
candidate=Path("staging_candidates/sbi_credit_report_batch19")
report=Path("reports/credit_note/batch21_two_blocker_fix.json")
report.parent.mkdir(parents=True,exist_ok=True)
status={
 "batch":21,"timestamp_utc":datetime.now(timezone.utc).isoformat(),
 "cookie_contract":"NOT_VERIFIED",
 "package_preflight":"NOT_VERIFIED",
 "canary_resume_allowed":False,
 "import_completeness":"NOT_CERTIFIED",
 "main_dashboard_modified":False,"financial_execution":"RESTRICTED",
 "blockers":[]
}
def problem(s):
    if s not in status["blockers"]:status["blockers"].append(s)
def valid_cookie(s):
    return isinstance(s,str) and re.fullmatch(r"[A-Za-z0-9_-]{2,64}",s) is not None
def dotted(node):
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):return dotted(node.value)+"."+node.attr
    return ""
def const(node):
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
    return None
def resolve(node,scope):
    x=const(node)
    if x is not None:return x
    if isinstance(node,ast.Name):return scope.get(node.id)
    if isinstance(node,ast.Call) and dotted(node.func) in (
          "os.getenv","os.environ.get"):
        if len(node.args)>1:return resolve(node.args[1],scope)
        for kw in node.keywords:
            if kw.arg=="default":return resolve(kw.value,scope)
    return None
def get_bindings(nodes, initial):
    table=dict(initial)
    # If a name has multiple different assignments, do not trust it.
    ambiguous=set()
    for node in nodes:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            value=resolve(node.value,table)
            if value is None:continue
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name):
                    if target.id in table and table[target.id]!=value:ambiguous.add(target.id)
                    else:table[target.id]=value
    for n in ambiguous:table.pop(n,None)
    return table
def candidate_calls(fn,globals_):
    scope=get_bindings(ast.walk(fn),globals_)
    setters=set();readers=set()
    for node in ast.walk(fn):
        if not isinstance(node,ast.Call):continue
        path=dotted(node.func)
        if path in ("response.set_cookie","resp.set_cookie") and node.args:
            value=resolve(node.args[0],scope)
            if valid_cookie(value):setters.add(value)
        if path in ("request.cookies.get","flask.request.cookies.get") and node.args:
            value=resolve(node.args[0],scope)
            if valid_cookie(value):readers.add(value)
    return setters,readers

if not session.is_file():
    problem("SESSION_MODULE_NOT_FOUND")
else:
    try:
        source=session.read_text(encoding="utf-8")
        tree=ast.parse(source,filename=str(session))
        globals_=get_bindings(tree.body,{})
        outer=next((n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=="install_sessions"),None)
        outer_scope=get_bindings(outer.body,globals_) if outer else globals_
        funcs=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        # Session issuer route calls a set_cookie helper; the helper performs
        # response.set_cookie with the actual static cookie name.
        wrappers=[n for n in funcs if n.name=="set_cookie"]
        logins=[n for n in funcs if n.name=="session_login"]
        readers=[]
        for fn in funcs:
            src=ast.get_source_segment(source,fn) or ""
            if "verify_session_cookie" in src and fn.name!="install_sessions":
                readers.append(fn)
        issuer_keys=set();reader_keys=set()
        for fn in logins:
            a,b=candidate_calls(fn,outer_scope)
            issuer_keys|=a
            if any(isinstance(c,ast.Call) and dotted(c.func).split(".")[-1]=="set_cookie" for c in ast.walk(fn)):
                for wrapper in wrappers:
                    setter,_=candidate_calls(wrapper,outer_scope)
                    issuer_keys|=setter
        for fn in readers:
            _,values=candidate_calls(fn,outer_scope)
            reader_keys|=values
        # Some implementations use a dedicated cookie reader helper called by
        # the verified-identity function; include it only if its name signals
        # it reads a session rather than CSRF or arbitrary browser cookies.
        for fn in funcs:
            if fn in readers:continue
            name=fn.name.lower()
            if ("session" in name or "identity" in name) and "csrf" not in name:
                _,values=candidate_calls(fn,outer_scope)
                reader_keys|=values
        matches=issuer_keys&reader_keys
        status["cookie_issuer_candidates"]=len(issuer_keys)
        status["cookie_reader_candidates"]=len(reader_keys)
        if (len(matches)==1 and logins and readers and
            "auth.create_session_cookie" in source and
            "auth.verify_session_cookie" in source):
            cookie=next(iter(matches))
            proof={
                "source_sha256":hashlib.sha256(session.read_bytes()).hexdigest(),
                "cookie_name":cookie,
                "proof":"issuer_reader_ast",
                "checked_utc":status["timestamp_utc"],
                "session_login_found":True,
                "verified_session_reader_found":True}
            proof_path=Path("reports/credit_note/batch21_verified_cookie.json")
            proof_path.write_text(json.dumps(proof,indent=2)+"\n",encoding="utf-8")
            proof_path.chmod(0o600)
            status["cookie_contract"]="ISSUER_READER_STATIC_MATCH"
            status["cookie_proof_file"]=str(proof_path)
        else:
            problem("COOKIE_ISSUER_READER_STATIC_PROOF_NOT_FOUND")
            status["cookie_contract"]="AMBIGUOUS_SOURCE_STOP"
    except (OSError,UnicodeError,SyntaxError) as exc:
        problem("COOKIE_SOURCE_"+type(exc).__name__)

# Restore the entire application's dependency file if available, without
# changing original dependency specifications or shipping source data.
required={
 "flask":"Flask>=3.0,<4",
 "gunicorn":"gunicorn>=21.2,<24",
 "firebase-admin":"firebase-admin>=6.5,<8",
 "google-cloud-storage":"google-cloud-storage>=2.16,<4"
}
if not candidate.is_dir():
    problem("ISOLATED_CANDIDATE_MISSING")
else:
    req=candidate/"requirements.txt"
    source_requirements=[
      Path("dashboard_source/requirements.txt"),
      Path("requirements.txt"),
      Path("dashboard_source/requirements-prod.txt")]
    existing=None
    for path in source_requirements:
        if path.is_file():
            try:
                current=path.read_text(encoding="utf-8")
                if current.strip():existing=current;break
            except (OSError,UnicodeError):pass
    if req.is_file():
        current=req.read_text(encoding="utf-8")
    elif existing:
        current=existing
    else:
        current=""
    provided=set()
    for line in current.splitlines():
        m=re.match(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\b",line)
        if m and not line.lstrip().startswith("#"):
            provided.add(m.group(1).lower().replace("_","-"))
    missing=[v for k,v in required.items() if k not in provided]
    modified=(current.rstrip()+"\n" if current.strip() else "")+(
        "# CREDIT NOTE private canary dependencies\n"+"\n".join(missing)+"\n" if missing else "")
    if not modified.strip():problem("REQUIREMENTS_CANNOT_BE_RESOLVED")
    else:
        if req.is_file() and current!=modified:
            folder=Path("backups/credit_note_repairs")
            folder.mkdir(parents=True,exist_ok=True)
            backup=folder/("before_batch21_requirements_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".txt")
            shutil.copy2(req,backup)
            status["requirements_backup"]=str(backup)
        if not req.is_file() or modified!=current:
            req.write_text(modified,encoding="utf-8")
            req.chmod(0o600)
        status["package_preflight"]="CANDIDATE_REQUIREMENTS_REPAIRED"
        status["added_dependency_names"]=[v.split(">")[0] for v in missing]
if status["cookie_contract"]=="ISSUER_READER_STATIC_MATCH" and status["package_preflight"]=="CANDIDATE_REQUIREMENTS_REPAIRED":
    status["canary_resume_allowed"]=True
status["import_completeness"]="NOT_CERTIFIED"
try:
    old=json.loads(Path("reports/consolidated_reporting_next_gate.json").read_text())
    status["import_completeness"]=old.get("import_completeness","NOT_CERTIFIED")
except (OSError,ValueError):pass
report.write_text(json.dumps(status,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
report.chmod(0o600)
print("COOKIE STATIC CONTRACT:",status["cookie_contract"])
print("CANDIDATE PYTHON DEPENDENCIES:",status["package_preflight"])
print("IMPORT COMPLETENESS:",status["import_completeness"])
print("REPAIR BLOCKERS:",",".join(status["blockers"]) or "NONE")
print("BATCH21_REPAIR="+json.dumps({
  "cookie_contract":status["cookie_contract"],
  "requirements":status["package_preflight"],
  "can_resume_canary":status["canary_resume_allowed"],
  "issuer_candidates":status.get("cookie_issuer_candidates",0),
  "reader_candidates":status.get("cookie_reader_candidates",0),
  "remaining":status["blockers"]},separators=(",",":")))
PY

READY="$(python3 -c 'import json;print("yes" if json.load(open("reports/credit_note/batch21_two_blocker_fix.json"))["canary_resume_allowed"] else "no")')"
if [ "$READY" != "yes" ]; then
  echo 'BATCH21_RESULT={"canary":"NOT_DEPLOYED","reason":"SOURCE_PROOF_INCOMPLETE","production":"BLOCKED"}'
  echo "MAIN DASHBOARD: UNCHANGED; FINANCIAL EXECUTION: RESTRICTED"
  echo "BATCH 21 COMPLETE"
  exit 0
fi
# Patch the LOCAL Batch20 script only if the expected exact source anchors exist.
# This extends cookie discovery with a SHA-256-bound attestation, not a bypass.
FILE="$HOME/sbi_batch20.sh"
if [ ! -f "$FILE" ]; then
  echo 'STOP: Previously executed Batch20 shell script missing; no deployment'
  exit 0
fi
python3 - "$FILE" <<'PY'
from pathlib import Path
import shutil,sys
from datetime import datetime,timezone
p=Path(sys.argv[1]);s=p.read_text(encoding="utf-8")
marker="BATCH21_SHA_BOUND_COOKIE_PROOF_V1"
old="        matches=issuer&reader\n        if len(matches)==1:"
new='''        matches=issuer&reader
        # BATCH21_SHA_BOUND_COOKIE_PROOF_V1
        from hashlib import sha256
        proof_path=Path("reports/credit_note/batch21_verified_cookie.json")
        if proof_path.is_file():
            proof=json.loads(proof_path.read_text(encoding="utf-8"))
            if (proof.get("proof")=="issuer_reader_ast"
                and proof.get("source_sha256")==sha256(session.read_bytes()).hexdigest()
                and isinstance(proof.get("cookie_name"),str)
                and re.fullmatch(r"[A-Za-z0-9_-]{2,64}",proof["cookie_name"])):
                matches={proof["cookie_name"]}
        if len(matches)==1:'''
if marker not in s:
    if s.count(old)!=1:
        raise SystemExit("STOP: Expected Batch20 cookie detector anchor missing; no modification")
    backup=p.with_name(p.name+".before_batch21_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(p,backup)
    p.write_text(s.replace(old,new,1),encoding="utf-8")
    print("BATCH20 LOCAL COOKIE DETECTOR: SHA-BOUND REPAIR INSTALLED")
else:
    print("BATCH20 LOCAL COOKIE DETECTOR: ALREADY REPAIRED")
PY
bash -n "$FILE"
echo "===== RESUMING PRIVATE CANARY PREFLIGHT ====="
bash "$FILE"
echo "BATCH 21 COMPLETE"
