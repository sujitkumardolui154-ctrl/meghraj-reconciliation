#!/usr/bin/env python3
"""R31.11.4J — combined prior 4I acceptance + loopback mTLS rehearsal.

No real Caddy configuration change, new internet-facing listener, cert
deployment, firewall opening, Firebase sign-in, database writes or financial
Apply. Default is READ-ONLY audit; optional --mode loopback creates a
synthetic localhost-only TLS listener and disposable private test certs.
"""
from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode=True

import r31_11_4h_combined_readonly_security as h
import r31_11_4i_combined_auth_mtls as i
import r31_11_4g_mtls_readonly_preflight as g
import r31_11_4j_loopback_mtls as tls

# Source SHA for the actual R31.11.4I private-auth operator invocation. The
# user-supplied AWS screenshot shows the local operator receipt succeeded.
# 4J checks this original local source provenance explicitly, not the new
# 4J working-tree SHA and not a reconstructed prior 4F log.
APPROVED_4I_SOURCE_SHA="f5b3088b2306cd6b435f4e6f1cd3e107dc88879f"


class GateBlocked(RuntimeError):
    pass


def require(ok,code):
    if not ok:
        raise GateBlocked(code)


def audit_baseline(sha):
    h.run_combined(sha)
    print("DB_R31_11_4J_PRIVATE_RLS_AUTH_AND_CADDY=PASS_COMBINED_4H_READONLY",
          flush=True)

    # Version and review-only placeholder syntax are inspected. This is not
    # an external TLS handshake or a live-approved QA hostname.
    i.verify_mtls_design_only()

    require(i.RECEIPT.is_file() and not i.RECEIPT.is_symlink(),
            "QA_AUTH_RECEIPT_MISSING_OR_SYMLINK")
    i.audit_local_receipt(APPROVED_4I_SOURCE_SHA)
    print("DB_R31_11_4J_4I_REAL_AUTH_LOCAL_RECEIPT=PASS_SOURCE_PINNED_OPERATOR_REPORT",
          flush=True)

    require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
            "QA_CADDY_HASH_DRIFT")
    g.check_database_isolation()
    g.ephemeral_cleanup()
    print("DB_R31_11_4J_DB_NETWORK_CADDY_AND_TEMP_CLEANUP=PASS_READONLY",
          flush=True)

    # There is no approved real DNS/CA/cert/ingress in source or in evidence.
    print("DB_R31_11_4J_REAL_QA_FQDN=NOT_APPROVED",flush=True)
    print("DB_R31_11_4J_REAL_CLIENT_CA_AND_CERTS=NOT_APPROVED",flush=True)
    print("DB_R31_11_4J_REAL_MTLS_INGRESS=NOT_DEPLOYED",flush=True)


def main(argv=None):
    p=argparse.ArgumentParser(description="R31.11.4J guarded mTLS readiness")
    p.add_argument("--source-sha",required=True)
    p.add_argument("--mode",choices=("audit","loopback"),default="audit")
    args=p.parse_args(argv)
    print("=== DB-R31.11.4J MTLS SECURITY ACCEPTANCE CANDIDATE ===",flush=True)
    try:
        audit_baseline(args.source_sha)
        if args.mode=="loopback":
            print("DB_R31_11_4J_MODE=SYNTHETIC_LOOPBACK_ONLY",flush=True)
            tls.run_synthetic()
            # Re-run actual previously-accepted source/owner/PG/Caddy checks
            # after disposable local TCP TLS activity. No production change.
            h.run_combined(args.source_sha)
            require(g.caddy_preflight()==h.EXPECTED_4G_CADDY_SHA256,
                    "QA_CADDY_HASH_DRIFT")
            g.check_database_isolation()
            g.ephemeral_cleanup()
            print("DB_R31_11_4J_POST_LOOPBACK_DB_CADDY=PASS_UNCHANGED",flush=True)
        else:
            print("DB_R31_11_4J_MODE=READONLY_NO_NETWORK_LISTENER",flush=True)
        print("DB_R31_11_4J_COMBINED_PREPARATION=PASS_NOT_EXTERNAL_ACCEPTANCE",
              flush=True)
        return 0
    except Exception:
        # Never print Firebase identifiers, Caddy config, certificates,
        # SQL rows, cloud credentials, raw Python TLS exception data.
        print("STOP=DB_R31_11_4J_SECURITY_ACCEPTANCE_REVIEW_REQUIRED",flush=True)
        return 2
    finally:
        print("DB_R31_11_4J_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4J_REAL_CERT_REVOCATION=NOT_TESTED",flush=True)
        print("DB_R31_11_4J_REAL_FIREBASE_EXPIRED_REVOKED_SESSION=NOT_TESTED",
              flush=True)
        print("DB_R31_11_4J_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED",flush=True)
        print("DB_R31_11_4J_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4J_PRODUCTION_RELEASE=BLOCKED",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
