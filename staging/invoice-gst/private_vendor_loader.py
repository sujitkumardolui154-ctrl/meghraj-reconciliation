"""Private vendor-profile archive intake for isolated invoice_qa PostgreSQL.

NEVER store logo, invoice, PAN, GSTIN or bank instructions in public GitHub.
Requires a local private ZIP containing vendor_profile.json, meghraj_logo.webp
and manifest.json. Native XLSX layout certification is handled separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile


REQUIRED_FIELDS = (
    "legal_name", "declaration_text", "bank_instructions",
    "pan", "gstin", "vendor_id", "service_type", "sac_code",
    "footer_text", "authorized_signature_label",
    "registered_office", "registered_phone", "registered_email",
    "head_office", "head_phone", "website",
)


def unpack_verified_bundle(path):
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        expected = {"vendor_profile.json", "meghraj_logo.webp",
                    "manifest.json", "README_PRIVATE.txt"}
        if names != expected:
            raise ValueError("PRIVATE_BUNDLE_FILESET_MISMATCH")
        payload = archive.read("vendor_profile.json")
        image = archive.read("meghraj_logo.webp")
        manifest = json.loads(archive.read("manifest.json"))
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if manifest.get("package_type") != "SBI_INVOICE_GST_PRIVATE_VENDOR_PROFILE":
        raise ValueError("INVALID_VENDOR_PACKAGE")
    if manifest.get("logo_sha256") != digest(image):
        raise ValueError("LOGO_DIGEST_MISMATCH")
    if manifest.get("vendor_profile_json_sha256") != digest(payload):
        raise ValueError("PROFILE_DIGEST_MISMATCH")
    if manifest.get("native_original_xlsx_available") is not False:
        raise ValueError("NATIVE_LAYOUT_CLAIM_REQUIRES_SEPARATE_REVIEW")
    if manifest.get("layout_certification") != "REFERENCE_PREVIEW_ONLY_NOT_PIXEL_EXACT":
        raise ValueError("PDF_LAYOUT_CLAIM_UNVERIFIED")
    profile = json.loads(payload)
    if profile.get("vendor_key") != "MEGHRAJ_EXPRESS":
        raise ValueError("VENDOR_KEY_MISMATCH")
    if profile.get("legal_name") != "MEGHRAJ EXPRESS":
        raise ValueError("VENDOR_NAME_MISMATCH")
    if profile.get("logo_mime") != "image/webp":
        raise ValueError("LOGO_MIME_MISMATCH")
    for key in REQUIRED_FIELDS:
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise ValueError("MISSING_VENDOR_" + key.upper())
    if len(image) > 2_000_000:
        raise ValueError("LOGO_FILE_TOO_LARGE")
    # Verify the image can really be decoded, rather than trusting extension.
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(image)) as logo:
        if logo.format != "WEBP" or logo.width < 100 or logo.height < 30:
            raise ValueError("INVALID_VENDOR_LOGO")
        logo.verify()
    return profile, image, manifest


def apply_only_isolated_qa(dsn, archive, reviewer):
    if not isinstance(reviewer, str) or not re.fullmatch(r"[A-Za-z0-9_@.-]{3,80}", reviewer):
        raise ValueError("REVIEWER_ID_REQUIRED")
    profile, logo, manifest = unpack_verified_bundle(archive)
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=6) as conn:
        database = conn.execute("SELECT current_database() AS db").fetchone()["db"]
        if database != "invoice_qa":
            raise ValueError("REFUSE_NON_ISOLATED_QA_DATABASE")
        # Owner approval locks the exact historical vendor profile. An import
        # may be repeated idempotently, but can never overwrite a different
        # logo, GST number, bank instruction, legal declaration or header.
        expected = {
            **{key: profile[key] for key in REQUIRED_FIELDS},
            "logo_image": logo, "logo_mime": profile["logo_mime"],
        }
        columns = list(expected)
        existing = conn.execute(
            """SELECT * FROM sbi_invoice_gst.vendor_profiles
               WHERE vendor_key='MEGHRAJ_EXPRESS' FOR UPDATE"""
        ).fetchone()
        if existing:
            if (
                existing["exact_logo_verified"] is not True or
                existing["verified_at"] is None or
                any(
                    bytes(existing[key]) != value
                    if key == "logo_image" else existing[key] != value
                    for key, value in expected.items()
                )
            ):
                raise ValueError("VENDOR_PROFILE_CONFLICT_NEW_OWNER_APPROVAL_REQUIRED")
            return {
                "status": "PRIVATE_VENDOR_QA_PROFILE_ALREADY_VERIFIED_UNCHANGED",
                "logo_sha256": manifest["logo_sha256"],
                "layout_certification": manifest["layout_certification"],
                "production_write": False,
            }
        conn.execute(
            """INSERT INTO sbi_invoice_gst.vendor_profiles
               (vendor_key, legal_name, logo_image, logo_mime, exact_logo_verified,
                declaration_text, bank_instructions, pan, gstin, vendor_id,
                service_type, sac_code, footer_text, authorized_signature_label,
                registered_office, registered_phone, registered_email,
                head_office, head_phone, website, verified_by, verified_at)
               VALUES ('MEGHRAJ_EXPRESS',%s,%s,%s,TRUE,
                       %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
               ON CONFLICT (vendor_key) DO NOTHING""",
            (profile["legal_name"], logo, profile["logo_mime"],
             profile["declaration_text"], profile["bank_instructions"],
             profile["pan"], profile["gstin"], profile["vendor_id"],
             profile["service_type"], profile["sac_code"], profile["footer_text"],
             profile["authorized_signature_label"],
             profile["registered_office"], profile["registered_phone"],
             profile["registered_email"], profile["head_office"],
             profile["head_phone"], profile["website"], reviewer),
        )
    return {
        "status": "PRIVATE_VENDOR_QA_PROFILE_LOADED",
        "logo_sha256": manifest["logo_sha256"],
        "layout_certification": manifest["layout_certification"],
        "production_write": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--qa-dsn-env", default="SBI_INVOICE_GST_TEST_DSN")
    args = parser.parse_args()
    import os
    dsn = os.environ.get(args.qa_dsn_env)
    if not dsn:
        raise SystemExit("QA_DSN_NOT_CONFIGURED")
    result = apply_only_isolated_qa(dsn, args.bundle, args.reviewer)
    # Never print vendor legal or bank details to CI or terminal logs.
    print("IMPORT_RESULT=", result["status"])
    print("LOGO_DIGEST=", result["logo_sha256"])
    print("PDF_LAYOUT_STATUS=", result["layout_certification"])
