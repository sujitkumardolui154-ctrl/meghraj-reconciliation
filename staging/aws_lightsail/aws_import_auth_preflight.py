"""AWS Lightsail import-auth *deployment preflight* (no cloud calls).

This module does not authenticate requests. AWS deployment is blocked until
a real, independently verified service-to-service auth boundary is installed.
Never treat the preview Basic Auth user or a forwarded identity header as a
service identity. This preflight is deliberately restrictive.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AWSAuthReadiness:
    ready: bool
    blockers: tuple[str, ...]


def evaluate_aws_import_readiness(config=None):
    """Pure check; never returns secrets or contacts AWS/Firestore."""
    cfg = os.environ if config is None else config
    blockers = []
    if cfg.get("SBI_AWS_GATEWAY_AUTH_VERIFIED") != "true":
        blockers.append("independent_gateway_auth_not_verified")
    if cfg.get("SBI_AWS_BACKEND_AUTH_VERIFIED") != "true":
        blockers.append("independent_backend_auth_not_verified")
    if cfg.get("SBI_AWS_PRIVATE_NETWORK_VERIFIED") != "true":
        blockers.append("private_network_not_verified")
    if cfg.get("SBI_AWS_NO_FINANCIAL_WRITES") != "true":
        blockers.append("financial_write_deny_not_verified")
    # These are operator assertions only, never sufficient authorization.
    # Until independent proof exists, all staging import execution stays shut.
    blockers.append("external_auth_evidence_required")
    return AWSAuthReadiness(ready=False, blockers=tuple(blockers))


if __name__ == "__main__":
    result = evaluate_aws_import_readiness()
    print("AWS_IMPORT_STAGE_READY=NO")
    for reason in result.blockers:
        print("BLOCKER=" + reason)
    raise SystemExit(2)
