"""Private vendor import contract tests: synthetic data, no real vendor assets."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from io import BytesIO
import hashlib
import json
import tempfile
import unittest
import zipfile

from PIL import Image


SOURCE = Path(__file__).resolve().parents[1] / "staging/invoice-gst/private_vendor_loader.py"
spec = spec_from_file_location("private_vendor_loader", SOURCE)
loader = module_from_spec(spec)
spec.loader.exec_module(loader)


def synthetic_zip(folder, *, corrupt_logo=False, layout_override=None):
    logo = BytesIO()
    Image.new("RGB", (306,105), (210,230,250)).save(logo, "WEBP")
    good_logo = logo.getvalue()
    profile = {key:"QA PLACEHOLDER" for key in loader.REQUIRED_FIELDS}
    profile.update({"vendor_key":"MEGHRAJ_EXPRESS",
                    "legal_name":"MEGHRAJ EXPRESS","logo_mime":"image/webp"})
    profile_bytes = (json.dumps(profile,indent=2)+"\n").encode()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    manifest = {
        "package_type": "SBI_INVOICE_GST_PRIVATE_VENDOR_PROFILE",
        "native_original_xlsx_available": False,
        "layout_certification": layout_override or "REFERENCE_PREVIEW_ONLY_NOT_PIXEL_EXACT",
        "logo_sha256": digest(good_logo),
        "vendor_profile_json_sha256": digest(profile_bytes),
    }
    out = folder / "synthetic-private.zip"
    with zipfile.ZipFile(out,"w") as archive:
        archive.writestr("manifest.json",json.dumps(manifest))
        archive.writestr("vendor_profile.json",profile_bytes)
        archive.writestr("meghraj_logo.webp",
                         good_logo + b"INVALID" if corrupt_logo else good_logo)
        archive.writestr("README_PRIVATE.txt","SYNTHETIC QA")
    return out


class PrivateAssetContract(unittest.TestCase):
    def test_valid_source_logo_and_profile_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            profile, logo, manifest = loader.unpack_verified_bundle(
                synthetic_zip(Path(folder))
            )
            self.assertEqual(profile["vendor_key"], "MEGHRAJ_EXPRESS")
            self.assertEqual(hashlib.sha256(logo).hexdigest(),
                             manifest["logo_sha256"])
            self.assertEqual(manifest["layout_certification"],
                             "REFERENCE_PREVIEW_ONLY_NOT_PIXEL_EXACT")

    def test_tampered_logo_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,"LOGO_DIGEST_MISMATCH"):
                loader.unpack_verified_bundle(synthetic_zip(Path(folder),corrupt_logo=True))

    def test_false_pixel_exact_claim_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,"PDF_LAYOUT_CLAIM_UNVERIFIED"):
                loader.unpack_verified_bundle(
                    synthetic_zip(Path(folder),layout_override="PIXEL_EXACT")
                )


if __name__ == "__main__":
    unittest.main()
