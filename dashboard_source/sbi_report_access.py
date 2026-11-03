"""A01: explicit role authorization for non-CREDIT NOTE dashboard reports.

The calling Flask app must first verify the Firebase session cookie and
populate g.dil_user/g.dil_identity through dashboard_sessions.install_sessions.
This helper performs no authentication or cloud access on its own.
CREDIT NOTE uses its existing separate sbi_credit_report_viewer contract.
"""

GENERAL_REPORT_CLAIM = "sbi_report_viewer"
CHANGE_REPORT_CLAIM = "sbi_reconciliation_change_viewer"


def can_view_report(user, identity, *, change_report=False):
    """Fail closed unless a verified session user has explicit report claims.

    A dashboard login alone or administrator label alone is insufficient
    authorization for invoices, financial changes, and customer report data.
    """
    if user is None or not isinstance(identity, dict):
        return False
    uid = getattr(user, "uid", None)
    if not isinstance(uid, str) or not uid or identity.get("uid") != uid:
        return False
    if getattr(user, "disabled", True) is not False:
        return False
    claims = getattr(user, "custom_claims", None)
    if not isinstance(claims, dict):
        return False
    if claims.get("dil_dashboard") is not True:
        return False
    if claims.get(GENERAL_REPORT_CLAIM) is not True:
        return False
    if change_report and claims.get(CHANGE_REPORT_CLAIM) is not True:
        return False
    return True

IMPORT_CLAIM = "sbi_invoice_importer"


def can_import_invoice(user, identity):
    """Require a verified, enabled Firebase user with an explicit import claim.

    Neither dashboard access, the administrator label nor report-viewer claims
    confer permission to preview, inspect receipts or apply invoice imports.
    """
    if user is None or not isinstance(identity, dict):
        return False
    uid = getattr(user, "uid", None)
    if not isinstance(uid, str) or not uid or identity.get("uid") != uid:
        return False
    if getattr(user, "disabled", True) is not False:
        return False
    claims = getattr(user, "custom_claims", None)
    return (
        isinstance(claims, dict)
        and claims.get("dil_dashboard") is True
        and claims.get(IMPORT_CLAIM) is True
    )
