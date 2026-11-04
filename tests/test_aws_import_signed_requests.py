"""Synthetic AWS HMAC gateway/backend contract. No AWS, Firebase or Firestore."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard_source"))
sys.path.insert(0, str(ROOT / "backend_source"))

from aws_import_signer import sign_prepared_import
from aws_import_verifier import verify_aws_import_request


class FakeRequest:
    def __init__(self, prepared, body=None, path=None, method=None):
        self.headers = dict(prepared.headers)
        self.method = method or prepared.method
        full = path or prepared.path_url
        self.path = full.partition("?")[0]
        self.query_string = full.partition("?")[2].encode("ascii")
        self.body = prepared.body if body is None else body
        self.content_length = len(self.body)
        self.max_content_length = None

    def get_data(self, cache=True):
        return self.body


class SignedImportContractTests(unittest.TestCase):
    NOW = 1780000000
    NONCE = "0123456789abcdef" * 2

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name)
        directory.chmod(0o700)
        self.key_file = str(directory / "service.key")
        Path(self.key_file).write_bytes(b"K" * 48)
        os.chmod(self.key_file, 0o600)
        self.replay_db = str(directory / "replays.sqlite")

    def make_signed(self, method="POST", path="/imports/preview", body=b"example body"):
        prepared = SimpleNamespace(method=method, path_url=path,
                                   body=body, headers={})
        sign_prepared_import(prepared, key_path=self.key_file,
                             now=self.NOW, nonce=self.NONCE)
        return prepared

    def verify(self, request, **kwargs):
        return verify_aws_import_request(
            request, key_path=self.key_file, replay_db=self.replay_db,
            now=self.NOW, **kwargs)

    def test_valid_signature_allowed_once(self):
        request = FakeRequest(self.make_signed())
        self.assertTrue(self.verify(request))
        self.assertFalse(self.verify(request))

    def test_tampered_body_denied(self):
        request = FakeRequest(self.make_signed(), body=b"changed")
        self.assertFalse(self.verify(request))

    def test_tampered_query_denied(self):
        request = FakeRequest(self.make_signed(method="GET",
                            path="/imports/" + "a" * 32 + "/rows?after=1",
                            body=b""), path="/imports/" + "a" * 32 + "/rows?after=2")
        self.assertFalse(self.verify(request))

    def test_tampered_method_denied(self):
        self.assertFalse(self.verify(FakeRequest(self.make_signed(), method="GET")))

    def test_missing_auth_denied(self):
        request = FakeRequest(self.make_signed())
        request.headers.clear()
        self.assertFalse(self.verify(request))

    def test_wrong_key_denied(self):
        request = FakeRequest(self.make_signed())
        wrong = str(Path(self.tmp.name) / "wrong.key")
        Path(wrong).write_bytes(b"W" * 48)
        self.assertFalse(verify_aws_import_request(
            request, key_path=wrong, replay_db=self.replay_db, now=self.NOW))

    def test_expired_timestamp_denied(self):
        self.assertFalse(verify_aws_import_request(
            FakeRequest(self.make_signed()), key_path=self.key_file,
            replay_db=self.replay_db, now=self.NOW + 31))

    def test_future_timestamp_denied(self):
        self.assertFalse(verify_aws_import_request(
            FakeRequest(self.make_signed()), key_path=self.key_file,
            replay_db=self.replay_db, now=self.NOW - 31))

    def test_missing_replay_db_denies_even_valid_signature(self):
        self.assertFalse(verify_aws_import_request(
            FakeRequest(self.make_signed()), key_path=self.key_file,
            replay_db="", now=self.NOW))

    def test_world_readable_replay_directory_denied(self):
        Path(self.tmp.name).chmod(0o755)
        self.assertFalse(self.verify(FakeRequest(self.make_signed())))

    def test_short_key_cannot_sign(self):
        Path(self.key_file).write_bytes(b"too-short")
        with self.assertRaises(ValueError):
            self.make_signed()

    def test_invalid_signed_route_rejected(self):
        with self.assertRaises(ValueError):
            self.make_signed(path="/reports")

    def test_missing_key_file_denied(self):
        self.assertFalse(verify_aws_import_request(
            FakeRequest(self.make_signed()), key_path="/missing-service-auth-key",
            replay_db=self.replay_db, now=self.NOW))

    def test_untrusted_nonce_denied(self):
        request = FakeRequest(self.make_signed())
        request.headers["X-SBI-Auth-Nonce"] = "0" * 32
        self.assertFalse(self.verify(request))


if __name__ == "__main__":
    unittest.main()
