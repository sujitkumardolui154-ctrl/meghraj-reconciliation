#!/usr/bin/env python3
"""Controlled Firebase viewer-role provisioning; DRY-RUN is default.

Never grants a user financial DB write/admin roles or touches invoice data.
Must run in authorized Google Cloud Shell/secure operator host with Firebase
IAM, a verified target account, and an independently approved access ticket.

Dry run:
 python tools/sbi_reporting_role_provision.py --target-uid UID \
   --target-email EMAIL --grant-general
Review the claims SHA from dry-run. To actually grant requires all:
 --apply --approved-ticket REF --expected-claims-sha256 HASH
and operator must type an exact interactive confirmation.
Do NOT share Firebase tokens, user email, credentials or claim details in chat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

PROJECT = "meghraj-reconciliation"
GENERAL = "sbi_report_viewer"
CHANGES = "sbi_reconciliation_change_viewer"
HEX_RE = re.compile(r"[a-f0-9]{64}\Z")


class RoleProvisionBlocked(ValueError):
    pass


def claims_hash(claims):
    if not isinstance(claims, dict):
        raise RoleProvisionBlocked("USER_CUSTOM_CLAIMS_INVALID")
    return hashlib.sha256(json.dumps(
        claims, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def plan(user, expected_uid, expected_email, *,
         grant_general=False, grant_changes=False):
    """Pure function. No identity writes or external Firebase access."""
    if (not isinstance(expected_uid, str) or not expected_uid.strip()
            or not isinstance(expected_email, str)
            or expected_email.count("@") != 1):
        raise RoleProvisionBlocked("EXPLICIT_TARGET_IDENTITY_REQUIRED")
    if (getattr(user, "uid", None) != expected_uid
            or str(getattr(user, "email", "")).casefold()
            != expected_email.casefold()
            or getattr(user, "disabled", True) is not False):
        raise RoleProvisionBlocked("FIREBASE_TARGET_UID_EMAIL_NOT_VERIFIED")
    original = getattr(user, "custom_claims", None) or {}
    if not isinstance(original, dict) or original.get("dil_dashboard") is not True:
        raise RoleProvisionBlocked("DASHBOARD_VIEWER_ROLE_NOT_VERIFIED")
    if not grant_general and not grant_changes:
        raise RoleProvisionBlocked("NO_ROLE_REQUESTED")
    if grant_changes and not grant_general and original.get(GENERAL) is not True:
        raise RoleProvisionBlocked("CHANGE_VIEWER_REQUIRES_GENERAL_REPORT_VIEWER")
    new_claims = dict(original)
    if grant_general:
        new_claims[GENERAL] = True
    if grant_changes:
        new_claims[CHANGES] = True
    if len(json.dumps(new_claims)) > 900:
        raise RoleProvisionBlocked("FIREBASE_CUSTOM_CLAIMS_CAP_NEAR_LIMIT")
    return original, new_claims


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-uid", required=True)
    parser.add_argument("--target-email", required=True)
    parser.add_argument("--grant-general", action="store_true")
    parser.add_argument("--grant-changes", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-ticket")
    parser.add_argument("--expected-claims-sha256")
    args = parser.parse_args(argv)
    try:
        import firebase_admin
        from firebase_admin import auth

        app = firebase_admin.initialize_app(
            options={"projectId": PROJECT}, name="sbi-report-role-provision"
        )
        user = auth.get_user(args.target_uid, app=app)
        before, after = plan(
            user, args.target_uid, args.target_email,
            grant_general=args.grant_general,
            grant_changes=args.grant_changes,
        )
        current_hash = claims_hash(before)
        print("PROJECT=" + PROJECT)
        print("IDENTITY_UID_EMAIL_MATCH=PASS")
        print("CURRENT_CLAIMS_SHA256=" + current_hash)
        print("CHANGE_REQUESTED=" + ("YES" if after != before else "NO"))
        print("FINANCIAL_DATA_WRITES=0")
        if not args.apply:
            print("ROLE_PROVISIONING=DRY_RUN_ONLY")
            return 0
        if (not args.approved_ticket
                or len(args.approved_ticket.strip()) < 8
                or not args.expected_claims_sha256
                or HEX_RE.fullmatch(args.expected_claims_sha256) is None
                or args.expected_claims_sha256 != current_hash):
            raise RoleProvisionBlocked("APPROVAL_TICKET_OR_CURRENT_CLAIMS_HASH_REQUIRED")
        if before == after:
            print("ROLE_PROVISIONING=ALREADY_GRANTED_NO_CHANGE")
            return 0
        if not sys.stdin.isatty():
            raise RoleProvisionBlocked("INTERACTIVE_CONFIRMATION_REQUIRED")
        confirmation = "GRANT REPORT VIEWER " + args.target_uid[-6:]
        typed = input("Type " + confirmation + " to authorize role change: ")
        if typed != confirmation:
            raise RoleProvisionBlocked("OPERATOR_DID_NOT_CONFIRM")
        # Non-financial security change, explicitly approved for this exact
        # Firebase identity and original claims digest; no other IAM changes.
        auth.set_custom_user_claims(args.target_uid, after, app=app)
        observed = auth.get_user(args.target_uid, app=app)
        if observed.custom_claims != after:
            raise RoleProvisionBlocked("POST_GRANT_CLAIMS_READBACK_MISMATCH")
        print("ROLE_PROVISIONING=APPLIED_VERIFIED")
        print("NEW_CLAIMS_SHA256=" + claims_hash(after))
        print("USER_MUST_RELOGIN_FOR_NEW_CLAIMS=YES")
        print("SIGNED_IN_HTTP_E2E=STILL_REQUIRED")
        return 0
    except RoleProvisionBlocked as error:
        print("ROLE_PROVISIONING=REVIEW_REQUIRED")
        print("BLOCKER=" + str(error))
        print("FINANCIAL_DATA_WRITES=0")
        return 2
    except Exception:
        print("ROLE_PROVISIONING=REVIEW_REQUIRED")
        print("BLOCKER=FIREBASE_IDENTITY_OR_IAM_OPERATION_FAILED")
        print("FINANCIAL_DATA_WRITES=0")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
