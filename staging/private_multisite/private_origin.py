"""Opt-in exact private HTTPS origin for multi-location Tailscale access.

Defaults to legacy mode; this does NOT make an application private by itself.
The AWS public firewall, Docker publishing and Caddy exposure must be separately
restricted and independently validated before declaring tailnet-only access.
"""
import re
from urllib.parse import urlsplit

MODE_KEY = "SBI_PRIVATE_ACCESS_MODE"
ORIGIN_KEY = "SBI_PRIVATE_TAILNET_ORIGIN"
APPROVED_MODE = "tailnet-staff-only-v1"
LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_private_origin(value):
    """Require a canonical, exact https://machine.tailnet.ts.net origin."""
    if not isinstance(value, str) or len(value) > 255 or value != value.strip():
        raise ValueError("PRIVATE_ORIGIN_MISSING_OR_UNSAFE")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("PRIVATE_ORIGIN_INVALID") from None
    host = parsed.hostname or ""
    parts = host.split(".")
    if not (
        parsed.scheme == "https"
        and parsed.netloc == host
        and port is None
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and len(parts) == 4
        and parts[2:] == ["ts", "net"]
        and all(LABEL.fullmatch(p) for p in parts[:2])
        and value == "https://" + host
    ):
        raise ValueError("PRIVATE_ORIGIN_NOT_EXACT_TAILNET_HTTPS")
    return value


def configured_private_origin(environment):
    """Fail closed on partial/unknown mode; never trust arbitrary Host headers."""
    mode = environment.get(MODE_KEY, "")
    origin = environment.get(ORIGIN_KEY, "")
    if not mode and not origin:
        return None
    if mode != APPROVED_MODE:
        raise ValueError("PRIVATE_ACCESS_MODE_NOT_APPROVED")
    return validate_private_origin(origin)
