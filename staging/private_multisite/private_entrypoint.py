"""Private-only opt-in WSGI adapter for a *separate, approved* QA image.

This module must not be used behind the existing public Caddy listener.
Bind the candidate host port to loopback only, use tailnet-only Tailscale
Serve HTTPS, and verify both Lightsail IPv4 + IPv6 firewall exposure.
"""
import os
from private_origin import configured_private_origin

# Fail closed BEFORE importing the application or opening app routes.
origin = configured_private_origin(os.environ)
if origin is None:
    raise RuntimeError("PRIVATE_TAILNET_MODE_REQUIRED_FOR_PRIVATE_ENTRYPOINT")

from app import app  # noqa: E402
from dashboard_sessions import ORIGINS  # noqa: E402

# Explicitly replace, not append to, the legacy Cloud Run/sslip origin list.
ORIGINS.clear()
ORIGINS.add(origin)

# Exact Host allowlist (Flask 3.1+). This is additional defense, NOT a
# substitute for server bind/firewall/grants. Do not trust X-Forwarded-* blindly.
app.config["TRUSTED_HOSTS"] = [origin.removeprefix("https://")]
