#!/usr/bin/env python3
"""Read-only check of a SECOND Firebase dashboard test account.

Email is prompted privately and passed only as docker-exec stdin, never argv,
shell, environment, logs or chat. Never creates users or changes claims.
"""
from __future__ import annotations
import getpass
import json
import re
import subprocess
import sys

from r31_real_firebase_qa_acceptance import STAGE

INNER = """
import json,sys
from firebase_admin import auth
from dashboard_sessions import firebase_app, MASTER_UID
try:
    raw=sys.stdin.buffer.read(1024)
    doc=json.loads(raw)
    email=doc.get('email') if isinstance(doc,dict) else None
    if not isinstance(email,str) or not 3<=len(email)<=254:
        print('DB_R31_11_SECOND_FIREBASE=BAD_INPUT')
    else:
        user=auth.get_user_by_email(email,app=firebase_app())
        if user.uid==MASTER_UID:
            print('DB_R31_11_SECOND_FIREBASE=BLOCKED_SAME_AS_MASTER')
        elif user.disabled:
            print('DB_R31_11_SECOND_FIREBASE=BLOCKED_USER_DISABLED')
        elif (user.custom_claims or {}).get('dil_dashboard') is not True:
            print('DB_R31_11_SECOND_FIREBASE=BLOCKED_DASHBOARD_CLAIM_MISSING')
        elif (user.custom_claims or {}).get('dil_admin') is True:
            print('DB_R31_11_SECOND_FIREBASE=BLOCKED_UNNECESSARY_ADMIN_CLAIM')
        else:
            print('DB_R31_11_SECOND_FIREBASE=READY_DISTINCT_AUTHORIZED_USER')
except auth.UserNotFoundError:
    print('DB_R31_11_SECOND_FIREBASE=NOT_FOUND_IN_FIREBASE_PROJECT')
except Exception:
    print('DB_R31_11_SECOND_FIREBASE=BLOCKED_FIREBASE_ADMIN_CHECK_FAILED')
"""


def check_second_firebase():
    if not sys.stdin.isatty():
        print("DB_R31_11_SECOND_FIREBASE=NOT_TESTED_TTY_REQUIRED", flush=True)
        return False
    answer=input("Check a SECOND distinct Firebase test account? [y/N]: ").strip().lower()
    if answer != "y":
        print("DB_R31_11_SECOND_FIREBASE=NOT_TESTED_SECOND_ACCOUNT_UNAVAILABLE",
              flush=True)
        return False
    email=getpass.getpass("Second TEST account email (hidden): ").strip()
    if not 3 <= len(email) <= 254:
        print("DB_R31_11_SECOND_FIREBASE=BAD_INPUT", flush=True)
        return False
    result=subprocess.run(
        ["sudo","-n","docker","exec","-i","-w","/app",STAGE,
         "python3","-c",INNER],
        input=json.dumps({"email":email}),text=True,capture_output=True,
        timeout=25,check=False
    )
    email=None
    allowed=frozenset({
        "READY_DISTINCT_AUTHORIZED_USER",
        "BLOCKED_SAME_AS_MASTER",
        "BLOCKED_USER_DISABLED",
        "BLOCKED_DASHBOARD_CLAIM_MISSING",
        "BLOCKED_UNNECESSARY_ADMIN_CLAIM",
        "NOT_FOUND_IN_FIREBASE_PROJECT",
        "BLOCKED_FIREBASE_ADMIN_CHECK_FAILED",
        "BAD_INPUT",
    })
    if result.returncode!=0:
        print("DB_R31_11_SECOND_FIREBASE=BLOCKED_RUNTIME",flush=True)
        return False
    matches=[
        line for line in result.stdout.splitlines()
        if re.fullmatch(r"DB_R31_11_SECOND_FIREBASE=[A-Z0-9_]{1,100}",line)
    ]
    if len(matches)!=1 or matches[0].split("=",1)[1] not in allowed:
        print("DB_R31_11_SECOND_FIREBASE=BLOCKED_INVALID_QA_RECEIPT",flush=True)
        return False
    print(matches[0],flush=True)
    return matches[0]=="DB_R31_11_SECOND_FIREBASE=READY_DISTINCT_AUTHORIZED_USER"


if __name__=="__main__":
    if not check_second_firebase():
        raise SystemExit(2)
