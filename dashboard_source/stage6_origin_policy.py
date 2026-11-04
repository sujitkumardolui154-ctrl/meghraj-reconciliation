"""Stage 6C explicit same-origin allowlist. No wildcard or inferred origin.

Cloud Run configuration is unchanged by default. AWS private staging requires
an exact HTTPS origin to be configured; missing/invalid configuration fails closed.
This module is pure and does not read credentials or perform network calls.
"""
import os
from urllib.parse import urlsplit

CLOUD_RUN_ORIGINS = frozenset({
    "https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://sbi-dashboard-109590290120.asia-south1.run.app",
    "https://sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://imports-v140---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
})
AWS_PROFILE = "aws-private-staging"

def private_aws_origin(env=None):
    env = os.environ if env is None else env
    profile = env.get("SBI_STAGE6_AUTH_PROFILE", "")
    if profile != AWS_PROFILE:
        return None
    origin = env.get("SBI_STAGE6_AWS_ORIGIN", "")
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        return None
    try:
        url = urlsplit(origin)
        host = url.hostname or ""
        if (url.scheme != "https" or url.username is not None
            or url.password is not None or url.port not in (None, 443)
            or url.path or url.query or url.fragment
            or host != host.lower()
            or not host.endswith(".sslip.io")
            or host.startswith(".") or "*" in host or "/" in host
            or origin != "https://" + host):
            return None
    except ValueError:
        return None
    return origin

def is_allowed_origin(origin, env=None, cloud_origins=None):
    env = os.environ if env is None else env
    profile = env.get("SBI_STAGE6_AUTH_PROFILE", "")
    if profile == AWS_PROFILE:
        valid = private_aws_origin(env)
        return bool(valid and origin == valid)
    if profile:  # unknown profile never enables a new origin
        return False
    return origin in (CLOUD_RUN_ORIGINS if cloud_origins is None else cloud_origins)

def aws_private_mode(env=None):
    env = os.environ if env is None else env
    return env.get("SBI_STAGE6_AUTH_PROFILE", "") == AWS_PROFILE
