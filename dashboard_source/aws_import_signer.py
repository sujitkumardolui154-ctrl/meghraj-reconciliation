"""AWS private invoice-import service request signing.

Synthetic-testable HMAC authentication. This is not AWS IAM identity.
Requires a dedicated, high-entropy secret mounted as a file in the gateway
and backend (never reuse preview credentials). No implicit fallback.
"""
import hashlib
import hmac
import os
import secrets
import time


MAX_BYTES = 8 * 1024 * 1024 + 65536


def _key(path):
    if not path or not os.path.isabs(path):
        raise ValueError("Dedicated service key file path required")
    with open(path, "rb") as stream:
        key = stream.read(257)
    if not 32 <= len(key) <= 256:
        raise ValueError("Invalid service key length")
    return key


def sign_prepared_import(prepared, *, key_path=None, now=None, nonce=None):
    """Sign the EXACT prepared wire body and path, including query string."""
    if prepared.method not in ("GET", "POST"):
        raise ValueError("Unsupported method")
    body = prepared.body or b""
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ValueError("Invalid import body")
    path = prepared.path_url
    if not path.startswith("/imports/") or "\n" in path or "\r" in path:
        raise ValueError("Invalid signed route")
    timestamp = str(int(time.time() if now is None else now))
    nonce = secrets.token_hex(16) if nonce is None else nonce
    if len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("Invalid nonce")
    digest = hashlib.sha256(body).hexdigest()
    payload = ("sbi-import-v1\n" + prepared.method + "\n" + path + "\n"
               + timestamp + "\n" + nonce + "\n" + digest).encode("ascii")
    signature = hmac.new(_key(key_path or os.environ.get("SBI_AWS_IMPORT_KEY_FILE")),
                         payload, hashlib.sha256).hexdigest()
    prepared.headers["Authorization"] = "SBI-HMAC-SHA256 " + signature
    prepared.headers["X-SBI-Auth-Timestamp"] = timestamp
    prepared.headers["X-SBI-Auth-Nonce"] = nonce
    return prepared
