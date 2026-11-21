#!/usr/bin/env python3
"""Patch one legacy/main Caddy route block, not a site header.

A Caddyfile can have multiple hostnames or generic site declarations.
Identify the main route by @legacy, @login and default backend markers.
Keep all other sites unchanged, retain the legacy proxy, and require
Caddy validation by the invoking deployment script before cutover.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


class StopRelease(Exception):
    pass


def stop(reason: str):
    raise StopRelease("STOP_" + reason)


ROUTE = re.compile(r"(?m)^[ \t]*route[ \t]*\{[ \t]*(?:#[^\n]*)?$")
LEGACY = re.compile(
    r"(?m)(^[ \t]*handle[ \t]+@legacy[ \t]*\{[ \t]*\n"
    r"[ \t]*reverse_proxy[ \t]+)sbi-preview:8080(?=[ \t]*$)"
)
LOGIN = re.compile(
    r"(?m)(^[ \t]*handle[ \t]+@login[ \t]*\{[ \t]*\n"
    r"[ \t]*reverse_proxy[ \t]+)sbi-source-reports-v1:8080(?=[ \t]*$)"
)
DEFAULT = re.compile(
    r"(?m)(^[ \t]*handle[ \t]*\{[ \t]*\n"
    r"[ \t]*reverse_proxy[ \t]+)sbi-preview:8080(?=[ \t]*$)"
)


def brace_end(text: str, at: int) -> int:
    start = text.find("{", at)
    if start < 0:
        stop("MAIN_ROUTE_UNBALANCED")
    depth, in_quote, escaped, in_comment = 0, False, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "\n":
            in_comment = False
            continue
        if in_comment:
            continue
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_quote:
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch == "#" and not in_quote:
            in_comment = True
            continue
        if in_quote:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
            if depth < 0:
                stop("MAIN_ROUTE_UNBALANCED")
    stop("MAIN_ROUTE_UNBALANCED")


def patch(original: str, target: str, host: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,95}", target):
        stop("INVALID_CANDIDATE_NAME")
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        stop("INVALID_MAIN_HOST")
    if host not in original:
        stop("MAIN_PUBLIC_HOST_NOT_IN_CADDY")
    if "sbi-bulk-report-pr129-https-preview:8080" not in original:
        stop("WORKING_PR129_PREVIEW_ROUTE_MISSING")

    matches = []
    for found in ROUTE.finditer(original):
        end = brace_end(original, found.start())
        block = original[found.start():end]
        if LEGACY.search(block) and LOGIN.search(block) and DEFAULT.search(block):
            matches.append((found.start(), end, block))
    if len(matches) != 1:
        stop("MAIN_ROUTE_NOT_UNIQUE")
    start, end, block = matches[0]

    if re.search(r"(?m)^\s*handle(?:_path)?\s+/api/bulk-report", block):
        stop("BULK_REPORT_ROUTE_ALREADY_EXISTS")
    if re.search(r"(?m)^\s*handle_path\s+", block):
        stop("UNVERIFIED_PATH_STRIPPING_IN_MAIN_ROUTE")
    if len(LEGACY.findall(block)) != 1:
        stop("LEGACY_MATCH_NOT_EXACTLY_ONE")
    if len(LOGIN.findall(block)) != 1 or len(DEFAULT.findall(block)) != 1:
        stop("LOGIN_OR_DEFAULT_NOT_EXACTLY_ONE")

    block, login_count = LOGIN.subn(
        lambda m: m.group(1) + target + ":8080", block
    )
    block, default_count = DEFAULT.subn(
        lambda m: m.group(1) + target + ":8080", block
    )
    if login_count != 1 or default_count != 1 or len(LEGACY.findall(block)) != 1:
        stop("LEGACY_LOGIN_DEFAULT_PROXY_PARITY")

    opening = ROUTE.search(block)
    if not opening or opening.start() != 0:
        stop("MAIN_ROUTE_OPEN_UNEXPECTED")
    indentation = re.match(r"[ \t]*", block).group(0) + "    "
    injection = (
        "\n" + indentation + "handle /api/bulk-report/* {\n"
        + indentation + "    reverse_proxy " + target + ":8080\n"
        + indentation + "}\n"
    )
    block = block[:opening.end()] + injection + block[opening.end():]
    updated = original[:start] + block + original[end:]
    if updated[:start] != original[:start] or not updated.endswith(original[end:]):
        stop("NON_MAIN_ROUTE_CHANGED")
    if updated.count("sbi-bulk-report-pr129-https-preview:8080") != original.count(
        "sbi-bulk-report-pr129-https-preview:8080"
    ):
        stop("PR129_PREVIEW_ROUTE_CHANGED")
    if len(LEGACY.findall(block)) != 1 or block.count(target + ":8080") != 3:
        stop("FINAL_ROUTE_INTEGRITY")
    return updated


def selftest() -> None:
    main_route = (
        "    route {\n"
        "        handle @legacy {\n"
        "            reverse_proxy sbi-preview:8080\n"
        "        }\n"
        "        handle @login {\n"
        "            reverse_proxy sbi-source-reports-v1:8080\n"
        "        }\n"
        "        handle {\n"
        "            reverse_proxy sbi-preview:8080\n"
        "        }\n"
        "    }\n"
    )
    other = (
        "pr129.13-232-241-221.sslip.io {\n"
        "    reverse_proxy sbi-bulk-report-pr129-https-preview:8080\n"
        "}\n"
    )
    host = "sbi-preview.13-232-241-221.sslip.io"
    for header in (host + " {\n", host + ", example.internal {\n"):
        sample = header + main_route + "}\n" + other
        result = patch(sample, "sbi-reports-main-test123", host)
        assert "handle /api/bulk-report/* {" in result
        assert result.count("sbi-reports-main-test123:8080") == 3
        assert "reverse_proxy sbi-preview:8080" in result
        assert result.endswith(other)
        try:
            patch(result, "sbi-reports-main-test123", host)
        except StopRelease as exc:
            assert "ALREADY_EXISTS" in str(exc)
        else:
            raise AssertionError("Double cutover not blocked")
    print("MAIN_CADDY_ROUTE_PATCH_SYNTHETIC=PASS")


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        selftest()
        return
    if len(sys.argv) != 4:
        stop("USAGE_REQUIRE_PROPOSED_FILE_CANDIDATE_MAIN_HOST")
    path = Path(sys.argv[1])
    before = path.read_text(encoding="utf-8")
    after = patch(before, sys.argv[2], sys.argv[3])
    path.write_text(after, encoding="utf-8")
    print("MAIN_LOGIN_PROXY=REPAIRED")
    print("MAIN_DEFAULT_DASHBOARD_PROXY=PROMOTED")
    print("MAIN_EXPLICIT_REPORT_API_PROXY=ADDED")
    print("MAIN_LEGACY_API_UPSTREAM=PRESERVED")
    print("OTHER_GATEWAY_SITES=UNCHANGED")


if __name__ == "__main__":
    try:
        main()
    except StopRelease as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
