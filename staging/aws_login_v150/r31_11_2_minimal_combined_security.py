#!/usr/bin/env python3
"""DB-R31.11.2 minimal combined security verification, private staging ONLY.

One operator command; three necessary, non-mutating checks:
  1. Reuse the already-reviewed R31.11 existing-clone read-only owner RLS audit;
  2. Deny unauthenticated HTTP requests inside the private QA container;
  3. Keep the QA container absent from the current public Caddy config.

Skip: clone creation, SQL migrations, synthetic INSERT, historical financial
tests, invoice/GST and reconciliation engines (R31.12 is quarantined).
Do not ask the same absent-second-user question again. No HTTPS E2E is claimed.
The backend uses a shared DB report role, so actual Firebase->tenant DB RLS
remains unconnected and release MUST remain blocked.
"""
from __future__ import annotations

from r31_11_existing_clone_readonly_audit import main as clone_readonly_main
from r31_real_firebase_qa_acceptance import STAGE, docker


APP_ANONYMOUS_PROBE = r"""
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None
opener=build_opener(NoRedirects())
# Single read-only request validates denied entry to the protected QA API.
try:
    response=opener.open(Request(
        'http://127.0.0.1:8080/api/r31-private-qa/sol-report',
        method='GET'
    ),timeout=6)
    status=response.status
except HTTPError as e:
    status=e.code
except (OSError,TimeoutError):
    status=0
print('DB_R31_11_2_ANONYMOUS_SOURCE_READ='+
      ('PASS_DENIED_401' if status==401 else 'FAIL_NOT_DENIED_AS_EXPECTED'))
"""

def anonymous_guard():
    output=docker("exec",STAGE,"python3","-c",APP_ANONYMOUS_PROBE)
    allowed="DB_R31_11_2_ANONYMOUS_SOURCE_READ=PASS_DENIED_401"
    if output != allowed:
        print("STOP=DB_R31_11_2_ANONYMOUS_SOURCE_GUARD_NOT_PROVEN",flush=True)
        return False
    print(allowed,flush=True)
    return True


def caddy_route_guard():
    config=docker("exec","aws_lightsail-caddy-1",
                  "cat","/etc/caddy/Caddyfile")
    if any(candidate in config for candidate in (
        "sbi-r31-auth-private-qa","sbi-r31-auth-qa",
    )):
        print("STOP=DB_R31_11_2_CADDY_QA_ROUTE_REFERENCE_FOUND",flush=True)
        return False
    # This is a route reference check, not full public TLS/certificate QA.
    print("DB_R31_11_2_CADDY_QA_CONTAINER_REFERENCE=ABSENT",flush=True)
    return True


def main():
    print("=== DB-R31.11.2 MINIMAL COMBINED SECURITY QA ===",flush=True)
    if clone_readonly_main()!=0:
        print("STOP=DB_R31_11_2_CLONE_RLS_NOT_REVERIFIED",flush=True)
        return 2
    print("DB_R31_11_2_CLONE_RLS=PASS_REUSED_READONLY_AUDIT",flush=True)
    anon_ok=anonymous_guard()
    route_ok=caddy_route_guard()
    # Existing owner says second real Firebase test user is NOT available.
    # No redundant prompts; do not simulate two actual Firebase accounts.
    print("DB_R31_11_2_TWO_FIREBASE_USERS=PENDING_DISTINCT_APPROVED_ACCOUNT",
          flush=True)
    print("DB_R31_11_2_HTTPS_E2E=PENDING_APPROVED_RESTRICTED_ROUTE",
          flush=True)
    print("DB_R31_11_2_RUNTIME_TENANT_RLS=NOT_CONNECTED_TO_FIREBASE",
          flush=True)
    print("DB_R31_11_2_RECONCILIATION_INVOICE_GST=QUARANTINED_R3112",
          flush=True)
    print("DB_R31_11_2_PRODUCTION_FINANCIAL_WRITES=NONE_BY_TEST",
          flush=True)
    if not (anon_ok and route_ok):
        print("DB_R31_11_2_RELEASE=BLOCKED_SECURITY_NEGATIVE_QA_FAILED",
              flush=True)
        return 2
    print("DB_R31_11_2_RELEASE=STAGING_SECURITY_CHECKS_PASS_PRODUCTION_BLOCKED",
          flush=True)
    return 2


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,RuntimeError,ValueError,TimeoutError):
        print("STOP=DB_R31_11_2_RUNTIME_UNAVAILABLE",flush=True)
        raise SystemExit(2)
