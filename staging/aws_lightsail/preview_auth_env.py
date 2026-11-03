#!/usr/bin/env python3
"""Preserve ONLY existing isolated-preview login variables for a staging rollout.

Reads the JSON array from `docker inspect --format '{{json .Config.Env}}'`
on stdin. Writes a pre-created, owner-only temporary env file. No credentials
are logged, and unrelated (possibly financial) environment variables are
never copied into the new container.
"""
from __future__ import annotations

import json
import os
import stat
import sys

KEYS = ("PREVIEW_USERNAME", "PREVIEW_PASSWORD")


def approved_preview_env(entries: object) -> dict[str, str]:
    if not isinstance(entries, list):
        raise ValueError("Docker environment must be a JSON array")
    result: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, str) or "=" not in item:
            raise ValueError("Invalid Docker environment entry")
        key, value = item.split("=", 1)
        if key not in KEYS:
            continue
        if key in result:
            raise ValueError("Duplicate preview credential")
        if any(char in value for char in ("\n", "\r", "\0")):
            raise ValueError("Preview credentials cannot contain line breaks or NUL")
        result[key] = value
    username = result.get("PREVIEW_USERNAME", "")
    password = result.get("PREVIEW_PASSWORD", "")
    if not username or ":" in username or len(password) < 20:
        raise ValueError("Existing preview login is missing or invalid")
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("BLOCKED: expected pre-created temporary env-file path", file=sys.stderr)
        return 2
    try:
        values = approved_preview_env(json.load(sys.stdin))
        path = argv[1]
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Destination must be an existing mode-0600 regular file")
        flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            for key in KEYS:
                target.write(f"{key}={values[key]}\n")
        print("PREVIEW_CREDENTIALS=VERIFIED")
        return 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError):
        # Do not print source values or exception messages containing secrets.
        print("BLOCKED: existing preview credentials could not be safely preserved", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
