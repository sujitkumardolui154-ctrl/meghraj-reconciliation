"""Credential and login-service dependency inventory for SBI PR129.

Runs inside one existing container with Python on stdin. NO credential values,
private key bytes, token strings, account identifiers or env value dumps.
Never calls Google APIs, starts auth, or writes any file.
"""
import ast
import json
import os
from pathlib import Path

key="GOOGLE_APPLICATION_CREDENTIALS"
path=os.environ.get(key,"")
print("GOOGLE_CREDENTIAL_ENV_PRESENT="+str(bool(path)))
if path:
    file=Path(path)
    regular=file.is_file()
    readable=regular and os.access(str(file),os.R_OK)
    print("GOOGLE_CREDENTIAL_FILE_EXISTS="+str(regular))
    print("GOOGLE_CREDENTIAL_FILE_READABLE="+str(readable))
    if readable:
        try:
            with file.open("r",encoding="utf-8") as stream:
                obj=json.load(stream)
            if not isinstance(obj,dict):
                print("GOOGLE_CREDENTIAL_DOCUMENT_TYPE=UNEXPECTED")
            else:
                kind=obj.get("type")
                category=kind if kind in ("service_account","external_account","authorized_user") else "OTHER"
                print("GOOGLE_CREDENTIAL_DOCUMENT_TYPE="+category)
                print("GOOGLE_CREDENTIAL_PROJECT_FIELD_PRESENT="+str(bool(obj.get("project_id"))))
                print("GOOGLE_CREDENTIAL_PRIVATE_KEY_FIELD_PRESENT="+str(bool(obj.get("private_key"))))
        except Exception as exc:
            print("GOOGLE_CREDENTIAL_DOCUMENT_READ=ERROR_"+type(exc).__name__)
else:
    print("GOOGLE_CREDENTIAL_FILE_EXISTS=NOT_CONFIGURED")
    print("GOOGLE_CREDENTIAL_FILE_READABLE=NOT_CONFIGURED")

for module in ("google.auth","firebase_admin","firebase_admin.auth"):
    try:
        import importlib.util
        found=importlib.util.find_spec(module) is not None
        print("MODULE_AVAILABLE="+module+" STATUS="+("YES" if found else "NO"))
    except Exception as exc:
        print("MODULE_AVAILABLE="+module+" STATUS=ERROR_"+type(exc).__name__)

files=("cloud_auth.py","dashboard_sessions.py","app.py","sbi_report_access.py")
needles=("authentication service unavailable","login setup is not complete","untrusted request origin")
for basename in files:
    file=Path("/app")/basename
    if not file.is_file():
        print("SOURCE_FILE="+basename+" STATUS=MISSING")
        continue
    print("SOURCE_FILE="+basename+" STATUS=PRESENT")
    try:
        code=file.read_text(encoding="utf-8")
        tree=ast.parse(code,filename=basename)
    except (OSError,UnicodeError,SyntaxError) as exc:
        print("SOURCE_FILE="+basename+" STATUS=ERROR_"+type(exc).__name__)
        continue
    imports=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            imports.update(a.name for a in node.names)
        if isinstance(node,ast.ImportFrom) and node.module:
            imports.add(node.module)
    for prefix in ("firebase_admin","google.auth","google.oauth2"):
        print("SOURCE_IMPORT="+basename+" NAME="+prefix+" PRESENT="+str(any(i==prefix or i.startswith(prefix+".") for i in imports)))
    match_funcs=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            text=ast.get_source_segment(code,node) or ""
            if "GOOGLE_APPLICATION_CREDENTIALS" in text or "firebase_admin" in text or "google.auth" in text:
                match_funcs.append(node.name)
    print("CREDENTIAL_RELATED_FUNCTIONS="+basename+" NAMES="+(",".join(sorted(set(match_funcs))[:30]) if match_funcs else "NONE_FOUND"))
    for lineno,line in enumerate(code.splitlines(),1):
        for phrase in needles:
            if phrase in line.lower():
                print("LOGIN_ERROR_SOURCE="+basename+" LINE="+str(lineno)+" TYPE="+phrase.replace(" ","_"))
print("CREDENTIAL_DEPENDENCY_AUDIT=COMPLETE")
